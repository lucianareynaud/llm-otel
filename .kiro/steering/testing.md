# Testing Steering

## Test execution command
All tests must be run with OTel disabled:
```bash
OTEL_SDK_DISABLED=true pytest tests/ -v
```
Never run `pytest` without `OTEL_SDK_DISABLED=true`. OTel startup in tests causes
background threads, exporter connection attempts, and intermittent teardown failures.

## pytest configuration (pyproject.toml)
```toml
[tool.pytest.ini_options]
asyncio_mode = "auto"
```

`asyncio_mode = "auto"` makes every `async def test_...` function run as an asyncio test
without needing `@pytest.mark.asyncio` decorators. Do not add decorators — they are redundant
with this setting and add noise.

---

## Async test pattern
All test functions that call `async def` code must themselves be `async def`:

```python
# Correct
async def test_call_llm_returns_result():
    with patch("gateway.client._call_provider", new_callable=AsyncMock) as mock_provider:
        mock_provider.return_value = ("response text", 10, 20)
        result = await call_llm("Hello", "/answer-routed")
    assert result.text == "response text"

# Wrong — will hang or fail silently
def test_call_llm_returns_result():
    result = call_llm("Hello", "/answer-routed")  # returns a coroutine, not a result
```

---

## Mocking async functions — use AsyncMock
When patching a function that is `async def`, always use `AsyncMock`, not `Mock`:

```python
from unittest.mock import AsyncMock, patch

# Correct — call_llm is async def
with patch("app.routes.answer_routed.call_llm", new_callable=AsyncMock) as mock_llm:
    mock_llm.return_value = GatewayResult(text="answer", ...)
    response = client.post("/answer-routed", ...)

# Wrong — regular Mock cannot be awaited
with patch("app.routes.answer_routed.call_llm") as mock_llm:
    mock_llm.return_value = GatewayResult(...)  # TypeError: object is not awaitable
```

`TestClient` from `starlette.testclient` handles async route handlers transparently —
you do not need `AsyncClient` for route-level tests. Only use `AsyncMock` for the *patch*,
not for the test client.

---

## Mocking OpenAI errors
Use real `openai.*Error` classes, not plain `Exception`:

```python
import httpx
import openai

def _make_rate_limit_error() -> openai.RateLimitError:
    response = httpx.Response(429, request=httpx.Request("POST", "https://api.openai.com"))
    return openai.RateLimitError("rate limited", response=response, body={})

def _make_auth_error() -> openai.AuthenticationError:
    response = httpx.Response(401, request=httpx.Request("POST", "https://api.openai.com"))
    return openai.AuthenticationError("unauthorized", response=response, body={})
```

The gateway uses `isinstance(error, openai.RateLimitError)` — a plain `Exception("rate limited")`
will not match and will be classified as `"unknown"` instead of `"rate_limit"`. This was the
root cause of a previous test failure.

---

## Environment variable injection
Use `monkeypatch.setenv()` to inject env vars in tests. Never set env vars globally in
module scope — they will bleed across tests:

```python
# Correct — scoped to the test or fixture
def test_auth_valid(monkeypatch):
    monkeypatch.setenv("APP_API_KEY", "test-key-123")
    response = client.post("/classify-complexity", ..., headers={"X-API-Key": "test-key-123"})
    assert response.status_code == 200

# Wrong — bleeds into other tests
os.environ["APP_API_KEY"] = "test-key-123"
```

For fixtures used across multiple tests in a file, use a session-scoped or function-scoped
`autouse=True` fixture:

```python
@pytest.fixture(autouse=True)
def set_required_env(monkeypatch):
    monkeypatch.setenv("APP_API_KEY", "test-key-123")
    monkeypatch.setenv("OTEL_SDK_DISABLED", "true")
```

---

## Dependency override pattern for FastAPI Depends()
When a route uses `Depends(get_conversation_store)`, override it in tests using
`app.dependency_overrides`:

```python
from app.services.conversation_store import InMemoryConversationStore, get_conversation_store

@pytest.fixture(autouse=True)
def override_conversation_store():
    store = InMemoryConversationStore()
    app.dependency_overrides[get_conversation_store] = lambda: store
    yield store
    app.dependency_overrides.clear()   # always clean up
```

The `yield` + `app.dependency_overrides.clear()` teardown is mandatory — if you forget it,
the override leaks into tests in other files.

---

## State reset between tests
Module-level singletons (cache, circuit breaker, conversation store) hold state between tests.
Always reset them in a `setup_function` or `autouse` fixture:

```python
import pytest
from gateway.cache import cache_clear
from gateway.circuit_breaker import circuit_force_state

@pytest.fixture(autouse=True)
def reset_gateway_state():
    cache_clear()
    circuit_force_state("closed")
    yield
```

Without this, a test that opens the circuit breaker will cause the next test's circuit check
to raise `CircuitOpenError` unexpectedly.

---

## Testing rate limiting
The rate limiter uses real timestamps. Set `RATE_LIMIT_RPM` to a small number in fixtures:

```python
@pytest.fixture(autouse=True)
def rate_limit_env(monkeypatch):
    monkeypatch.setenv("RATE_LIMIT_RPM", "3")
```

Create a new `TestClient` instance (or new middleware instance) for each test that checks
rate limiting — the deque carries state within a client instance.

---

## What to test vs. what to mock

### Always mock at the OpenAI boundary
Never call the real OpenAI API in tests. Mock at the lowest boundary:

- For gateway tests: mock `_call_provider` (not `call_llm`)
- For route tests: mock `call_llm` with `AsyncMock`
- For routing tests: mock `openai.embeddings.create`
- For cache semantic tests: mock `_cache._embed`

### Do not mock internal business logic
Do not mock `determine_complexity`, `prepare_context`, or `count_tokens` in route tests —
these are pure functions with no I/O that should be tested with real inputs.

### Assert on behaviour, not implementation
Test what the function returns or what side effects it produces — not how it does it
internally:

```python
# Correct — tests observable behaviour
assert result.selected_model == "gpt-4o-mini"
assert response.status_code == 200

# Wrong — tests implementation details
assert mock_client.responses.create.call_count == 1
assert "_call_provider" in str(mock_calls)
```

---

## Test file organisation
Each new component gets its own test file:

| Component | Test file |
|---|---|
| Auth middleware | `tests/test_auth.py` |
| Rate limit middleware | `tests/test_rate_limit.py` |
| Token counter | `tests/test_token_counter.py` |
| Semantic cache | `tests/test_cache.py` |
| Circuit breaker | `tests/test_circuit_breaker.py` |
| Conversation store | `tests/test_conversation_store.py` |
| Gateway (call_llm, errors, retry) | `tests/test_gateway.py` |
| Routes | `tests/test_routes.py` |
| Services (routing, context) | `tests/test_services.py` |

Do not add tests for new components to `test_gateway.py` or `test_routes.py` unless they
are specifically testing gateway or route behaviour.

---

## Minimum test coverage per component

| Component | Minimum tests |
|---|---|
| Auth middleware | valid key, missing key, wrong key, health bypass (×2 for healthz + readyz) |
| Rate limit | under limit, at limit, over limit, two-key isolation |
| Token counter | known string exact count, empty string, unknown model fallback, cache reuse |
| Semantic cache | exact hit, miss, stats hit/miss counters, clear, cross-model isolation, bypass when disabled |
| Circuit breaker | initial closed, threshold opens, check raises when open, timeout → half-open, success closes, failure reopens, thread safety |
| Conversation store | get unknown returns [], append+get preserves order, delete, TTL expiry, two IDs isolated, Redis contract with fakeredis |
| Routing (embedding) | correct tuple type with mocked embeddings, fallback on API error, cosine identical=1.0, kNN majority vote, disabled path |

---

## Test count tracking
The test count must match the spec's expected value after each spec is complete:

| After spec | Expected total |
|---|---|
| 001–004 + OTel | 135 |
| 006 | 138 |
| 007 | 147 |
| 009 | 151 |
| 010 | 159 |
| 011 | 167 |
| 012 | 176 |
| 013 | 182 |

If the count diverges from this table, investigate before proceeding to the next spec.

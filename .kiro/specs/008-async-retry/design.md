# Design: 008 Async-Safe Gateway Retry

---

## Call chain after this spec

```
async def answer_routed() / conversation_turn()
  → await call_llm(...)
    → async def call_llm()
      → await _call_provider(...)
        → async def _call_provider()
          → await client.responses.create(...)   # AsyncOpenAI
          → await asyncio.sleep(2**attempt)       # on retry only
```

`classify_complexity` is not in this chain — it never calls the gateway.

---

## gateway/client.py changes

### OpenAI client

```python
# Before
from openai import OpenAI
client = OpenAI(api_key=api_key)
response = client.responses.create(...)

# After
from openai import AsyncOpenAI
client = AsyncOpenAI(api_key=api_key)
response = await client.responses.create(...)
```

The `AsyncOpenAI` constructor signature is identical to `OpenAI`. No other constructor
arguments change.

### Sleep replacement

```python
# Before
import time
time.sleep(2**attempt)

# After
import asyncio
await asyncio.sleep(2**attempt)
```

`import time` is kept because `time.perf_counter()` is used for wall-clock latency measurement
and is not async-sensitive.

### Function signatures

```python
async def call_llm(
    prompt: str,
    route: str,
    context_strategy: str | None = None,
    context_tokens_used: int = 0,
) -> GatewayResult:

async def _call_provider(
    model: str,
    prompt: str,
    api_key: str,
    max_tokens: int,
    attempt: int,
) -> tuple[str, int, int]:
```

All internal logic remains identical. Only the `def` → `async def` keywords and sleep call change.

---

## Route handler changes

### app/routes/answer_routed.py

```python
# Before
def answer_routed(request: AnswerRoutedRequest) -> AnswerRoutedResponse:
    ...
    result = call_llm(...)

# After
async def answer_routed(request: AnswerRoutedRequest) -> AnswerRoutedResponse:
    ...
    result = await call_llm(...)
```

### app/routes/conversation_turn.py

```python
# Before
def conversation_turn(request: ConversationTurnRequest) -> ConversationTurnResponse:
    ...
    result = call_llm(...)

# After
async def conversation_turn(request: ConversationTurnRequest) -> ConversationTurnResponse:
    ...
    result = await call_llm(...)
```

---

## Test changes

### tests/test_gateway.py — direct call_llm tests

```python
# Before
def test_call_llm_success():
    result = call_llm(...)
    assert result.text == "..."

# After
@pytest.mark.asyncio
async def test_call_llm_success():
    result = await call_llm(...)
    assert result.text == "..."
```

### tests/test_routes.py — patched call_llm tests

```python
# Before
with patch("app.routes.answer_routed.call_llm", return_value=mock_result):
    response = client.post(...)

# After
with patch("app.routes.answer_routed.call_llm", new_callable=AsyncMock, return_value=mock_result):
    response = client.post(...)
```

`TestClient` from `starlette.testclient` handles async route handlers transparently — no
change needed to the `TestClient` instantiation or request calls.

---

## pytest-asyncio configuration

Add to `pyproject.toml`:

```toml
[tool.pytest.ini_options]
asyncio_mode = "auto"
```

With `asyncio_mode = "auto"`, all `async def` test functions are treated as asyncio tests
without requiring explicit `@pytest.mark.asyncio` decorators. This is cleaner and avoids
decorator churn when adding async tests in later specs.

# Coding Standards

## Language and runtime
- Python 3.11 exclusively. No Python 3.10 or earlier syntax.
- FastAPI for the HTTP layer. Do not replace or augment with another framework.
- Pydantic v2 for request/response contracts and data validation.
- `AsyncOpenAI` for all provider calls. Never use the synchronous `OpenAI` client.

## Linting, formatting, and type checking
Run before every commit and in CI:
```bash
ruff check .
ruff format --check .
mypy app/ gateway/ evals/ reporting/ --ignore-missing-imports
```

All three must exit zero. A PR that fails any check is blocked from merging.

Ruff configuration (`pyproject.toml`):
```toml
[tool.ruff]
line-length = 100
select = ["E", "F", "I", "UP", "W", "B", "C4"]
ignore = ["B008", "B904"]
exclude = [".venv", ".git", "__pycache__", "artifacts"]

[tool.ruff.format]
quote-style = "double"
indent-style = "space"
```

Mypy configuration (`pyproject.toml`):
```toml
[tool.mypy]
python_version = "3.11"
packages = ["app", "gateway", "evals", "reporting"]
ignore_missing_imports = true
warn_return_any = true
warn_unused_ignores = true
warn_unused_configs = true
no_implicit_optional = true
strict_equality = true
```

## Async rules

All gateway calls are async. The full call chain must be async end-to-end:

```
async def route_handler()
  → await call_llm()
    → await _call_provider()
      → await client.responses.create()   # AsyncOpenAI
      → await asyncio.sleep()             # retry backoff only
```

**Never call `time.sleep()` in any async context.** Use `await asyncio.sleep()` for
all backoff delays in the gateway retry loop.

`app/routes/classify_complexity.py` is the only route that may remain synchronous —
it does not call the gateway.

When writing async test functions, rely on `asyncio_mode = "auto"` in `pyproject.toml`.
Do not add `@pytest.mark.asyncio` decorators — they are redundant and noisy with auto mode.

## Type annotations
All public functions must have complete type annotations including return type:
```python
def count_tokens(text: str, model: str = "gpt-4o") -> int: ...
async def call_llm(prompt: str, route: str, ...) -> GatewayResult: ...
```

Use `|` union syntax (Python 3.10+), not `Optional[X]` or `Union[X, Y]`:
```python
def get(self, conversation_id: str) -> list[str]: ...     # correct
def find(self, key: str) -> str | None: ...               # correct
def find(self, key: str) -> Optional[str]: ...            # wrong
```

Use `Literal` for constrained string values:
```python
CircuitState = Literal["closed", "open", "half_open"]
```

Use `typing.Protocol` for interfaces (not ABC):
```python
class ConversationStore(Protocol):
    def get(self, conversation_id: str) -> list[str]: ...
```

Use `dataclasses.dataclass(frozen=True)` for immutable value objects:
```python
@dataclasses.dataclass(frozen=True)
class CacheStats:
    hits: int
    misses: int
    size: int
```

## Module and function design

Modules must be named after concrete responsibilities:
- Good: `token_counter.py`, `circuit_breaker.py`, `conversation_store.py`, `cost_model.py`
- Bad: `utils.py`, `helpers.py`, `manager.py`, `base.py`, `common.py`

Functions must have one responsibility. If a function needs a comment to explain what each
section does, it should be split into smaller functions.

Public functions must have docstrings that explain:
- what the function does
- non-obvious behaviour (not restatements of the code)
- error conditions that callers must handle

Private functions (prefixed `_`) do not require docstrings unless the logic is non-trivial.

## Middleware pattern
Middleware must be implemented as Starlette `BaseHTTPMiddleware` subclasses:

```python
class MyMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)
        # read env vars here, raise ValueError if required vars are missing

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        if request.url.path in self._EXEMPT_PATHS:
            return await call_next(request)
        # ... logic ...
        return await call_next(request)
```

Middleware reads its configuration from env vars at `__init__` time, not at request time.
If a required env var is missing, raise `ValueError` from `__init__` so the app fails to
start rather than failing at the first request.

## Singleton pattern for stateful gateway components
The cache, circuit breaker, and conversation store each have a module-level singleton.
Public module-level functions delegate to the singleton:

```python
# gateway/cache.py
_cache = SemanticCache()

def cache_get(prompt: str, model: str) -> str | None:
    return _cache.get(prompt, model)
```

This pattern keeps the public API stable while allowing tests to reset state via the
singleton directly (e.g., `_cache.clear()`).

## Dependency injection for swappable components
Use FastAPI's `Depends()` for components that need different implementations in tests:

```python
# In route handler
async def conversation_turn(
    request: ConversationTurnRequest,
    store: ConversationStore = Depends(get_conversation_store),
) -> ConversationTurnResponse:
```

In tests, override with `app.dependency_overrides[get_conversation_store] = lambda: InMemoryConversationStore()`.

## Error handling

Use `isinstance` checks against specific exception types from the `openai` package:
```python
# Correct
if isinstance(error, openai.RateLimitError): ...

# Wrong — fragile, breaks on message changes
if "Rate limit" in str(error): ...
```

For gateway errors, always set a stable `error_type` string in the telemetry emit call.
Known error types: `"rate_limit"`, `"auth_error"`, `"timeout"`, `"transient_error"`,
`"invalid_request"`, `"circuit_open"`, `"unknown"`.

Catch exceptions only where you can meaningfully handle or translate them. Do not silently
swallow exceptions unless falling back to a degraded path is an explicit policy (e.g.,
embedding classifier fallback to keyword matching).

When falling back to a degraded path, always log a warning:
```python
logging.getLogger(__name__).warning("Embedding classifier failed; falling back to keyword classifier")
```

## Security rules

- Never log API key values. Log only status indicators like `"auth=ok"` or `"auth=fail"`.
- Use `secrets.compare_digest()` for API key comparison (prevents timing attacks).
- `APP_API_KEY` must be read from env — never hardcoded.
- The rate limiter sliding window stores only timestamps, never request bodies or headers.

## Configuration rules

- All configuration via environment variables.
- Every env var must have a safe default (except `OPENAI_API_KEY` and `APP_API_KEY` which are
  required — raise `ValueError` at startup if absent).
- Defaults are documented in `architecture.md` configuration reference.
- Read env vars at module or class `__init__` time, not at function call time, to make
  misconfiguration visible on startup.

## Dependency management

- All packages pinned to exact versions in `requirements.txt`.
- `redis` is a soft dependency: import conditionally inside `RedisConversationStore.__init__`
  only. The module must load without Redis installed.
- `numpy` is not a dependency. All vector arithmetic uses pure Python.
- When adding a new package, add it to `requirements.txt` with a pinned version before any
  code that imports it.

## Commenting rules

Comments must explain intent or non-obvious constraints — not restate the code:
```python
# Correct: explains a non-obvious constraint
# Embedding computation uses openai.embeddings.create() directly, not call_llm(),
# to avoid recursive cost tracking in the telemetry pipeline.

# Wrong: restates the code
# Create a SHA-256 hash of the model and prompt
key = hashlib.sha256(f"{model}:{prompt}".encode()).hexdigest()
```

Upgrade path comments are required in two places:
1. `RateLimitMiddleware` — Redis upgrade path for multi-instance deployments
2. `InMemoryConversationStore` and `SemanticCache` — Redis upgrade path

Pricing source comments are required in `gateway/cost_model.py`:
```python
# Source: https://platform.openai.com/docs/models — retrieved YYYY-MM-DD
```

## Anti-patterns — never introduce these

- `utils.py`, `helpers.py`, or any dumping-ground module
- Base classes for hypothetical future providers
- Abstract factory for the gateway
- Plugin/registry systems
- Deep inheritance hierarchies
- `**kwargs` forwarding through multiple layers
- `Any` type annotations (except where unavoidable with third-party libraries)
- Global mutable state outside the three explicit singletons (cache, circuit breaker, ready flag)
- Synchronous I/O in async route handlers (no `time.sleep`, no synchronous file I/O)
- Hardcoded model names in route handlers (always via `RoutePolicy`)
- Business logic in middleware (only auth and rate limit enforcement)
- Telemetry logic outside `gateway/telemetry.py`

## Code review standard
A file is acceptable only if another engineer can immediately answer:
1. What does this module do?
2. Why does it exist as a separate module?
3. Who calls it and from where?
4. How is it tested?
5. What artifacts or side effects does it produce?

If the answer to any of these requires reading more than two files, the implementation
is too complex.

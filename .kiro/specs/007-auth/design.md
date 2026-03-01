# Design: 007 Authentication and Rate Limiting

---

## APIKeyMiddleware (app/middleware/auth.py)

Starlette `BaseHTTPMiddleware` subclass. Reads `APP_API_KEY` from the environment once at
`__init__` time. If the env var is missing, raises `ValueError` immediately — this surfaces
as a startup error before the app accepts any traffic.

```python
class APIKeyMiddleware(BaseHTTPMiddleware):
    _EXEMPT_PATHS = {"/healthz", "/readyz"}

    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)
        key = os.environ.get("APP_API_KEY")
        if not key:
            raise ValueError("APP_API_KEY environment variable is required")
        self._key = key

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        if request.url.path in self._EXEMPT_PATHS:
            return await call_next(request)
        provided = request.headers.get("X-API-Key", "")
        if not secrets.compare_digest(provided, self._key):
            return JSONResponse({"detail": "Unauthorized"}, status_code=401)
        return await call_next(request)
```

`secrets.compare_digest` prevents timing-based key enumeration attacks. The key value is
never logged — only `"auth=ok"` or `"auth=fail"` at DEBUG level.

---

## RateLimitMiddleware (app/middleware/rate_limit.py)

Starlette `BaseHTTPMiddleware` subclass. Implements a per-key sliding window counter using
`collections.deque`. The deque stores request timestamps; entries older than 60 seconds are
purged on each request before counting.

```python
class RateLimitMiddleware(BaseHTTPMiddleware):
    _EXEMPT_PATHS = {"/healthz", "/readyz"}

    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)
        self._rpm = int(os.environ.get("RATE_LIMIT_RPM", "60"))
        self._windows: dict[str, deque[float]] = {}
        # For multi-instance deployments, replace deque with Redis ZRANGEBYSCORE + ZADD

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        if request.url.path in self._EXEMPT_PATHS:
            return await call_next(request)
        key = request.headers.get("X-API-Key", "__anonymous__")
        now = time.monotonic()
        window = self._windows.setdefault(key, deque())
        # Evict timestamps older than 60 s
        while window and now - window[0] > 60.0:
            window.popleft()
        if len(window) >= self._rpm:
            return JSONResponse(
                {"detail": "Rate limit exceeded"},
                status_code=429,
                headers={"Retry-After": "60"},
            )
        window.append(now)
        return await call_next(request)
```

---

## Middleware registration order in app/main.py

Starlette adds middleware in stack order — the last `add_middleware()` call is the outermost
wrapper (runs first on the request path, last on the response path).

To ensure **auth runs before rate limiting** (we don't want to count rejected requests against
the rate limit):

```python
# Add rate limit second → it is the inner wrapper → runs second on request
app.add_middleware(RateLimitMiddleware)
# Add auth first → it is the outer wrapper → runs first on request
app.add_middleware(APIKeyMiddleware)
```

This means: unauthenticated requests are rejected by `APIKeyMiddleware` before
`RateLimitMiddleware` increments any counter.

---

## APP_API_KEY startup validation

The `ValueError` raised inside `APIKeyMiddleware.__init__` will propagate during
`app.add_middleware(APIKeyMiddleware)` registration, which happens at module load time
before any request is served. The process exits with a clear error message rather than
serving open endpoints.

---

## Test fixture pattern

```python
# In test files
@pytest.fixture(autouse=True)
def set_api_key(monkeypatch):
    monkeypatch.setenv("APP_API_KEY", "test-key-123")

# In test requests
response = client.post("/classify-complexity", ..., headers={"X-API-Key": "test-key-123"})
```

The `autouse=True` fixture ensures every test in `test_auth.py` and `test_rate_limit.py`
has the env var set before the middleware is constructed.

For `test_routes.py`, add `X-API-Key: test-key-123` to all existing request calls.
The `APP_API_KEY` fixture must be added to the existing session-scoped fixture in that file.

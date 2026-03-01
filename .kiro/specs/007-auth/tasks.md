# Tasks: 007 Authentication and Rate Limiting

## Prerequisite gate
Run before starting any task:

```bash
OTEL_SDK_DISABLED=true pytest tests/ -v  # must report ≥ 138 tests, all passing
```

If any test fails, fix it first. Do not proceed while the gate is red.

---

## Task 1 — Create app/middleware/ package

- [ ] 1.1 Create `app/middleware/__init__.py` (empty)

**Acceptance**: `python -c "import app.middleware"` succeeds.

---

## Task 2 — Implement APIKeyMiddleware

- [ ] 2.1 Create `app/middleware/auth.py`
- [ ] 2.2 Import: `import os, secrets`, `from starlette.middleware.base import BaseHTTPMiddleware`,
  `from starlette.types import ASGIApp`, `from fastapi import Request, Response`,
  `from fastapi.responses import JSONResponse`
- [ ] 2.3 Implement `APIKeyMiddleware(BaseHTTPMiddleware)`:
  - `_EXEMPT_PATHS = {"/healthz", "/readyz"}` as a class constant
  - `__init__`: read `APP_API_KEY` from `os.environ`; raise `ValueError` if absent or empty
  - `dispatch`: if path in `_EXEMPT_PATHS` → pass through; else check header with
    `secrets.compare_digest`; reject with HTTP 401 if mismatch; pass through on match
  - Never log the key value — log only `"auth=ok"` or `"auth=fail"` at `logging.DEBUG`
- [ ] 2.4 Verify: `ruff check app/middleware/auth.py` — zero errors
- [ ] 2.5 Verify: `mypy app/middleware/auth.py --ignore-missing-imports` — zero errors

**Acceptance**: Module imports. Auth logic is self-contained. No route handler imports.

---

## Task 3 — Implement RateLimitMiddleware

- [ ] 3.1 Create `app/middleware/rate_limit.py`
- [ ] 3.2 Import: `import os, time`, `from collections import deque`, `from starlette.middleware.base import BaseHTTPMiddleware`, `from fastapi.responses import JSONResponse`
- [ ] 3.3 Implement `RateLimitMiddleware(BaseHTTPMiddleware)`:
  - `_EXEMPT_PATHS = {"/healthz", "/readyz"}` as a class constant
  - `__init__`: read `RATE_LIMIT_RPM` from env (default `60`); initialise `_windows: dict[str, deque[float]] = {}`
  - Add a comment: `# For multi-instance deployments, replace deque with Redis ZRANGEBYSCORE + ZADD`
  - `dispatch`: exempt health paths; get key from `X-API-Key` header (fallback `"__anonymous__"`);
    evict stale timestamps; if `len(window) >= rpm` return HTTP 429 with `Retry-After: 60`;
    else append timestamp and pass through
- [ ] 3.4 Verify: `ruff check app/middleware/rate_limit.py` — zero errors

**Acceptance**: Module imports. Rate window is per-key. Health paths are exempt.

---

## Task 4 — Register middlewares in app/main.py

- [ ] 4.1 Open `app/main.py`
- [ ] 4.2 Add at the top of the file (inside the lifespan function, before `setup_otel()`):
  ```python
  import os
  if not os.environ.get("APP_API_KEY"):
      raise ValueError("APP_API_KEY environment variable is required")
  ```
  (This provides a clear startup error message. The middleware also validates it, but this
  surfaces the error before the OTel setup begins.)
- [ ] 4.3 Import both middlewares:
  ```python
  from app.middleware.auth import APIKeyMiddleware
  from app.middleware.rate_limit import RateLimitMiddleware
  ```
- [ ] 4.4 Register in the correct order (rate limit first, auth second — so auth is outermost):
  ```python
  app.add_middleware(RateLimitMiddleware)
  app.add_middleware(APIKeyMiddleware)
  ```
  These go at module level (not inside the lifespan handler), after the `app = FastAPI(...)` call.

**Acceptance**: App starts correctly with `APP_API_KEY=test-key uvicorn app.main:app`.
Without `APP_API_KEY`, the process raises `ValueError` before accepting requests.

---

## Task 5 — Create tests/test_auth.py

- [ ] 5.1 Create `tests/test_auth.py`
- [ ] 5.2 Add a `monkeypatch`-based fixture that sets `APP_API_KEY=test-key-007`
- [ ] 5.3 Write the following tests (all using `TestClient`):
  - `test_valid_key_passes`: POST `/classify-complexity` with `X-API-Key: test-key-007` → HTTP 200
  - `test_missing_key_rejected`: POST `/classify-complexity` with no `X-API-Key` → HTTP 401,
    body `{"detail": "Unauthorized"}`
  - `test_wrong_key_rejected`: POST `/classify-complexity` with `X-API-Key: wrong-key` → HTTP 401
  - `test_healthz_exempt`: GET `/healthz` with no `X-API-Key` → HTTP 200
  - `test_readyz_exempt`: GET `/readyz` with no `X-API-Key` → HTTP 200 or 503 (either is correct)
- [ ] 5.4 Run: `OTEL_SDK_DISABLED=true pytest tests/test_auth.py -v` — all 5 tests pass

**Acceptance**: All 5 auth tests pass. The `APP_API_KEY` env var is injected via monkeypatch.

---

## Task 6 — Create tests/test_rate_limit.py

- [ ] 6.1 Create `tests/test_rate_limit.py`
- [ ] 6.2 Add fixtures: `APP_API_KEY=test-key-007` and `RATE_LIMIT_RPM=3`
- [ ] 6.3 Write the following tests:
  - `test_under_limit_passes`: 2 requests → both HTTP 200
  - `test_at_limit_passes`: exactly 3 requests → all HTTP 200
  - `test_over_limit_rejected`: 4th request → HTTP 429, `Retry-After` header present
  - `test_different_keys_independent`: 3 requests with key A + 3 requests with key B → all HTTP 200;
    4th request with either key → HTTP 429
- [ ] 6.4 Each test must create a fresh `TestClient` (or reset the rate limit window) to prevent
  counter state leaking between tests
- [ ] 6.5 Run: `OTEL_SDK_DISABLED=true pytest tests/test_rate_limit.py -v` — all 4 tests pass

**Acceptance**: All 4 rate limit tests pass. Key isolation is verified.

---

## Task 7 — Update existing route tests

- [ ] 7.1 Open `tests/test_routes.py`
- [ ] 7.2 Add a session-scoped fixture that sets `APP_API_KEY=test-key-007` via monkeypatch
- [ ] 7.3 Add `headers={"X-API-Key": "test-key-007"}` to every `client.get()` and `client.post()`
  call in the file
- [ ] 7.4 Run: `OTEL_SDK_DISABLED=true pytest tests/test_routes.py -v` — all existing tests pass

**Acceptance**: No existing test changes its assertion logic. Only headers are added.

---

## Task 8 — Full verification

- [ ] 8.1 `OTEL_SDK_DISABLED=true pytest tests/ -v` — all tests pass (138 + 9 = ≥ 147)
- [ ] 8.2 `ruff check app/middleware/` — zero errors
- [ ] 8.3 `mypy app/middleware/ --ignore-missing-imports` — zero errors
- [ ] 8.4 Confirm no log line ever contains the value of `APP_API_KEY` (grep log output)

**Acceptance**: Full test suite green. No key leakage in logs. Both middlewares deployed.

---

## Completion criteria
This spec is complete when:
- Requests without `X-API-Key` return HTTP 401 on all business routes
- Requests exceeding `RATE_LIMIT_RPM` return HTTP 429 with `Retry-After`
- Health endpoints remain accessible without auth
- `APP_API_KEY` missing at startup raises `ValueError` before any request is served
- `OTEL_SDK_DISABLED=true pytest tests/ -v` reports ≥ 147 tests, all passing
- No route handler contains any auth or rate-limit logic

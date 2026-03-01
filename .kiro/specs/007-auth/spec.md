# Spec: 007 Authentication and Rate Limiting

## Goal
Prevent any unauthenticated request from triggering a billable LLM call, and enforce a
per-caller request-per-minute ceiling to prevent runaway billing. Both controls are implemented
as FastAPI middleware so route handlers contain zero auth logic.

## Prerequisite gate
Spec 006 must be complete before starting:

```bash
OTEL_SDK_DISABLED=true pytest tests/ -v  # ≥ 138 tests, all passing
curl http://localhost:8000/healthz        # HTTP 200
curl http://localhost:8000/readyz         # HTTP 200 after startup
```

All checks must pass before any task in this spec begins.

## What this spec adds
- `app/middleware/auth.py` — `APIKeyMiddleware`
- `app/middleware/rate_limit.py` — `RateLimitMiddleware`
- `tests/test_auth.py` — auth middleware unit tests
- `tests/test_rate_limit.py` — rate limit middleware unit tests

## What this spec changes
- `app/main.py` — register both middlewares, add `APP_API_KEY` startup validation
- `tests/test_routes.py` — add `X-API-Key` header to all existing route test requests

## What this spec does NOT change
Route handlers, gateway, schemas, telemetry, OTel setup, health endpoints, and CI workflows
are frozen.

## Problem
All three API endpoints are fully open. Any HTTP client that can reach the application can
trigger LLM calls billed to the configured `OPENAI_API_KEY`. There is no per-caller identity
and no spending ceiling.

## Acceptance criteria
1. A request to `/answer-routed` without `X-API-Key` returns HTTP 401 `{"detail": "Unauthorized"}`.
2. A request with a wrong `X-API-Key` value returns HTTP 401.
3. A request with the correct `X-API-Key` value proceeds normally.
4. `GET /healthz` without `X-API-Key` returns HTTP 200 (auth-exempt).
5. `GET /readyz` without `X-API-Key` returns HTTP 200 or 503 as appropriate (auth-exempt).
6. A caller that sends more requests per minute than `RATE_LIMIT_RPM` receives HTTP 429 with
   a `Retry-After: 60` header.
7. Two callers with different API keys have independent rate limit counters.
8. The app refuses to start if `APP_API_KEY` is not set in the environment (raises `ValueError`).
9. The `APP_API_KEY` value is never written to any log output.
10. `OTEL_SDK_DISABLED=true pytest tests/ -v` passes — all existing tests plus new auth/rate-limit tests.

## Testing requirements
- `tests/test_auth.py`: valid key, missing key, wrong key, health endpoint bypass.
- `tests/test_rate_limit.py`: under limit, at limit, over limit, per-key isolation.
  Use `RATE_LIMIT_RPM=3` in test fixtures to keep the window small.
- All existing route tests in `tests/test_routes.py` must pass after adding the required
  `X-API-Key` header to every request fixture.
- Tests inject `APP_API_KEY` via `monkeypatch.setenv` — no real env var setup needed.

## Hard rules
- Middleware enforced at the middleware layer only — no `Depends()` auth guards in route handlers.
- Exempt paths (`/healthz`, `/readyz`) must be hardcoded in the middleware, not as a config option.
- Rate limit sliding window must use stdlib only (`collections.deque`) — no external packages.
- Middleware registration order in `app/main.py`: `APIKeyMiddleware` executes first
  (runs the auth check before the rate limiter counts the request).
- `APP_API_KEY` must be a required env var. The app must not start without it.
- A comment must document the Redis upgrade path for the rate limiter.

# Spec: 006 Health Endpoints and CI/CD Pipeline

## Goal
Make the application deployable behind any load balancer or orchestrator, and gate every code
change behind automated quality checks. These two concerns are grouped together because both
are infrastructure-visibility features with no product logic — and CI immediately validates
the health endpoints once they exist.

## Prerequisite gate
Spec 005 must be complete before starting:

```bash
OTEL_SDK_DISABLED=true pytest tests/ -v
grep -r "gpt-5" . # must return zero matches
```

Both must pass with no errors before any task in this spec begins.

## What this spec adds
- `app/routes/health.py` — `/healthz` and `/readyz` endpoints
- `.github/workflows/ci.yml` — lint + type check + test pipeline
- `.github/workflows/regression.yml` — eval regression pipeline
- `pyproject.toml` — ruff and mypy configuration (if not already present)

## What this spec changes
- `app/main.py` — register health router, add readiness flag to lifespan

## What this spec does NOT change
All three business routes, gateway, schemas, telemetry, OTel setup, and eval harness are frozen.

## Problem
There are no health or readiness endpoints. Kubernetes liveness probes, ECS health checks,
and nginx upstreams all require a `/healthz` to route traffic safely. Without it, the app
cannot be placed behind any load balancer.

`.github/workflows/ci.yml` and `.github/workflows/regression.yml` are empty files. No automated
gate exists on pull requests. Broken tests and lint errors can be merged to `main` silently.

## Acceptance criteria
1. `GET /healthz` returns HTTP 200 `{"status": "ok"}` at all times, including during startup and shutdown.
2. `GET /readyz` returns HTTP 200 `{"status": "ready"}` after the lifespan handler completes startup.
3. `GET /readyz` returns HTTP 503 `{"status": "not_ready"}` before startup completes and after shutdown begins.
4. Neither endpoint triggers any gateway call or touches `gateway/client.py`.
5. A pull request that introduces a failing pytest test is blocked from merging by CI.
6. A pull request that introduces a ruff lint error is blocked from merging by CI.
7. CI runs without any secrets — all LLM calls are mocked in tests.
8. Regression workflow runs all three eval runners and fails if `failed > 0` in any result.
9. `OTEL_SDK_DISABLED=true pytest tests/ -v` passes — all 135+ tests remain green.
10. New test count: 135 + 3 = 138 minimum.

## Testing requirements
- `tests/test_routes.py` (or a new `tests/test_health.py`): three tests covering `/healthz` (always 200), `/readyz` when ready (200), `/readyz` when not ready (503).
- Tests must use `monkeypatch` to control the readiness flag — not a real lifespan boot.
- No mock of the gateway is needed — these endpoints must never reach the gateway.

## Hard rules
- `/healthz` must never return non-200 regardless of application state.
- `/readyz` must not check downstream dependencies (no OpenAI ping, no Redis ping).
- Health endpoints must be excluded from OTel HTTP span instrumentation.
- CI must use Python 3.11 (matches the project constraint).
- All GitHub Actions action versions must be pinned (e.g. `actions/checkout@v4`).
- No `OPENAI_API_KEY` secret is required in CI — all provider calls are mocked.
- `OTEL_SDK_DISABLED=true` must be set in every CI test step.

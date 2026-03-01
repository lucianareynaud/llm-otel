# Spec: 011 Circuit Breaker

## Goal
Add a circuit breaker around all provider calls so that sustained OpenAI API degradation
produces immediate HTTP 503 responses rather than tying up worker threads for the full retry
duration. This is the standard resilience pattern for any service that depends on a fallible
external API.

## Prerequisite gate
Spec 010 must be complete before starting:

```bash
OTEL_SDK_DISABLED=true pytest tests/ -v  # ≥ 159 tests, all passing
```

All tests must be green before any task in this spec begins.

## What this spec adds
- `gateway/circuit_breaker.py` — three-state circuit breaker implementation
- `tests/test_circuit_breaker.py` — circuit breaker unit tests

## What this spec changes
- `gateway/client.py` — wraps `_call_provider` with circuit breaker checks
- (No route, schema, middleware, or telemetry changes)

## What this spec does NOT change
Routes, schemas, middleware, auth, cache, token counting, and OTel setup are frozen.
The JSONL telemetry format gains only `"error_type": "circuit_open"` for breaker-tripped events,
which is backward compatible.

## Problem
When the OpenAI API is degraded, every active request retries to exhaustion. With the async
retry from spec 008 in place, the event loop is no longer blocked — but goroutines (async
tasks) still pile up, each waiting for its full backoff sequence. Under sustained degradation
with 5 concurrent requests and 3-retry policy, 15 async tasks are inflight simultaneously,
each consuming memory and connection-pool slots. There is no fast-fail mechanism.

## Acceptance criteria
1. After `CIRCUIT_BREAKER_FAILURE_THRESHOLD` consecutive failures, the circuit opens.
2. While open, `circuit_check()` raises `CircuitOpenError` immediately — no provider call, no retry.
3. HTTP 503 is returned within 50 ms when the circuit is open.
4. After `CIRCUIT_BREAKER_RESET_TIMEOUT_S` seconds, the circuit transitions to half-open.
5. A successful probe in half-open state closes the circuit.
6. A failed probe in half-open state re-opens the circuit.
7. Span attribute `llm_gateway.circuit_state` is set on every gateway call.
8. `OTEL_SDK_DISABLED=true pytest tests/ -v` — all tests pass.

## Testing requirements
- `tests/test_circuit_breaker.py`: initial state is closed; threshold failures open it;
  `check()` raises when open; timeout transition to half-open; success from half-open closes;
  failure from half-open re-opens; thread-safety test; `force_state()` for test setup.
- No new route-level tests needed — existing route tests cover the 200/503 surface.

## Hard rules
- The circuit breaker is route-agnostic: one global instance per provider, not per route.
- State is in-memory only — no Redis, no persistence across restarts.
- The breaker must be thread-safe using `threading.Lock`.
- `force_state()` is the only public method that bypasses the state machine (test use only).
- The circuit breaker must live entirely in `gateway/circuit_breaker.py`. Routes and route
  handlers must not import from it.
- When the circuit is open, telemetry is still emitted with `status="error"` and
  `error_type="circuit_open"`.

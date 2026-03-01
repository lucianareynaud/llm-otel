# Tasks: 011 Circuit Breaker

## Prerequisite gate
Run before starting any task:

```bash
OTEL_SDK_DISABLED=true pytest tests/ -v  # ≥ 213 tests, all passing
```

If any test fails, fix it before proceeding.

---

## Task 1 — Implement gateway/circuit_breaker.py

- [ ] 1.1 Create `gateway/circuit_breaker.py`
- [ ] 1.2 Add imports: `import os, threading, time` and `from typing import Literal`
- [ ] 1.3 Define `CircuitState = Literal["closed", "open", "half_open"]`
- [ ] 1.4 Define `CircuitOpenError(Exception)`:
  - Constructor: `__init__(self, state: CircuitState)`
  - Sets `self.state = state`
  - Calls `super().__init__(f"Circuit breaker is {state}")`
- [ ] 1.5 Implement `class CircuitBreaker`:
  - `__init__`: initialise `_state="closed"`, `_failure_count=0`, `_last_failure_time=0.0`,
    `_lock=threading.Lock()`; read `CIRCUIT_BREAKER_FAILURE_THRESHOLD` (default 5) and
    `CIRCUIT_BREAKER_RESET_TIMEOUT_S` (default 30) from env vars
  - `state` property: returns `_state`
  - `check()`: under lock — if `OPEN` and timeout elapsed → transition to `HALF_OPEN`;
    if `OPEN` and timeout not elapsed → raise `CircuitOpenError`; else return
  - `record_success()`: under lock — if `HALF_OPEN` → transition to `CLOSED`, reset `_failure_count`
  - `record_failure()`: under lock — if `CLOSED` and `count < threshold` → increment count;
    if `CLOSED` and `count >= threshold` → open circuit, record time;
    if `HALF_OPEN` → re-open circuit, record time
  - `force_state(state)`: under lock — directly set `_state`; if opening, set `_last_failure_time`
- [ ] 1.6 Add module-level singleton: `_breaker = CircuitBreaker()`
- [ ] 1.7 Add public functions: `circuit_check`, `circuit_record_success`, `circuit_record_failure`,
  `circuit_force_state`, `circuit_state`
- [ ] 1.8 `ruff check gateway/circuit_breaker.py` — zero errors
- [ ] 1.9 `mypy gateway/circuit_breaker.py --ignore-missing-imports` — zero errors

**Acceptance**: Module imports. `circuit_check()` raises `CircuitOpenError` when state is `"open"`.

---

## Task 2 — Create tests/test_circuit_breaker.py

- [ ] 2.1 Create `tests/test_circuit_breaker.py`
- [ ] 2.2 Add a `setup_function` or `autouse` fixture that resets the breaker to `"closed"` state
  before each test using `circuit_force_state("closed")`
- [ ] 2.3 Write:
  - `test_initial_state_closed`: `circuit_state() == "closed"`
  - `test_threshold_failures_open_circuit`: call `circuit_record_failure()` N times where
    N equals `CIRCUIT_BREAKER_FAILURE_THRESHOLD` (default 5); assert `circuit_state() == "open"`
  - `test_check_raises_when_open`: `circuit_force_state("open")` then `circuit_check()` raises `CircuitOpenError`
  - `test_check_transitions_to_half_open_after_timeout`: `circuit_force_state("open")`;
    directly set `_breaker._last_failure_time = time.monotonic() - 999`; call `circuit_check()`;
    assert `circuit_state() == "half_open"`
  - `test_success_from_half_open_closes`: `circuit_force_state("half_open")`;
    `circuit_record_success()`; assert `circuit_state() == "closed"`
  - `test_failure_from_half_open_reopens`: `circuit_force_state("half_open")`;
    `circuit_record_failure()`; assert `circuit_state() == "open"`
  - `test_thread_safety`: spin up 20 threads each calling `circuit_record_failure()` 1 time;
    join all; assert `_breaker._failure_count <= 20` (no data corruption)
  - `test_force_state_is_immediate`: `circuit_force_state("open")` then `circuit_state() == "open"`
- [ ] 2.4 Run: `OTEL_SDK_DISABLED=true pytest tests/test_circuit_breaker.py -v` — all 8 tests pass

**Acceptance**: All 8 circuit breaker tests pass. Thread-safety test does not raise or corrupt state.

---

## Task 3 — Integrate circuit breaker into gateway/client.py

- [ ] 3.1 Open `gateway/client.py`
- [ ] 3.2 Add imports:
  ```python
  from gateway.circuit_breaker import (
      circuit_check,
      circuit_record_success,
      circuit_record_failure,
      circuit_state,
      CircuitOpenError,
  )
  ```
- [ ] 3.3 In `call_llm`, after the cache check and before `_call_provider`, add:
  ```python
  try:
      circuit_check()
  except CircuitOpenError:
      emit(..., status="error", error_type="circuit_open")
      span.set_attribute("llm_gateway.circuit_state", "open")
      raise HTTPException(status_code=503, detail="Service temporarily unavailable")
  span.set_attribute("llm_gateway.circuit_state", circuit_state())
  ```
- [ ] 3.4 After a successful provider call: call `circuit_record_success()`
- [ ] 3.5 After a non-retryable exception: call `circuit_record_failure()` before re-raising
- [ ] 3.6 After retry exhaustion (all attempts failed): call `circuit_record_failure()` once,
  after the retry loop exits — not inside the loop
- [ ] 3.7 `ruff check gateway/client.py` — zero errors

**Acceptance**: `CircuitOpenError` causes HTTP 503 without touching `_call_provider`. Span attribute is set.

---

## Task 4 — Full verification

- [ ] 4.1 `OTEL_SDK_DISABLED=true pytest tests/ -v` — all tests pass, ≥ 221 tests
- [ ] 4.2 Manual: force circuit open, send request to `/answer-routed`, measure response time < 50 ms
- [ ] 4.3 `ruff check gateway/circuit_breaker.py gateway/client.py` — zero errors

**Acceptance**: Full test suite green. Circuit breaker fast-fail verified.

---

## Completion criteria
This spec is complete when:
- `circuit_check()` raises `CircuitOpenError` after threshold failures
- HTTP 503 is returned immediately (no provider call) when circuit is open
- `llm_gateway.circuit_state` span attribute is set on every request
- `OTEL_SDK_DISABLED=true pytest tests/ -v` reports ≥ 221 tests, all passing
- Circuit breaker state is never modified from outside `gateway/circuit_breaker.py`

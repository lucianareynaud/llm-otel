# Design: 011 Circuit Breaker

---

## State machine

```
             failure_count >= threshold
CLOSED  ──────────────────────────────►  OPEN
  ▲                                        │
  │  record_success()              reset_timeout elapsed
  │  (from HALF_OPEN)                      │
  │                                        ▼
  └──────────────────────────────  HALF_OPEN
           record_failure()
           (from HALF_OPEN) → back to OPEN
```

---

## gateway/circuit_breaker.py

```python
import os
import threading
import time
from typing import Literal

CircuitState = Literal["closed", "open", "half_open"]


class CircuitOpenError(Exception):
    def __init__(self, state: CircuitState) -> None:
        self.state = state
        super().__init__(f"Circuit breaker is {state}")


class CircuitBreaker:
    def __init__(self) -> None:
        self._state: CircuitState = "closed"
        self._failure_count: int = 0
        self._last_failure_time: float = 0.0
        self._lock = threading.Lock()
        self._threshold = int(os.environ.get("CIRCUIT_BREAKER_FAILURE_THRESHOLD", "5"))
        self._reset_timeout = float(os.environ.get("CIRCUIT_BREAKER_RESET_TIMEOUT_S", "30"))

    @property
    def state(self) -> CircuitState:
        return self._state

    def check(self) -> None:
        """Raise CircuitOpenError if the circuit should not allow a request through."""
        with self._lock:
            if self._state == "open":
                if time.monotonic() - self._last_failure_time >= self._reset_timeout:
                    self._state = "half_open"
                else:
                    raise CircuitOpenError(self._state)

    def record_success(self) -> None:
        with self._lock:
            if self._state == "half_open":
                self._state = "closed"
                self._failure_count = 0

    def record_failure(self) -> None:
        with self._lock:
            if self._state == "closed":
                self._failure_count += 1
                if self._failure_count >= self._threshold:
                    self._state = "open"
                    self._last_failure_time = time.monotonic()
            elif self._state == "half_open":
                self._state = "open"
                self._last_failure_time = time.monotonic()

    def force_state(self, state: CircuitState) -> None:
        """Test-only: directly set breaker state, bypassing normal transitions."""
        with self._lock:
            self._state = state
            if state == "open":
                self._last_failure_time = time.monotonic()
```

### Module-level singleton and public functions

```python
_breaker = CircuitBreaker()

def circuit_check() -> None:
    _breaker.check()

def circuit_record_success() -> None:
    _breaker.record_success()

def circuit_record_failure() -> None:
    _breaker.record_failure()

def circuit_force_state(state: CircuitState) -> None:
    _breaker.force_state(state)

def circuit_state() -> CircuitState:
    return _breaker.state
```

---

## gateway/client.py integration

### Placement in call_llm

The circuit check sits between the cache check and `_call_provider`:

```python
from gateway.circuit_breaker import (
    circuit_check, circuit_record_success, circuit_record_failure,
    circuit_state, CircuitOpenError
)

# In call_llm, after cache check:
try:
    circuit_check()
except CircuitOpenError:
    emit(..., status="error", error_type="circuit_open")
    span.set_attribute("llm_gateway.circuit_state", "open")
    raise HTTPException(status_code=503, detail="Service temporarily unavailable")

span.set_attribute("llm_gateway.circuit_state", circuit_state())

# After successful _call_provider:
circuit_record_success()

# After non-retryable exception or retry exhaustion:
circuit_record_failure()
```

### Failure recording rules

- Non-retryable error (any `openai.*Error` that `_is_retryable()` returns False for):
  call `circuit_record_failure()` immediately.
- Retryable error that exhausts all retry attempts: call `circuit_record_failure()` once
  after the final attempt — not on each individual retry.
- Retryable error that succeeds on a later attempt: call `circuit_record_success()` — the
  intermittent failure should not count against the circuit.

---

## Thread safety note

`threading.Lock` in `CircuitBreaker` protects all state mutations. FastAPI's async event loop
runs in a single thread per worker, but the lock is zero-cost when there is no contention.
If uvicorn runs multiple workers (multiple processes), each process has its own circuit breaker
instance — this is acceptable for the MVP. A Redis-backed shared breaker is a future upgrade.

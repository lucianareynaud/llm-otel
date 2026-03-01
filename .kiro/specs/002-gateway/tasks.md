# Tasks: 002 Gateway

## Implementation order
Tasks must be executed in the order listed to maintain safe incremental progress.

## Task list

### 1. Define structured gateway result contract
Create the structured result type returned by the gateway.

- [x] 1.1 Update `gateway/client.py`
  - Define a structured gateway result type
  - The result must contain at minimum:
    - `text`
    - `selected_model`
    - `request_id`
    - `tokens_in`
    - `tokens_out`
    - `estimated_cost_usd`
    - `cache_hit`
  - Keep the contract concrete and inspectable
  - Do not introduce provider abstractions

**Acceptance**: Gateway public call path is designed around a structured result, not a raw string.

---

### 2. Create cost model
Create deterministic cost estimation from local pricing configuration.

- [x] 2.1 Create `gateway/cost_model.py`
  - Define a local inspectable pricing dictionary for the current provider
  - Implement `estimate_cost(model: str, tokens_in: int, tokens_out: int) -> float`
  - Implement `get_pricing() -> dict`
  - Use deterministic arithmetic only
  - Add docstrings
  - Keep pricing local and inspectable

**Acceptance**: Cost model exists and returns deterministic estimates for known configured models.

---

### 3. Create route policies for gateway-backed routes
Create simple route-specific policy configuration for routes that currently use the gateway.

- [x] 3.1 Create `gateway/policies.py`
  - Define `RoutePolicy` dataclass
  - Include only fields required by the current design, such as:
    - `max_output_tokens`
    - `retry_attempts`
    - `cache_enabled`
    - logical tier behavior
  - Define hardcoded policies for:
    - `/answer-routed`
    - `/conversation-turn`
  - Do not require a gateway policy for `/classify-complexity` in the current repo state
  - Implement `get_route_policy(route_name: str) -> RoutePolicy`
  - Add docstrings
  - Keep policies simple and inspectable

**Acceptance**: Policy module exists with hardcoded route policies for gateway-backed routes.

---

### 4. Create telemetry emission
Create structured event creation and JSON-lines emission.

- [x] 4.1 Create `gateway/telemetry.py`
  - Implement simple JSON-lines emission
  - Write events to `artifacts/logs/telemetry.jsonl`
  - Required fields:
    - `timestamp`
    - `request_id`
    - `route`
    - `provider`
    - `model`
    - `latency_ms`
    - `status`
    - `tokens_in`
    - `tokens_out`
    - `estimated_cost_usd`
    - `cache_hit`
    - `schema_valid`
    - `error_type`
  - Support optional route metadata fields:
    - `selected_model`
    - `routing_decision`
    - `routing_reason`
    - `context_strategy`
    - `context_tokens_used`
    - `conversation_id`
    - `turn_index`
    - `prompt_version`
  - Use direct append-based file writing
  - Add docstrings

**Acceptance**: Telemetry module exists and writes stable structured JSON lines.

---

### 5. Create minimal optional cache
Create minimal local cache capability, but keep it conservative.

- [x] 5.1 Create `gateway/cache.py`
  - Implement simple dict-based in-memory cache
  - Implement `get(prompt: str, model: str) -> str | None`
  - Implement `put(prompt: str, model: str, response: str) -> None`
  - Use simple deterministic cache keys
  - Add docstrings
  - Do not add TTL, eviction, persistence, or distributed behavior

**Acceptance**: Minimal cache capability exists and is easy to disable.

---

### 6. Replace temporary gateway stub with real concrete gateway behavior
Update the gateway client to support the current provider and structured result output.

- [x] 6.1 Update `gateway/client.py`
  - Replace the temporary stub with real current-provider integration
  - Keep implementation concrete and provider-specific for the MVP
  - Implement:
    - request_id generation
    - route policy lookup
    - local tier-to-model resolution
    - optional cache check if enabled by policy
    - provider call
    - latency measurement
    - token extraction from provider response
    - deterministic cost estimation
    - telemetry emission
    - structured result return
  - Keep retry logic simple and bounded
  - Emit stable `error_type` values on failure
  - Do not introduce abstraction layers, factories, or plugin systems

**Acceptance**: Gateway client performs real provider-backed calls and returns structured gateway results.

---

### 7. Update route integration where needed
Adjust current route handlers only as needed to consume the structured gateway result.

- [x] 7.1 Update gateway-backed routes
  - Update `/answer-routed` if needed to consume structured result fields directly
  - Update `/conversation-turn` if needed to consume structured result fields directly
  - Do not expand scope beyond current route needs
  - Do not migrate `/classify-complexity` into the gateway unless explicitly required

**Acceptance**: Current gateway-backed routes work with the structured gateway result contract.

---

### 8. Update requirements.txt
Add the current provider SDK dependency.

- [x] 8.1 Update `requirements.txt`
  - Add the provider SDK package required by the gateway implementation

**Acceptance**: requirements.txt includes the dependency needed for real gateway calls.

---

### 9. Create gateway tests
Create deterministic tests for gateway components.

- [x] 9.1 Create or update `tests/test_gateway.py`
  - Test structured gateway result shape
  - Test `cost_model.estimate_cost()` with known inputs
  - Test `policies.get_route_policy()` for current gateway-backed routes
  - Test cache get/put behavior if cache is implemented
  - Test telemetry emission shape
  - Test successful gateway call path with mocked provider responses
  - Test error path with mocked provider failures
  - Test retry behavior if retries are implemented
  - Test route metadata propagation into telemetry
  - Mock provider API responses for deterministic tests
  - Add docstrings

**Acceptance**: Gateway tests pass and cover the concrete MVP gateway behavior.

---

### 10. Optional live smoke verification
Optionally verify real provider integration after deterministic tests pass.

- [ ] 10.1 Manual smoke verification
  - Set required provider API key environment variable
  - Start app with `uvicorn app.main:app --reload`
  - Call `/answer-routed`
  - Call `/conversation-turn`
  - Verify responses are returned
  - Verify `artifacts/logs/telemetry.jsonl` is created and populated

This is a smoke check, not the primary correctness proof.

**Acceptance**: Optional live smoke check succeeds if credentials are available.

---

### 11. Update README with gateway information
Document concrete gateway behavior and telemetry output.

- [x] 11.1 Update `README.md`
  - Add a short "Gateway" section
  - Document required environment variable for the current provider
  - Document telemetry output location: `artifacts/logs/telemetry.jsonl`
  - Add one example telemetry event shape
  - Keep documentation minimal and exact

**Acceptance**: README documents gateway behavior and telemetry output.

---

### 12. Verify acceptance criteria
Verify all relevant spec acceptance criteria are met.

- [x] 12.1 Verify gateway-backed routes use the gateway
  - Confirm `/answer-routed` calls gateway
  - Confirm `/conversation-turn` calls gateway

- [x] 12.2 Verify structured gateway result
  - Confirm client returns structured result fields
  - Confirm routes consume the result correctly

- [x] 12.3 Verify telemetry emission
  - Check `telemetry.jsonl` exists
  - Verify events contain required fields

- [x] 12.4 Verify deterministic cost estimation
  - Check `estimated_cost_usd` is present
  - Verify estimates are stable for mocked inputs

- [x] 12.5 Verify policy behavior
  - Test route policy lookup
  - Verify max output token handling where applicable

- [x] 12.6 Verify optional cache behavior if enabled
  - Test cache hit/miss behavior only if cache is active
  - Verify `cache_hit` field in telemetry

- [x] 12.7 Verify route metadata propagation
  - Check routing metadata for `/answer-routed`
  - Check context metadata for `/conversation-turn`

- [x] 12.8 Verify inspectability
  - Verify no provider abstractions exist
  - Verify policies remain hardcoded and readable
  - Verify pricing remains local and readable

**Acceptance**: Relevant gateway acceptance criteria are verified and documented.

---

## Task completion criteria
A task is complete only when:
- all code exists and is committed
- all relevant tests pass
- code is inspectable and follows coding standards
- no scope creep or speculative abstractions were added
- the gateway remains concrete and MVP-scoped

## Notes
- Use the current provider SDK directly
- Keep all configuration local and inspectable
- Mock provider API calls in tests for determinism
- Focus on the current gateway-backed routes only
- Do not add multi-provider support
- Do not add plugin systems, registries, or factories
- Keep everything minimal, explicit, and inspectable

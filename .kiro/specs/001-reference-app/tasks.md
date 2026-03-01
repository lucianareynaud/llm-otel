# Tasks: 001 Reference App

## Implementation order
Tasks must be executed in the order listed to maintain safe incremental progress.

## Task list

### 1. Create explicit request and response schemas
Create explicit Pydantic request and response models for all three routes.

- [x] 1.1 Create `app/schemas/classify_complexity_request.py`
  - Define `ClassifyComplexityRequest` with field: `message`
  - Add docstrings

- [x] 1.2 Create `app/schemas/classify_complexity_response.py`
  - Define `ClassifyComplexityResponse` with fields: `complexity`, `recommended_tier`, `needs_escalation`
  - Use Literal types for enum fields
  - Add docstrings

- [x] 1.3 Create `app/schemas/answer_routed_request.py`
  - Define `AnswerRoutedRequest` with field: `message`
  - Add docstrings

- [x] 1.4 Create `app/schemas/answer_routed_response.py`
  - Define `AnswerRoutedResponse` with fields: `answer`, `selected_model`, `routing_decision`
  - Use Literal types for enum fields
  - Add docstrings

- [x] 1.5 Create `app/schemas/conversation_turn_request.py`
  - Define `ConversationTurnRequest` with fields: `conversation_id`, `history`, `message`, `context_strategy`
  - Use Literal types for `context_strategy`
  - Add docstrings

- [x] 1.6 Create `app/schemas/conversation_turn_response.py`
  - Define `ConversationTurnResponse` with fields: `answer`, `turn_index`, `context_tokens_used`, `context_strategy_applied`
  - Use Literal types for enum fields
  - Add docstrings

**Acceptance**: All schema files exist and define valid Pydantic models.

---

### 2. Create routing service
Create the shared routing logic used by `/classify-complexity` and `/answer-routed`.

- [x] 2.1 Create `app/services/routing.py`
  - Implement `determine_complexity(message: str) -> tuple[str, str, bool]`
  - Return: `(complexity, recommended_tier, needs_escalation)`
  - Use simple keyword-based heuristics
  - Keep logic deterministic and inspectable
  - Add docstrings
  - Do not call providers directly

**Acceptance**: `routing.py` exists with `determine_complexity()` function that returns stable outputs for deterministic test inputs.

---

### 3. Create context manager service
Create the context strategy logic for `/conversation-turn`.

- [x] 3.1 Create `app/services/context_manager.py`
  - Implement `prepare_context(history: list[str], message: str, strategy: str) -> tuple[str, int]`
  - Return: `(prepared_context, estimated_token_count)`
  - Support strategies: `full`, `sliding_window`, `summarized`
  - `full`: concatenate all history + message
  - `sliding_window`: keep last N messages + current message
  - `summarized`: use deterministic placeholder summarization for older history in MVP
  - Use simple token estimation (e.g. `len(text) // 4`)
  - Keep logic deterministic and inspectable
  - Add docstrings
  - Do not call providers directly

**Acceptance**: `context_manager.py` exists with `prepare_context()` function that handles all three strategies deterministically.

---

### 4. Create a temporary gateway stub
Create a minimal gateway boundary so route code still respects the architectural rule that all LLM calls go through the gateway.

- [x] 4.1 Create or update `gateway/client.py`
  - Add a temporary minimal callable interface for this phase
  - Accept route-relevant input and return deterministic mock output
  - Preserve a concrete gateway call path without implementing full Spec 002 behavior
  - Do not introduce provider abstractions or generalized policy systems

**Acceptance**: Route code can call a gateway boundary without making direct provider calls.

---

### 5. Create route: /classify-complexity
Create the cheapest route for complexity classification.

- [x] 5.1 Create `app/routes/classify_complexity.py`
  - Define POST route `/classify-complexity`
  - Use `ClassifyComplexityRequest`
  - Call `routing.determine_complexity(message)`
  - Return `ClassifyComplexityResponse`
  - Add docstrings
  - Keep handler thin

**Acceptance**: Route file exists, imports schemas and services correctly, and returns schema-compliant output.

---

### 6. Create route: /answer-routed
Create the routed answer generation route.

- [x] 6.1 Create `app/routes/answer_routed.py`
  - Define POST route `/answer-routed`
  - Use `AnswerRoutedRequest`
  - Call `routing.determine_complexity(message)` to get routing decision
  - Call the temporary gateway stub using the selected tier
  - Return `AnswerRoutedResponse` with routing metadata
  - Add docstrings
  - Keep handler thin

**Acceptance**: Route file exists, uses routing service, goes through the gateway boundary, and returns schema-compliant response with routing metadata.

---

### 7. Create route: /conversation-turn
Create the multi-turn conversation route.

- [x] 7.1 Create `app/routes/conversation_turn.py`
  - Define POST route `/conversation-turn`
  - Use `ConversationTurnRequest`
  - Call `context_manager.prepare_context(history, message, context_strategy)`
  - Call the temporary gateway stub with prepared context
  - Calculate `turn_index` from history length
  - Return `ConversationTurnResponse` with context metadata
  - Add docstrings
  - Keep handler thin

**Acceptance**: Route file exists, uses context manager, goes through the gateway boundary, and returns schema-compliant response with context metadata.

---

### 8. Create FastAPI app
Create the main FastAPI application and register routes.

- [x] 8.1 Update `app/main.py`
  - Create FastAPI app instance
  - Import and register all three route modules
  - Add basic app metadata
  - Keep file minimal and inspectable

**Acceptance**: `app/main.py` exists, registers all three routes, and the app is runnable with `uvicorn app.main:app --reload`.

---

### 9. Create minimal deterministic fixtures for tests
Create simple deterministic fixtures for route and service tests.

- [x] 9.1 Add deterministic test inputs for routing cases
  - Cover simple, medium, and complex messages
  - Cover cheap and expensive routing outcomes

- [x] 9.2 Add deterministic test inputs for conversation context cases
  - Cover `full`, `sliding_window`, and `summarized`
  - Cover different history lengths

**Acceptance**: Deterministic inputs exist and can be reused across tests.

---

### 10. Create route and service tests
Create tests for routes and core services.

- [x] 10.1 Update `tests/test_routes.py`
  - Add tests for `/classify-complexity`
  - Add tests for `/answer-routed`
  - Add tests for `/conversation-turn`
  - Test valid and invalid inputs
  - Test that routing/context metadata is present in responses

- [x] 10.2 Create or update `tests/test_services.py`
  - Test `routing.determine_complexity()` with deterministic inputs
  - Test `context_manager.prepare_context()` for all three strategies
  - Verify token count estimates are stable and reproducible

**Acceptance**: Route and service tests pass with deterministic results.

---

### 11. Update README with route documentation
Document how to run the app and call each route.

- [x] 11.1 Update `README.md`
  - Add "Running the Reference App" section
  - Document command: `uvicorn app.main:app --reload`
  - Add one example request for `/classify-complexity`
  - Add one example request for `/answer-routed`
  - Add one example request for `/conversation-turn`
  - Include expected response shapes
  - Keep examples minimal and exact

**Acceptance**: README includes run command and one example per route.

---

### 12. Verify acceptance criteria
Verify all spec acceptance criteria are met.

- [x] 12.1 Verify app runs locally with one command
  - Run: `uvicorn app.main:app --reload`
  - Verify app starts without errors

- [x] 12.2 Verify all three routes are callable
  - Call each route with example requests
  - Verify responses are returned

- [x] 12.3 Verify schema compliance
  - Verify all responses match declared schemas
  - Run schema validation tests

- [x] 12.4 Verify test inputs exist
  - Verify deterministic route and service cases exist

- [x] 12.5 Verify no direct provider calls
  - Grep codebase for direct provider imports
  - Verify route code goes through gateway boundary

- [x] 12.6 Verify route examples in README
  - Verify README contains exact request examples

- [x] 12.7 Verify app is inspectable
  - Verify handlers remain thin
  - Verify no hidden framework magic

- [x] 12.8 Verify different cost profiles are represented
  - Verify `/classify-complexity` represents the cheapest path
  - Verify `/answer-routed` exposes routing decisions
  - Verify `/conversation-turn` exposes context usage explicitly

**Acceptance**: All acceptance criteria from the spec are verified and documented.

---

## Task completion criteria
A task is complete only when:
- all code exists and is committed
- all relevant tests pass
- code is inspectable and follows coding standards
- no scope creep or speculative abstractions were added

## Notes
- The gateway in this phase is a temporary stub only
- Full gateway behavior belongs to Spec 002
- Focus on route structure, schemas, service logic, and a clean gateway boundary
- Keep everything minimal, explicit, and inspectable

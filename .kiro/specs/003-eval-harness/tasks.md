# Tasks: 003 Eval Harness

## Implementation order
Tasks must be executed in the order listed to preserve bounded scope, deterministic behavior, and safe incremental verification.

## Task list

### 1. Create dataset files
Create versioned JSONL datasets for all three routes.

- [x] 1.1 Create `evals/datasets/classify_cases.jsonl`
  - Add at least 5 cases for `/classify-complexity`
  - Each case must include: `id`, `input`, `expected`
  - Cases must cover: simple, medium, complex, long, and edge-case messages
  - Expected values must include exact expected outputs for:
    - `complexity`
    - `recommended_tier`
    - `needs_escalation`

- [x] 1.2 Create `evals/datasets/answer_routed_cases.jsonl`
  - Add at least 5 cases for `/answer-routed`
  - Each case must include: `id`, `input`, `expected`
  - Cases must cover: cheap path, expensive path, keyword-triggered routing, short message, edge case
  - Expected values must include bounded constraints only:
    - `routing_decision`
    - optional `min_answer_length`

- [x] 1.3 Create `evals/datasets/conversation_turn_cases.jsonl`
  - Add at least 5 cases for `/conversation-turn`
  - Each case must include: `id`, `input`, `expected`
  - Cases must cover: empty history, short history, full strategy, sliding_window, summarized
  - Expected values must include bounded constraints only:
    - `context_strategy_applied`
    - optional `min_answer_length`
    - optional expected `turn_index`

**Acceptance**: Three JSONL dataset files exist, are valid, versioned in-repo, and contain at least 5 bounded cases per route.

---

### 2. Create runner utility helpers
Create one tiny shared utility module for dataset loading and result writing.

- [x] 2.1 Create `evals/runners/common.py`
  - Implement `load_jsonl_cases(path: str) -> list[dict]`
  - Implement `write_eval_results(path: str, payload: dict) -> None`
  - Implement small helper for UTC timestamp generation
  - Keep file small and concrete
  - Do not introduce a framework, registry, or base runner abstraction

**Acceptance**: `evals/runners/common.py` exists and supports dataset loading and result writing for all runners.

---

### 3. Create assertion helpers
Create small explicit helper functions for bounded checks.

- [x] 3.1 Create `evals/assertions/schema_checks.py`
  - Implement `check_required_fields(response: dict, fields: list[str]) -> tuple[bool, str]`
  - Implement `check_field_type(response: dict, field: str, expected_type: type) -> tuple[bool, str]`
  - Implement `check_max_length(value: str, max_length: int) -> tuple[bool, str]`
  - Keep helpers small and explicit

- [x] 3.2 Create `evals/assertions/routing_checks.py`
  - Implement `check_routing_decision(response: dict, expected: str) -> tuple[bool, str]`
  - Implement `check_selected_model_present(response: dict) -> tuple[bool, str]`
  - Do not inspect semantic answer quality

- [x] 3.3 Create `evals/assertions/context_checks.py`
  - Implement `check_turn_index(response: dict, expected: int) -> tuple[bool, str]`
  - Implement `check_context_strategy(response: dict, expected: str) -> tuple[bool, str]`
  - Implement `check_context_tokens_present(response: dict) -> tuple[bool, str]`
  - Do not attempt semantic comparison

**Acceptance**: Assertion helper files exist, stay small, and return `(bool, str)` for pass/fail and explanation.

---

### 4. Create classify eval runner
Create the deterministic eval runner for `/classify-complexity`.

- [x] 4.1 Create `evals/runners/run_classify_eval.py`
  - Use `TestClient(app)` in-process
  - Load `evals/datasets/classify_cases.jsonl`
  - Call `POST /classify-complexity` for each case
  - Assert:
    - required fields present
    - exact `complexity` match
    - exact `recommended_tier` match
    - exact `needs_escalation` match
    - bounded response size
  - Write results to `artifacts/reports/classify_eval_results.json`
  - Exit with code `0` if all pass, `1` otherwise

**Acceptance**: `run_classify_eval.py` executes locally with `python3` and produces inspectable JSON results.

---

### 5. Create answer-routed eval runner
Create the deterministic eval runner for `/answer-routed`.

- [x] 5.1 Create `evals/runners/run_answer_routed_eval.py`
  - Use `TestClient(app)` in-process
  - Load `evals/datasets/answer_routed_cases.jsonl`
  - Default eval mode must patch or monkeypatch:
    - `app.routes.answer_routed.call_llm`
  - Do not require `OPENAI_API_KEY`
  - Do not hit live provider
  - Return deterministic mocked `GatewayResult`
  - Assert:
    - required fields present
    - `answer` is non-empty
    - `selected_model` present
    - `routing_decision` matches expected when specified
    - bounded response size
  - Write results to `artifacts/reports/answer_routed_eval_results.json`
  - Exit with code `0` if all pass, `1` otherwise

**Acceptance**: `run_answer_routed_eval.py` executes locally with `python3`, never depends on live gateway behavior, and produces inspectable JSON results.

---

### 6. Create conversation-turn eval runner
Create the deterministic eval runner for `/conversation-turn`.

- [x] 6.1 Create `evals/runners/run_conversation_turn_eval.py`
  - Use `TestClient(app)` in-process
  - Load `evals/datasets/conversation_turn_cases.jsonl`
  - Default eval mode must patch or monkeypatch:
    - `app.routes.conversation_turn.call_llm`
  - Do not require `OPENAI_API_KEY`
  - Do not hit live provider
  - Return deterministic mocked `GatewayResult`
  - Assert:
    - required fields present
    - `answer` is non-empty
    - `turn_index` matches expected when specified
    - `context_tokens_used` present and >= 0
    - `context_strategy_applied` matches expected when specified
    - bounded response size
  - Write results to `artifacts/reports/conversation_turn_eval_results.json`
  - Exit with code `0` if all pass, `1` otherwise

**Acceptance**: `run_conversation_turn_eval.py` executes locally with `python3`, never depends on live gateway behavior, and produces inspectable JSON results.

---

### 7. Add artifact directory handling
Ensure artifact directories are created deterministically.

- [x] 7.1 Update runner write paths
  - Ensure `artifacts/reports/` is created automatically if missing
  - Do not require manual setup
  - Keep file output simple and local

**Acceptance**: Running any eval runner from a clean repo creates the required artifact directory automatically.

---

### 8. Test dataset loading and assertion helpers
Create tests for the eval harness support code.

- [x] 8.1 Create `tests/test_evals.py`
  - Test JSONL dataset loading from temporary files
  - Test result writing format
  - Test `schema_checks.py`
  - Test `routing_checks.py`
  - Test `context_checks.py`
  - Use small deterministic inputs only

**Acceptance**: Helper and dataset-loading tests pass locally and remain independent of route behavior.

---

### 9. Test classify runner end-to-end
Add a small end-to-end smoke test for the classify runner.

- [x] 9.1 Extend `tests/test_evals.py`
  - Run classify eval against a temporary or small fixture dataset
  - Verify:
    - runner executes successfully
    - result JSON is written
    - pass/fail structure is correct
  - Do not rely on external HTTP or live provider calls

**Acceptance**: At least one small runner smoke test exists for classify eval.

---

### 10. Test gateway-backed runners end-to-end
Add small end-to-end smoke tests for the gateway-backed runners.

- [x] 10.1 Extend `tests/test_evals.py`
  - Add one smoke test for `run_answer_routed_eval.py`
  - Add one smoke test for `run_conversation_turn_eval.py`
  - Patch or monkeypatch route import-boundary call sites:
    - `app.routes.answer_routed.call_llm`
    - `app.routes.conversation_turn.call_llm`
  - Use tiny temporary or fixture datasets
  - Verify:
    - runner executes successfully
    - result JSON is written
    - pass/fail structure is correct
  - Do not require `OPENAI_API_KEY`
  - Do not require live provider calls

**Acceptance**: Each gateway-backed runner has at least one deterministic smoke test that exercises runner execution and artifact writing.

---

### 11. Update README with eval usage
Document how to run the eval harness.

- [x] 11.1 Update `README.md`
  - Add a section: `Eval Harness`
  - Document:
    - `python3 evals/runners/run_classify_eval.py`
    - `python3 evals/runners/run_answer_routed_eval.py`
    - `python3 evals/runners/run_conversation_turn_eval.py`
  - Mention artifact output path: `artifacts/reports/`
  - Explain that gateway-backed evals use mocked gateway behavior by default
  - Keep documentation exact and minimal

**Acceptance**: README includes exact eval commands and states where result artifacts are written.

---

### 12. Verify acceptance criteria
Verify the 003 spec acceptance criteria against the implemented harness.

- [x] 12.1 Verify each route has its own dataset and runner
  - Confirm all three JSONL datasets exist
  - Confirm all three runners exist

- [x] 12.2 Verify pass/fail output per case
  - Run each runner
  - Confirm output JSON contains per-case results

- [x] 12.3 Verify route-specific bounded checks
  - Confirm classify checks exact deterministic values
  - Confirm gateway-backed runners check metadata, schema, and bounded behavior only

- [x] 12.4 Verify local inspectability
  - Confirm result JSON files exist under `artifacts/reports/`
  - Confirm failures include readable reasons

- [x] 12.5 Verify no live provider dependency
  - Confirm eval runners do not require `OPENAI_API_KEY`
  - Confirm route import-boundary mocking is used for gateway-backed routes

- [x] 12.6 Verify no scope creep
  - Confirm there is no semantic eval
  - Confirm there is no model judge
  - Confirm there is no notebook workflow
  - Confirm there is no large benchmark suite

**Acceptance**: All 003 acceptance criteria are explicitly verified and documented.

---

## Task completion criteria
A task is complete only when:
- the files exist
- the code runs
- tests pass or are updated explicitly
- artifact files are produced where required
- no live provider dependency is introduced into the eval harness
- no speculative abstraction or framework was added

## Notes
- Default eval mode for gateway-backed routes must remain mocked and deterministic
- Live provider smoke testing remains outside 003
- Keep all eval inputs small, versioned, and inspectable
- Prefer explicit repetition over clever abstraction if the latter reduces clarity

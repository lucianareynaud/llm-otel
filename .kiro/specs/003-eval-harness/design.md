# Design: 003 Eval Harness

## Purpose
This design describes a bounded evaluation harness for detecting operational regressions in the reference app's three routes.

The harness focuses exclusively on:
- schema compliance
- required field presence
- bounded behavior checks
- routing metadata presence
- context metadata presence

It does not attempt semantic evaluation, model quality scoring, or open-ended judgment.

## Design Principles

### 1. Deterministic execution model
Runners execute routes in-process using FastAPI TestClient.

No external HTTP server is required.
No uvicorn startup is required.

For default eval execution:
- `/classify-complexity` runs directly with no mocking
- `/answer-routed` and `/conversation-turn` run with gateway calls mocked or monkeypatched
- eval runners must not require `OPENAI_API_KEY`
- eval runners must not depend on live provider calls

Live provider smoke tests are out of scope for this eval harness and remain separate from 003.

### 2. Bounded assertions
Assertions check only what can be verified deterministically:
- schema structure
- required field presence
- field type correctness
- bounded output size
- metadata field presence

Assertions do NOT check:
- exact text content for gateway-backed routes
- semantic quality
- subjective "goodness"
- LLM output variance

### 3. Route-specific behavior
The harness recognizes two operational patterns:

**Local deterministic routes:**
- `/classify-complexity` is local and deterministic
- No gateway calls
- No LLM variance
- Assertions can be strict and exact against expected values

**Gateway-backed routes:**
- `/answer-routed` and `/conversation-turn` call the gateway in production
- Default eval mode replaces gateway calls with deterministic mocked results
- Assertions focus on schema, metadata, bounded behavior, and non-empty outputs

### 4. Inspectable outputs
All eval outputs are written to `artifacts/reports/` or `artifacts/evals/`.

Source code and datasets remain under `evals/`.

Generated results are artifacts, not source.

### 5. Reproducibility
The same dataset run twice should produce:
- the same pass/fail outcomes for schema checks
- the same pass/fail outcomes for required field checks
- the same pass/fail outcomes for bounded behavior checks
- the same pass/fail outcomes for exact deterministic checks on local routes

Gateway-backed text content is not treated as a semantic gold target. The harness verifies contract compliance and bounded operational invariants.

## Component Design

### 1. Datasets

**Location:** `evals/datasets/`

**Format:** JSONL (one JSON object per line)

**Files:**
- `classify_cases.jsonl`
- `answer_routed_cases.jsonl`
- `conversation_turn_cases.jsonl`

**Dataset structure:**

Each case must include:
- `id`: unique case identifier
- `input`: request payload matching the route's request schema
- `expected`: optional expected output constraints (not exact text for gateway-backed routes)

Example for `/classify-complexity`:
```json
{
  "id": "classify_001",
  "input": {
    "message": "What is 2+2?"
  },
  "expected": {
    "complexity": "simple",
    "recommended_tier": "cheap",
    "needs_escalation": false
  }
}
```

Example for `/answer-routed`:
```json
{
  "id": "answer_routed_001",
  "input": {
    "message": "What is 2+2?"
  },
  "expected": {
    "routing_decision": "cheap",
    "min_answer_length": 1
  }
}
```

Example for `/conversation-turn`:
```json
{
  "id": "conversation_turn_001",
  "input": {
    "conversation_id": "conv_001",
    "message": "What is 2+2?",
    "history": [],
    "context_strategy": "full"
  },
  "expected": {
    "context_strategy_applied": "full",
    "min_answer_length": 1
  }
}
```

**Dataset requirements:**
- Minimum 5 cases per route
- Cases must be small and fast to execute
- Conversation histories must be short (≤3 turns)
- Cases must represent the route's intended operational profile

### 2. Runners

**Location:** `evals/runners/`

**Files:**
- `run_classify_eval.py`
- `run_answer_routed_eval.py`
- `run_conversation_turn_eval.py`

**Execution model:**
Each runner:
1. Imports the FastAPI app from `app.main`
2. Creates a TestClient instance
3. Loads the dataset from `evals/datasets/`
4. Executes each case via `client.post()`
5. Runs assertions on the response
6. Writes results to `artifacts/reports/{route_name}_eval_results.json`

For default eval execution:
- `run_classify_eval.py` calls the route directly
- `run_answer_routed_eval.py` monkeypatches or mocks `call_llm` to avoid live provider usage
- `run_conversation_turn_eval.py` monkeypatches or mocks `call_llm` to avoid live provider usage

**Runner output format:**
```json
{
  "route": "/classify-complexity",
  "timestamp": "2026-02-27T10:00:00Z",
  "total_cases": 5,
  "passed": 5,
  "failed": 0,
  "results": [
    {
      "case_id": "classify_001",
      "status": "pass",
      "assertions": {
        "schema_valid": true,
        "required_fields_present": true,
        "bounded_behavior": true
      }
    }
  ]
}
```

**Runner CLI:**
```bash
python evals/runners/run_classify_eval.py
python evals/runners/run_answer_routed_eval.py
python evals/runners/run_conversation_turn_eval.py
```

### 3. Assertions

**Location:** `evals/assertions/`

**Files:**
- `schema_checks.py`
- `routing_checks.py`
- `context_checks.py`

**Purpose:**
Small explicit helper functions that reduce duplication across runners.

These are NOT a generalized framework.
These are NOT a plugin system.
These are simple functions that return `(bool, str)` for pass/fail and reason.

**Example functions:**

`schema_checks.py`:
```python
def check_response_schema(response: dict, required_fields: list[str]) -> tuple[bool, str]:
    """Check that all required fields are present in the response."""
    ...

def check_field_type(response: dict, field: str, expected_type: type) -> tuple[bool, str]:
    """Check that a field has the expected type."""
    ...
```

`routing_checks.py`:
```python
def check_routing_metadata(response: dict) -> tuple[bool, str]:
    """Check that routing metadata fields are present."""
    ...
```

`context_checks.py`:
```python
def check_context_metadata(response: dict) -> tuple[bool, str]:
    """Check that context metadata fields are present."""
    ...
```

### 4. Route-Specific Assertion Design

#### `/classify-complexity` (local, deterministic)

**Assertions:**
- Schema valid
- `complexity` field present and exactly matches dataset `expected["complexity"]`
- `recommended_tier` field present and exactly matches dataset `expected["recommended_tier"]`
- `needs_escalation` field present and exactly matches dataset `expected["needs_escalation"]`
- Response size bounded (< 500 chars)

**No LLM variance:**
This route is deterministic. Assertions should check exact expected values.

#### `/answer-routed` (gateway-backed)

**Assertions:**
- Schema valid
- `answer` field present and non-empty (length > 0)
- `selected_model` field present and non-empty
- `routing_decision` field present and in `["cheap", "expensive"]`
- `routing_decision` matches dataset expected value when specified
- Response size bounded (< 5000 chars)

**LLM variance:**
Text content is not evaluated semantically. Default eval mode uses deterministic mocked gateway results so assertions remain stable and do not require a live API key.

#### `/conversation-turn` (gateway-backed)

**Assertions:**
- Schema valid
- `answer` field present and non-empty (length > 0)
- `turn_index` field present and >= 0
- `turn_index` matches history length when specified by the case
- `context_tokens_used` field present and >= 0
- `context_strategy_applied` field present and in `["full", "sliding_window", "summarized"]`
- `context_strategy_applied` matches dataset expected value when specified
- Response size bounded (< 5000 chars)

**LLM variance:**
Text content is not evaluated semantically. Default eval mode uses deterministic mocked gateway results so assertions remain stable and do not require a live API key.

## File Structure

```
evals/
├── datasets/
│   ├── classify_cases.jsonl
│   ├── answer_routed_cases.jsonl
│   └── conversation_turn_cases.jsonl
├── runners/
│   ├── run_classify_eval.py
│   ├── run_answer_routed_eval.py
│   └── run_conversation_turn_eval.py
└── assertions/
    ├── schema_checks.py
    ├── routing_checks.py
    └── context_checks.py

artifacts/
└── reports/
    ├── classify_eval_results.json
    ├── answer_routed_eval_results.json
    └── conversation_turn_eval_results.json

tests/
└── test_evals.py
```

## Testing Strategy

**File:** `tests/test_evals.py`

**Purpose:**
Test the eval harness itself, not the routes.

**Test coverage:**
- Dataset loading works
- Assertion helpers return correct pass/fail outcomes
- Runner output format is correct
- Gateway-backed runner mocking works
- Edge cases (empty responses, missing fields) are handled

**Not tested here:**
- Route behavior (covered by `tests/test_routes.py`)
- Gateway behavior (covered by `tests/test_gateway.py`)
- Live provider behavior (covered by separate smoke tests, not 003)

## Regression Detection Workflow

**Local development:**
```bash
python evals/runners/run_classify_eval.py
python evals/runners/run_answer_routed_eval.py
python evals/runners/run_conversation_turn_eval.py
```

**CI workflow:**
1. Run all three eval runners
2. Check exit codes (0 = all passed, 1 = any failed)
3. Fail the build if any eval fails
4. Publish eval results as CI artifacts

**Before/after comparison:**
1. Run evals before a change
2. Save results to `artifacts/reports/before/`
3. Make the change
4. Run evals after the change
5. Save results to `artifacts/reports/after/`
6. Compare pass/fail counts and failure reasons

## Acceptance Criteria Mapping

| Criterion | Design Element |
|-----------|----------------|
| Each route has its own dataset and runner | Three datasets, three runners |
| Eval output shows pass/fail per case | Runner output format includes per-case status |
| Route-specific bounded checks are implemented | Assertion design per route |
| Regression workflow runs in CI | CLI-invokable runners with exit codes |
| Failures are easy to inspect locally | JSON output with failure reasons |
| README explains how to run evals | README update task |
| No human labeling loops required | Bounded assertions only |

## Constraints Honored

**No notebooks:** All runners are CLI-invokable Python scripts.

**No model judge:** No LLM-as-a-judge evaluation.

**No semantic eval framework:** No BLEU, ROUGE, embedding similarity, or subjective scoring.

**No large benchmark suite:** Minimum 5 cases per route, designed for fast execution.

**Bounded and explicit:** All assertions are deterministic checks on structure and metadata.

## Final Design Rule

If an assertion cannot be verified deterministically from the response structure and metadata, it does not belong in this harness.

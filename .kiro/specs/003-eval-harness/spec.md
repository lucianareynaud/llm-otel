# Spec: 003 Eval Harness

## Goal
Create a bounded evaluation harness that detects operational regressions for each route in the reference app.

This harness does not attempt general model evaluation.
Its purpose is to detect regressions that matter for:
- schema compliance
- route-level reliability
- routing behavior
- bounded output behavior
- context-budget assumptions
- cost-control assumptions

## Principle
The evaluation harness must answer the following questions:

1. Is the route still returning valid structured output?
2. Did the failure rate increase?
3. Did the route violate bounded behavior expected by the MVP?
4. Did routing behavior drift in ways that break the intended cheap vs. expensive split?
5. Did context handling drift in ways that silently increase token usage or break constraints?

The harness must remain operationally useful, cheap to run, and easy to inspect.

## Required evaluation scope
Each route must have:
- its own versioned dataset
- its own runner
- route-specific assertions
- pass/fail output per case
- outputs that can run locally and in CI

## Required checks for all routes
For every route, evals must include:
- schema validity
- required field presence
- failure rate tracking
- route-specific bounded behavior checks

## Route-specific checks

### 1. /classify-complexity
The eval harness must verify:
- `complexity` is present and valid
- `recommended_tier` is present
- `needs_escalation` is boolean
- output remains schema-valid
- output remains short and bounded enough for the route's cheap profile

### 2. /answer-routed
The eval harness must verify:
- `answer` is present and non-empty
- `selected_model` is present
- `routing_decision` is present
- output remains schema-valid
- routing-specific fields are not silently dropped

### 3. /conversation-turn
The eval harness must verify:
- `answer` is present and non-empty
- `turn_index` is present
- `context_tokens_used` is present
- `context_strategy_applied` is present
- output remains schema-valid
- context-related fields are not silently dropped

## Dataset rules
- Datasets must be stored as JSONL files in-repo.
- Datasets must be deterministic and versioned.
- Minimum 5 cases per route.
- Each dataset must represent the intended operational profile of the route.
- Cases must be small enough to run repeatedly during development and CI.
- Conversation fixtures must use short, deterministic histories.

## Runner rules
- Each route must have its own runnable eval script.
- Each runner must be invokable with one command.
- Runner output must be easy to inspect locally.
- Failures must identify which case failed and why.

## Assertion rules
Assertions must remain bounded and explicit.

Allowed assertion types:
- schema checks
- required field checks
- length/size threshold checks
- route-specific structure checks
- routing metadata checks
- context metadata checks

Disallowed assertion types:
- vague semantic scoring
- open-ended “quality” judgments
- LLM-as-a-judge systems
- notebook-only evaluation flows

## Acceptance criteria
This spec is complete only if all of the following are true:

1. Each route has its own dataset and runner.
2. Eval output shows pass/fail per case.
3. Route-specific bounded checks are implemented.
4. Regression workflow runs in CI.
5. Failures are easy to inspect locally.
6. README explains how to run evals and add new cases.
7. The harness can be used repeatedly without human labeling loops.

## Required files
At minimum, this spec must result in:
- `evals/datasets/classify_cases.jsonl`
- `evals/datasets/answer_routed_cases.jsonl`
- `evals/datasets/conversation_turn_cases.jsonl`
- `evals/runners/run_classify_eval.py`
- `evals/runners/run_answer_routed_eval.py`
- `evals/runners/run_conversation_turn_eval.py`
- `evals/assertions/schema_checks.py`
- `evals/assertions/routing_checks.py`
- `evals/assertions/context_checks.py`
- `tests/test_evals.py`

## Explicitly out of scope
- human evaluation
- semantic similarity scoring
- BLEU, ROUGE, or embedding similarity metrics
- large benchmark suites
- model-judge systems
- notebook-dependent workflows
- expensive or slow evaluation pipelines

## Final constraint
If an evaluation approach makes the harness harder to rerun, harder to inspect, or more subjective without improving bounded regression detection, reject it.

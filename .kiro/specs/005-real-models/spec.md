# Spec: 005 Real Model Identifiers and Pricing

## Goal
Replace the fictional model names `gpt-5-mini` and `gpt-5.2` with real OpenAI model identifiers
so the application can make a single successful live LLM call. This is the only blocker that
prevents any real usage of the app, and it must be resolved before any other production work begins.

## Prerequisite gate
This is the first production-readiness spec. The entire test suite from specs 001–004 must pass
before starting:

```bash
OTEL_SDK_DISABLED=true pytest tests/ -v
```

All tests must be green. Zero failures permitted.

## What this spec changes
- `gateway/cost_model.py` — model names and pricing
- `gateway/policies.py` — model names in route policies
- `tests/test_gateway.py` — model name assertions
- `tests/test_routes.py` — mock GatewayResult model name fields

## What this spec does NOT change
Everything else is frozen. No route logic, no gateway call path, no schemas, no telemetry format,
no OTel setup, no middleware, no eval harness.

## Problem
Model names `gpt-5-mini` and `gpt-5.2` do not exist in the OpenAI API. Every call to
`/answer-routed` and `/conversation-turn` returns a 404 from the provider. The pricing dict
references the same fictional names, so cost estimation also produces zero output.
The app cannot demonstrate a single real LLM round-trip in its current state.

## Acceptance criteria
1. `gateway/cost_model.py` contains no reference to `gpt-5-mini` or `gpt-5.2`.
2. `gateway/policies.py` contains no reference to `gpt-5-mini` or `gpt-5.2`.
3. `grep -r "gpt-5" .` returns zero matches across all source files.
4. `OTEL_SDK_DISABLED=true pytest tests/ -v` passes — all existing tests green.
5. With a valid `OPENAI_API_KEY`, a POST to `/answer-routed` returns HTTP 200 with a real response body.

## Testing requirements
No new test files are created. Existing tests are updated to use the correct model names.
The update must not skip or stub any previously passing assertion.

## Hard rules
- Pricing must include a source comment (URL + retrieval date) — no uncommented magic numbers.
- The cheap tier maps to `gpt-4o-mini`; the expensive tier maps to `gpt-4o`.
- Pricing values must match the published OpenAI pricing at implementation time.
- No other files change in this spec.

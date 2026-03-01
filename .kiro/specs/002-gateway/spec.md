# Spec: 002 Gateway

## Goal
Create a thin and concrete gateway layer that is the single control point for all LLM provider calls in the MVP.

The gateway exists to make inference behavior measurable, policy-aware, token-efficient, and reproducible across all routes.
It must remain narrow, inspectable, and easy to test.

Its purpose is to support three specific operational concerns:
- cost-aware route execution
- routing-based model selection
- context-budget control for multi-turn flows

## Core responsibility
The gateway is responsible for:
- executing provider calls
- attaching route and request context
- recording structured telemetry
- estimating cost
- applying bounded policy controls
- enforcing token-economy defaults
- exposing a stable path for all route-level LLM usage

## Hard architectural rules
1. No direct provider call may exist outside `gateway/client.py`.
2. No route may contain provider-specific logic.
3. No route may calculate cost.
4. No route may implement retry or fallback behavior directly.
5. No route may implement caching directly.
6. No provider interface hierarchy may be introduced for future extensibility.
7. No plugin architecture, registry, or abstract factory may be introduced.
8. The gateway must remain concrete and MVP-scoped.

## Required gateway components

### `gateway/client.py`
A concrete provider client for the MVP.
It may support only one provider in the MVP.

### `gateway/telemetry.py`
Responsible for structured event creation and emission.

### `gateway/policies.py`
Responsible for bounded runtime policy handling, including:
- route-level max output tokens
- retry policy
- optional fallback model
- optional caching switch
- route-level context budget
- route-level prompt template selection
- route-level model selection rules

### `gateway/cache.py`
A minimal local cache implementation only if used by acceptance criteria.
Keep it simple and local.

### `gateway/cost_model.py`
Responsible for deterministic cost estimation from current pricing configuration.

## Telemetry contract
Every gateway-emitted event must include:

```json
{
  "timestamp": "ISO-8601 string",
  "request_id": "string",
  "route": "string",
  "provider": "string",
  "model": "string",
  "latency_ms": 0,
  "status": "success|error",
  "tokens_in": 0,
  "tokens_out": 0,
  "estimated_cost_usd": 0.0,
  "cache_hit": false,
  "schema_valid": true,
  "error_type": null
}
```

Additionally, when applicable, the event must support:
- `selected_model`
- `routing_decision`
- `routing_reason`
- `context_strategy`
- `context_tokens_used`
- `conversation_id`
- `turn_index`
- `prompt_version`

## Token economy requirements
The gateway must support bounded token-economy controls in the MVP:

1. route-specific `max_output_tokens`
2. route-specific prompt templates
3. route-specific context budgets for multi-turn flows
4. route-specific model selection
5. optional cache for repeated deterministic requests

These controls must be simple, inspectable, and testable.
Do not create generalized policy engines.

## Routing requirements
The gateway must support the operational needs of:
- `/classify-complexity`
- `/answer-routed`
- `/conversation-turn`

This means it must be able to:
- record the routing decision used by `/answer-routed`
- record which model was selected
- support cheaper vs. more expensive route behavior
- support context strategy metadata for `/conversation-turn`

The gateway must not implement a generalized workflow engine.
It must only support the current MVP route requirements.

## Cost model requirements
- Cost estimation must be deterministic from current pricing configuration.
- Pricing configuration must be local and inspectable.
- Cost must be attributable per request and aggregatable per route.
- The model must be simple enough to explain in one short document.
- Cost estimation must support route-level comparisons in reporting.

## Logging requirements
- Telemetry must be written as structured JSON lines.
- Logs must be readable by downstream aggregation scripts.
- Log format must remain stable enough for repeatable parsing.
- Do not mix prose logging with telemetry payloads.

## Functional acceptance criteria
This spec is complete only if all of the following are true:

1. All three reference app routes use the gateway.
2. The gateway successfully executes provider calls for all three routes.
3. Structured telemetry is emitted for all LLM calls.
4. Cost is estimated per request.
5. Policy behavior can be toggled and tested.
6. Cache hit or miss is recorded when caching is enabled.
7. The gateway can enforce smaller output budgets for cheaper routes.
8. The gateway can record routing decisions for `/answer-routed`.
9. The gateway can enforce and record context strategy metadata for `/conversation-turn`.
10. The gateway can be inspected and understood without provider-agnostic abstractions.

## Testing requirements
The gateway must be covered by tests for:
- successful call path
- error path
- retry behavior
- cost estimation
- cache hit/miss behavior
- telemetry emission shape
- route-specific output token cap behavior
- routing decision recording
- context budget behavior
- context strategy metadata emission

## Required files
At minimum, this spec must result in:
- `gateway/client.py`
- `gateway/telemetry.py`
- `gateway/policies.py`
- `gateway/cache.py`
- `gateway/cost_model.py`
- `tests/test_gateway.py`

## Explicitly out of scope
- multi-provider support
- provider-agnostic architecture
- distributed caching
- advanced rate limiting
- secrets management systems
- dashboard UI
- queueing systems
- plugin-based policy engines
- generalized orchestration frameworks

## Final constraint
If a proposed gateway design is more extensible but less concrete, less readable, or less testable for the current MVP, reject it.

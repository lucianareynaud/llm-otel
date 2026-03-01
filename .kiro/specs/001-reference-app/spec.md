# Spec: 001 Reference App

## Goal
Create a minimal FastAPI reference app with three controlled LLM workflows that make cost, routing decisions, and context growth measurable.

The app is not intended to be a user-facing product.
Its purpose is to create reproducible inference patterns that allow the project to demonstrate:
- route-level cost differences
- routing-based model selection
- context window growth and control
- stable structured outputs for evaluation

## Required routes
The app must expose exactly these three POST routes:

### 1. /classify-complexity
#### Input
```json
{ "message": "string" }
```

#### Output
```json
{
  "complexity": "simple|medium|complex",
  "recommended_tier": "cheap|expensive",
  "needs_escalation": false
}
```

### 2. /answer-routed
#### Input
```json
{ "message": "string" }
```

#### Output
```json
{
  "answer": "string",
  "selected_model": "string",
  "routing_decision": "cheap|expensive"
}
```

### 3. /conversation-turn
#### Input
```json
{
  "conversation_id": "string",
  "history": ["string"],
  "message": "string",
  "context_strategy": "full|sliding_window|summarized"
}
```

#### Output
```json
{
  "answer": "string",
  "turn_index": 0,
  "context_tokens_used": 0,
  "context_strategy_applied": "full|sliding_window|summarized"
}
```

## Functional requirements
1. The app must be implemented with FastAPI.
2. Every route must use explicit Pydantic request and response schemas.
3. Every route must call the provider only through the gateway.
4. The app must run locally with a single command.
5. All route behavior must be deterministic enough for bounded testing.
6. The routes must represent three different operational patterns:
   - cheap classification
   - routed answer generation
   - multi-turn context handling
7. Every route must expose a different cost profile that can later be observed in reporting.

## Route behavior requirements

### /classify-complexity
- Must be optimized for short prompts and short structured outputs.
- Must use a fixed classification prompt template.
- Must be designed as the cheapest route in the app.
- Must produce stable enough outputs for bounded tests.

### /answer-routed
- Must represent a routed inference path.
- Must be suitable for demonstrating model-tier selection.
- Must return which model was selected.
- Must return the routing decision explicitly.
- Must be designed so that the same message can be traced through a routing decision and then through an answer generation step.

### /conversation-turn
- Must represent a multi-turn conversation workload.
- Must accept prior history as part of the request.
- Must accept an explicit context strategy.
- Must expose how much context was actually used.
- Must be suitable for demonstrating context window growth and context management strategies.

## Data and fixture rules
- Test fixtures must be stored in-repo.
- Example requests used in docs and tests must be stable and deterministic.
- No dynamic external data source may be required for this spec.
- Conversation fixtures must be short, versioned, and reproducible.

## Telemetry expectations
The reference app itself must not own telemetry logic, but all routes must be compatible with gateway-emitted telemetry.

Each route must pass enough context so the gateway can emit:
- request_id
- route
- model
- latency
- token-related fields
- estimated cost
- status
- routing decision when applicable
- context strategy when applicable
- schema validation outcome

## Acceptance criteria
This spec is complete only if all of the following are true:

1. The app runs locally with one documented command.
2. All three routes are implemented and callable.
3. Every route returns output that conforms to its declared schema.
4. Every route has at least 5 fixed test cases or fixtures.
5. No route makes a direct provider call.
6. Route examples are documented in the README with exact request examples.
7. The app is small enough for manual inspection without hidden framework magic.
8. The three routes expose meaningfully different cost and behavior profiles.

## Required files
At minimum, this spec must result in:
- `app/main.py`
- `app/routes/classify_complexity.py`
- `app/routes/answer_routed.py`
- `app/routes/conversation_turn.py`
- `app/schemas/classify_complexity_response.py`
- `app/schemas/answer_routed_response.py`
- `app/schemas/conversation_turn_response.py`
- `app/services/routing.py`
- `app/services/context_manager.py`

## Explicitly out of scope
- authentication
- user accounts
- database integration
- frontend/UI
- streaming responses
- background queue systems
- multi-provider logic
- advanced prompt management systems
- real production chat infrastructure

## Final constraint
If an implementation choice makes the app more “product-like” but less reproducible, less inspectable, or less useful for demonstrating cost control, reject it.

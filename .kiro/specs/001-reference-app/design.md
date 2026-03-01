# Design: 001 Reference App

## Design overview
This design describes a minimal FastAPI application with three POST routes that demonstrate different LLM cost and context patterns.

The app is intentionally small, locally runnable, and optimized for reproducibility and inspection.

All LLM calls must go through the gateway layer.
No route contains provider-specific logic, cost estimation, telemetry formatting, retry logic, or caching logic.

## Design goals
This design must optimize for:
- reproducibility
- explicit contracts
- low complexity
- route-level cost differentiation
- compatibility with later gateway, eval, and reporting phases

This design must not optimize for:
- future scale
- generalized framework design
- multi-provider support
- user-facing polish
- hidden heuristics

## Component structure

### Route handlers
Each route is a thin FastAPI endpoint that:
1. validates input against an explicit Pydantic request schema
2. calls a service function or the gateway
3. returns output validated against an explicit Pydantic response schema

Route handlers must not contain:
- provider calls
- cost estimation
- telemetry logic
- retry logic
- caching logic
- generalized orchestration

### Service layer
Two small service modules provide route-specific logic:

**`app/services/routing.py`**
- contains the shared routing decision logic
- determines complexity and recommended tier from a message
- is used both by `/classify-complexity` and `/answer-routed`
- does not call the provider directly

**`app/services/context_manager.py`**
- applies context strategy for `/conversation-turn`
- supports: `full`, `sliding_window`, `summarized`
- returns prepared context and context token usage estimate
- does not call the provider directly
- if summarization ever requires an LLM call, that call must also go through the gateway

### Schema layer
Each route must have explicit Pydantic request and response models.

At minimum, the response schema files are:
- `app/schemas/classify_complexity_response.py`
- `app/schemas/answer_routed_response.py`
- `app/schemas/conversation_turn_response.py`

Request contracts must also remain explicit and inspectable.
Do not rely on untyped payloads.

## Route designs

### Route 1: `/classify-complexity`

**Purpose**  
Cheapest route, optimized for short structured output.

**Input**
```json
{ "message": "string" }
```

**Output**
```json
{
  "complexity": "simple|medium|complex",
  "recommended_tier": "cheap|expensive",
  "needs_escalation": false
}
```

**Flow**
1. Receive the input message
2. Use shared routing logic to classify complexity
3. Produce structured output
4. Return schema-valid response

**Operational role**
This route represents a cheap, frequent, low-latency LLM or LLM-like decision task.
It is intended to demonstrate that some requests can be classified into cheaper or more expensive handling paths.

**Design notes**
- use a fixed and reproducible decision strategy
- keep output short and structured
- keep route logic minimal
- route-level behavior must remain inspectable

---

### Route 2: `/answer-routed`

**Purpose**  
Demonstrate routing-based model selection.

**Input**
```json
{ "message": "string" }
```

**Output**
```json
{
  "answer": "string",
  "selected_model": "string",
  "routing_decision": "cheap|expensive"
}
```

**Flow**
1. Receive the input message
2. Use the shared routing logic to determine complexity and recommended tier
3. Call the gateway using the selected tier or selected model path
4. Return answer plus routing metadata

**Operational role**
This route represents a routed inference path whose cost profile changes based on routing decisions.

**Design notes**
- `/answer-routed` must not implement separate routing logic from `/classify-complexity`
- both routes must rely on the same routing decision logic
- the response must expose the routing decision and selected model explicitly
- route behavior must remain reproducible and inspectable

---

### Route 3: `/conversation-turn`

**Purpose**  
Demonstrate multi-turn context handling and token growth.

**Input**
```json
{
  "conversation_id": "string",
  "history": ["string"],
  "message": "string",
  "context_strategy": "full|sliding_window|summarized"
}
```

**Output**
```json
{
  "answer": "string",
  "turn_index": 0,
  "context_tokens_used": 0,
  "context_strategy_applied": "full|sliding_window|summarized"
}
```

**Flow**
1. Receive conversation input
2. Use `context_manager.py` to prepare context according to the requested strategy
3. Call the gateway with the prepared context
4. Return answer plus context metadata

**Operational role**
This route represents a multi-turn conversation workload whose token usage changes with conversation length and context strategy.

**Design notes**
- `full` includes all history
- `sliding_window` keeps only the most recent bounded portion
- `summarized` must remain bounded and reproducible
- if summarization requires an LLM call, it must go through the gateway
- the route must expose how much context was actually used

## Shared routing design

### Routing logic ownership
`app/services/routing.py` is the single shared decision layer for routing behavior in the reference app.

It must:
- classify message complexity
- determine the recommended tier
- produce stable enough outputs for bounded tests

It must not:
- call providers directly
- hide business-critical heuristics in unrelated modules
- become a generalized routing framework

## Context strategy design

### Context logic ownership
`app/services/context_manager.py` owns route-local context preparation for `/conversation-turn`.

It must:
- prepare context from explicit request inputs
- support bounded strategies
- return context metadata needed downstream

It must not:
- persist chat state outside the request
- become a generalized conversation memory system
- call providers directly

## Gateway integration boundary
All LLM calls must go through the gateway.

For this design, it is sufficient to assume:
- each route invokes one concrete gateway call path
- route-specific metadata is passed into that path
- telemetry is emitted by the gateway layer
- cost estimation belongs to the gateway
- retries belong to the gateway
- model resolution belongs to the gateway

This design must not overdefine the internal gateway API, because those details belong to Spec 002.

## File structure
This design maps to the following files:

- `app/main.py`
- `app/routes/classify_complexity.py`
- `app/routes/answer_routed.py`
- `app/routes/conversation_turn.py`
- `app/schemas/classify_complexity_response.py`
- `app/schemas/answer_routed_response.py`
- `app/schemas/conversation_turn_response.py`
- `app/services/routing.py`
- `app/services/context_manager.py`

## Data flow summaries

### `/classify-complexity`
Request → Route Handler → Routing Service → Structured Response

### `/answer-routed`
Request → Route Handler → Routing Service → Gateway → Provider → Structured Response

### `/conversation-turn`
Request → Route Handler → Context Manager → Gateway → Provider → Structured Response

## Configuration
Configuration must remain small and inspectable.

Allowed configuration includes:
- provider API key
- route-to-tier or tier-to-model mapping
- bounded defaults for output size
- bounded defaults for context strategy parameters

Do not introduce heavy configuration systems.

## Error handling
Routes should rely on standard FastAPI validation behavior for malformed input.

Gateway or provider failures should surface as standard route errors while detailed diagnostics remain in structured gateway telemetry.

The design must not hide routing or context behavior behind silent fallbacks unless explicitly allowed by policy.

## Local run model
The app must run locally with a single documented command.

A reviewer must be able to:
1. install dependencies
2. start the app
3. call each route
4. inspect outputs manually

## Documentation expectations
README updates for this phase should include:
- local run command
- one example request per route
- one example response shape per route

## Out of scope for this design
This design must not introduce:
- authentication
- user accounts
- database persistence
- frontend/UI
- streaming
- provider abstraction layers
- multi-provider support
- plugin systems
- advanced prompt management
- background queue systems
- production deployment concerns
- generalized routing frameworks
- persistent chat-memory infrastructure

## Final design rule
If a design choice makes the app more elaborate but less reproducible, less inspectable, or less aligned with the current spec, reject it.

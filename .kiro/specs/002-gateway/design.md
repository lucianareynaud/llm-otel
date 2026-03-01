# Design: 002 Gateway

## Design overview
This design describes a thin, concrete gateway layer that serves as the single architectural choke point for LLM-backed provider calls in the MVP.

The gateway exists to make inference behavior measurable, policy-aware, token-efficient, and reproducible.

It must remain:
- concrete
- local-first
- inspectable
- narrow in scope

The gateway is designed around the real needs of the completed `001-reference-app` phase.

## Design goals
This design must optimize for:
- a single measurable call path for LLM-backed routes
- explicit route-level metadata
- deterministic local cost estimation
- simple route-level policy control
- structured telemetry emission
- compatibility with later eval and reporting phases

This design must not optimize for:
- future providers
- plugin systems
- generalized workflow engines
- generalized routing frameworks
- broad platform abstraction

## Architectural boundary
The gateway is required for all LLM-backed route behavior.

In the current repo state:
- `/answer-routed` must use the gateway
- `/conversation-turn` must use the gateway
- `/classify-complexity` may remain local and deterministic unless explicitly migrated later

This design must not force local deterministic logic into the gateway if no provider call is needed.

## Core gateway responsibilities
The gateway is responsible for:
- provider call execution
- model resolution from a logical tier
- route-aware policy enforcement
- structured telemetry emission
- deterministic cost estimation
- optional cache behavior if enabled
- returning a structured result to route handlers

The gateway is not responsible for:
- route business logic
- generalized orchestration
- persistent conversation memory
- generalized routing decisions beyond what current routes require

## Required components

### `gateway/client.py`
Owns the concrete provider call path and public gateway entry point.

This module must expose one concrete callable entry point for LLM-backed requests.

### `gateway/telemetry.py`
Owns telemetry event creation and JSON-lines emission.

### `gateway/policies.py`
Owns route-level policy lookup and bounded policy enforcement.

### `gateway/cache.py`
Owns minimal local cache behavior if caching is enabled.
Cache behavior must remain optional and simple.

### `gateway/cost_model.py`
Owns deterministic cost estimation from local pricing configuration.

## Public gateway contract

### Input shape
The gateway public entry point must accept enough information to execute and measure a route-level LLM call.

At minimum, it must accept:
- prepared prompt or context
- logical model tier
- route name
- route-specific metadata

### Output shape
The gateway must return a structured result object, not a raw string.

The result must contain at minimum:
- `text`
- `selected_model`
- `request_id`
- `tokens_in`
- `tokens_out`
- `estimated_cost_usd`
- `cache_hit`

Additional fields may be included only if required by current routes or telemetry needs.

## Route policy design

### Policy ownership
`gateway/policies.py` owns route-level policy definitions.

Policies must remain explicit and inspectable.

### Route policy contents
Each route policy may define:
- `max_output_tokens`
- `retry_attempts`
- `cache_enabled`
- allowed logical tier or tier behavior
- bounded context budget if relevant

### Current route expectations
For the current MVP:
- `/answer-routed` needs route-level model tier handling and routing metadata
- `/conversation-turn` needs route-level context-budget-related metadata
- `/classify-complexity` does not need gateway policy unless later migrated behind the gateway

## Model resolution design

### Logical tier model
The gateway should resolve actual model names from logical tiers.

Tier-to-model mapping must be:
- local
- inspectable
- simple
- current-provider-only

Do not encode speculative multi-provider behavior.

## Cost model design

### Ownership
`gateway/cost_model.py` owns deterministic request cost estimation.

### Inputs
Cost estimation must use:
- selected model
- tokens_in
- tokens_out
- local pricing configuration

### Constraints
Pricing configuration must remain:
- local
- inspectable
- deterministic

Do not fetch pricing dynamically in the MVP.

## Telemetry design

### Emission model
Telemetry must be emitted from the gateway path only.

Telemetry must be written as JSON lines to a local artifact path.

Do not mix prose logging with structured telemetry events.

### Event requirements
Each event must contain:
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

When applicable, it must also support:
- `selected_model`
- `routing_decision`
- `routing_reason`
- `context_strategy`
- `context_tokens_used`
- `conversation_id`
- `turn_index`
- `prompt_version`

### Emission style
Telemetry writing must stay simple.
Prefer direct append-based JSON-lines writing over lifecycle-heavy logging systems.

## Cache design

### Role
Caching is optional in this phase.
The gateway must support a minimal local cache only if currently enabled by route policy.

### Constraints
The cache must remain:
- local
- deterministic
- inspectable
- easy to disable

Do not introduce distributed caching, TTL management frameworks, or advanced invalidation logic.

### Current MVP stance
Cache capability may exist, but current route usage should remain conservative.
Do not force cache behavior where it is not yet justified by the completed reference app.

## Error handling design
Gateway failures must be explicit and inspectable.

The gateway must:
- return or raise clear failures
- emit stable `error_type` values in telemetry
- avoid silent fallbacks unless explicitly required by policy

The design must not hide routing or context behavior changes behind implicit failure recovery.

## File structure
This design maps to the following files:

- `gateway/client.py`
- `gateway/telemetry.py`
- `gateway/policies.py`
- `gateway/cache.py`
- `gateway/cost_model.py`

## Data flow summaries

### `/answer-routed`
Route Handler → Shared Routing Logic → Gateway → Provider Stub/Provider → Structured Gateway Result → Route Response

### `/conversation-turn`
Route Handler → Context Manager → Gateway → Provider Stub/Provider → Structured Gateway Result → Route Response

### `/classify-complexity`
Route Handler → Local Routing Logic → Structured Route Response

## Configuration
Gateway configuration must remain small and inspectable.

Allowed configuration includes:
- provider API key
- tier-to-model mapping
- local pricing table
- route policy values
- telemetry output path

Do not introduce heavy configuration systems.

## Testing expectations
The gateway design must support deterministic tests for:
- successful call path
- error path
- route-level policy lookup
- deterministic cost estimation
- optional cache hit/miss behavior
- telemetry emission shape
- structured gateway result contents

## Out of scope for this design
This design must not introduce:
- multi-provider support
- provider abstraction hierarchies
- plugin systems
- generalized routing frameworks
- generalized memory systems
- workflow engines
- advanced rate limiting
- dashboard UI
- queue systems
- dynamic pricing fetches

## Final design rule
If a gateway design choice makes the system more extensible but less concrete, less readable, less testable, or less aligned with the completed reference app, reject it.

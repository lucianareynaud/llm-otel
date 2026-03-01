# Architecture Steering

## Core principle
Every LLM provider call passes through a single choke point: `gateway/client.py`.
No route handler, middleware, service, or eval runner may call the OpenAI API directly.
This is the non-negotiable architectural invariant of this project.

---

## Full system architecture

```
HTTP Request
  │
  ▼
[APIKeyMiddleware]         app/middleware/auth.py
  │  → 401 on missing/invalid X-API-Key header
  ▼
[RateLimitMiddleware]      app/middleware/rate_limit.py
  │  → 429 on per-key sliding window overflow
  ▼
[FastAPIInstrumentor]      OTel SERVER span for HTTP request
  │
  ▼
Route Handler (async)      app/routes/
  │
  ├── /classify-complexity → determine_complexity()   (no LLM call)
  │
  ├── /answer-routed       → determine_complexity()
  │                           → await call_llm()
  │
  └── /conversation-turn   → ConversationStore.get()
                             → prepare_context()      (tiktoken)
                             → await call_llm()
                             → ConversationStore.append()
                                   │
                                   ▼
                             [gateway/client.py]       OTel CLIENT span
                                   │
                                   ├── RoutePolicy lookup
                                   ├── SemanticCache.get()    → return cached if HIT
                                   ├── CircuitBreaker.check() → 503 if OPEN
                                   ├── await _call_provider() → AsyncOpenAI
                                   │         └── await asyncio.sleep() on retry
                                   ├── estimate_cost()
                                   ├── SemanticCache.put()
                                   └── emit()                 → OTel metrics + JSONL
```

---

## Layer responsibilities

### app/middleware/
Authentication and rate limiting. These are the outermost layers — they run before any
route handler, service, or gateway logic. **No business logic here.**

- `auth.py` — `APIKeyMiddleware`: checks `X-API-Key` header against `APP_API_KEY` env var.
  Exempts `/healthz` and `/readyz`. Returns 401 on failure.
- `rate_limit.py` — `RateLimitMiddleware`: per-key sliding window counter using
  `collections.deque`. Returns 429 with `Retry-After` on overflow.

Middleware registration order (in `app/main.py`): auth is outermost (runs first), rate
limit is inner (runs second). This means rejected auth requests never count against the
rate limit.

### app/routes/
Thin route handlers. Each handler:
1. Validates input (Pydantic does this automatically)
2. Calls a service or the gateway
3. Returns a schema-compliant response

**Route handlers must not**: implement caching, calculate cost, apply retry logic, format
telemetry, check circuit state, or contain any business logic that belongs in services or
the gateway.

### app/routes/health.py
Infrastructure-only endpoints. Not business routes.
- `GET /healthz` — always 200. Never fails.
- `GET /readyz` — 200 when `_ready=True` (set by lifespan), 503 otherwise.

These endpoints are exempt from auth middleware and OTel instrumentation.

### app/services/
Domain logic that is not gateway-specific.

- `routing.py` — `determine_complexity()`: returns `(Complexity, Tier, bool)`. Uses
  embedding-based kNN (primary) or keyword heuristic (fallback). Signature is frozen.
- `context_manager.py` — `prepare_context()`: assembles conversation context using the
  chosen strategy (`full`, `sliding_window`, `summarized`). Uses tiktoken for token counts.
  Raises `ContextTooLargeError` when assembled context exceeds `MAX_CONTEXT_TOKENS`.
- `token_counter.py` — `count_tokens(text, model)`: wraps tiktoken with model-specific
  encoding and `cl100k_base` fallback. lru_cache per model encoder.
- `conversation_store.py` — `ConversationStore` protocol + `InMemoryConversationStore` +
  `RedisConversationStore`. Retrieved via `Depends(get_conversation_store)` in routes.

### gateway/
The choke point. Everything that touches the provider or measures it lives here.

- `client.py` — `async def call_llm()`: the only path to the provider. Implements:
  OTel CLIENT span, cache check, circuit check, async retry with exponential backoff,
  cost estimation, telemetry emission.
- `cache.py` — `SemanticCache`: exact (sha256 key) and semantic (cosine similarity)
  cache layers. Module-level singleton with public `cache_get/cache_put/cache_clear/cache_stats`.
- `circuit_breaker.py` — `CircuitBreaker`: three-state machine (closed/open/half-open).
  Thread-safe with `threading.Lock`. Module-level singleton with public functions.
- `cost_model.py` — `MODEL_PRICING` dict + `estimate_cost()`. Hardcoded snapshot pricing.
  **Must include a source URL comment and retrieval date.**
- `policies.py` — `RoutePolicy` frozen dataclass + `_ROUTE_POLICIES` dict.
  Contains model-for-tier mapping and cache_enabled flag per route.
- `telemetry.py` — `emit()`: dual-write to OTel metrics and JSONL file. JSONL format
  is frozen — existing fields must not change. New optional fields are allowed.
- `otel_setup.py` — `setup_otel()` / `shutdown_otel()`: global TracerProvider +
  MeterProvider configuration. Called from lifespan in `app/main.py`.

---

## Hard architectural rules

These rules may not be overridden by any spec task:

1. **No direct OpenAI calls outside `gateway/client.py`.**
   Exception: `openai.embeddings.create()` in `gateway/cache.py` (semantic cache) and
   `app/services/routing.py` (anchor embeddings) — these are lightweight read-only calls
   that must not go through `call_llm` to avoid recursive cost tracking.

2. **No route handler contains auth, rate-limit, caching, retry, or circuit-breaker logic.**
   These belong in middleware or the gateway exclusively.

3. **The cache lives in `gateway/cache.py` only.** Routes may not import from `gateway.cache`.

4. **The circuit breaker lives in `gateway/circuit_breaker.py` only.** Routes may not
   import from `gateway.circuit_breaker`.

5. **Authentication is enforced at middleware layer only.** No `Depends()` auth guards in
   route handlers.

6. **tiktoken is imported only in `app/services/token_counter.py`.** Never in routes,
   gateway, or other services.

7. **The `ConversationStore` abstraction uses `typing.Protocol` only.** No ABC, no registry,
   no factory pattern.

8. **`gateway/client.py` is the sole source of telemetry emission.** Route handlers must not
   call `emit()` directly.

9. **The JSONL telemetry format is frozen.** Existing field names and types must not change.
   New optional fields may be added.

10. **The three route paths are frozen.** `/classify-complexity`, `/answer-routed`,
    `/conversation-turn` — their URLs and schemas may not change.

---

## Dependency rules between layers

```
routes     → services, gateway/client (await call_llm)
services   → token_counter, openai.embeddings (routing only)
gateway    → openai (AsyncOpenAI), telemetry, cost_model, policies, cache, circuit_breaker
middleware → fastapi internals only
```

Reverse dependencies (e.g., gateway importing from routes) are forbidden.

---

## Configuration architecture
All configuration is environment-variable driven. No config files, no `.env` loading in
application code (`.env` is loaded externally by the developer).

Required env vars (app refuses to start without these):
- `OPENAI_API_KEY` — provider auth
- `APP_API_KEY` — API consumer auth (raises `ValueError` if absent)

Optional env vars (all have safe defaults):
- `RATE_LIMIT_RPM=60`
- `MAX_CONTEXT_TOKENS=8192`
- `SEMANTIC_CACHE_ENABLED=false`
- `SEMANTIC_CACHE_THRESHOLD=0.97`
- `CIRCUIT_BREAKER_FAILURE_THRESHOLD=5`
- `CIRCUIT_BREAKER_RESET_TIMEOUT_S=30`
- `CONVERSATION_TTL_SECONDS=3600`
- `REDIS_URL` — enables Redis conversation backend
- `ROUTING_USE_EMBEDDINGS=true`
- `OTEL_EXPORTER_OTLP_ENDPOINT` — OTLP collector endpoint
- `OTEL_SDK_DISABLED=false` — set `true` in CI to suppress OTel startup

---

## What must NOT be added

These are permanently out of scope:
- Multi-provider abstraction (`BaseProvider`, provider registry)
- Streaming responses
- Tool/function calling
- Background task queues
- Plugin systems
- Agent orchestration
- Fine-tuning pipeline
- Dashboard or UI
- OAuth / user management
- Database migrations framework
- Distributed rate limiting (comment documenting the upgrade path is sufficient)

---

## Simplicity rule
When two designs solve the same problem, prefer the one with:
- fewer files
- fewer moving parts
- easier local inspection
- no speculative extensibility

A design that is "flexible for future needs" but harder to read today is the wrong design.

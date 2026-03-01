# Spec: 010 Semantic Cache

## Goal
Implement `gateway/cache.py` so that exact and near-identical repeated prompts are served
from an in-memory cache without calling the provider. This is the highest-impact cost
reduction lever for production LLM deployments.

## Prerequisite gate
Spec 009 must be complete before starting:

```bash
OTEL_SDK_DISABLED=true pytest tests/ -v  # ≥ 151 tests, all passing
grep "CHARS_PER_TOKEN" .                  # must return zero matches
```

Both must pass before any task in this spec begins.

## What this spec adds
- `gateway/cache.py` — full cache implementation (currently empty)
- `tests/test_cache.py` — cache unit tests

## What this spec changes
- `gateway/client.py` — cache check before provider call, cache write after successful call
- `gateway/policies.py` — `cache_enabled=True` on `/answer-routed` (opt-in per route)

## What this spec does NOT change
Routes, schemas, middleware, auth, tiktoken integration, OTel setup, and telemetry JSONL
format are frozen. The JSONL telemetry format gains only two new optional fields:
`cache_hit: bool` and enriches existing records — it does not break existing consumers.

## Problem
`gateway/cache.py` is empty. Every identical prompt sent to `/answer-routed` calls the
provider and incurs full token billing. In any real deployment, a significant fraction of
requests are repeated questions, FAQ responses, or near-identical reformulations of the same
query. The cache was scaffolded but never implemented.

## Acceptance criteria
1. A second identical prompt to `/answer-routed` (when `cache_enabled=True`) returns the
   cached response without calling `_call_provider`.
2. `cache_hit=True` appears in the telemetry JSONL event for a cache hit.
3. `tokens_in=0`, `tokens_out=0`, `estimated_cost_usd=0.0` for a cache hit.
4. Different models produce different cache keys (no cross-model collision).
5. `cache_clear()` resets the store and all counters.
6. `cache_stats()` returns a `CacheStats` frozen dataclass with `hits`, `misses`, and `size`.
7. When `cache_enabled=False` in the route policy, the cache is bypassed entirely.
8. `OTEL_SDK_DISABLED=true pytest tests/ -v` — all tests pass.

## Testing requirements
- `tests/test_cache.py`: exact hit, cache miss, stats counters, clear, cross-model isolation,
  cache bypass when disabled in policy, semantic hit with mocked embedding function.
- No new test for `_call_provider` internals — only the public cache interface is tested.
- The semantic cache embedding call is mocked — tests do not require a real OpenAI key.

## Hard rules
- The cache lives entirely in `gateway/cache.py`. Routes must never import from it directly.
- The cache is checked and written only inside `gateway/client.py`.
- The semantic embedding call uses `openai.embeddings.create()` directly — not via `call_llm`
  (that would be recursive cost tracking).
- Cache is disabled by default (`cache_enabled=False`) on all routes. Only opt-in per policy.
- `CacheStats` is a frozen dataclass — not a mutable dict.
- The in-memory store has no TTL and no persistence across restarts. A comment must document
  the Redis upgrade path.
- `SEMANTIC_CACHE_ENABLED` env var (default `false`) controls whether the cosine-similarity
  layer is active. The exact cache layer is always active when `cache_enabled=True`.

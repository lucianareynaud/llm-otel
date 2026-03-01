# Tasks: 010 Semantic Cache

## Prerequisite gate
Run before starting any task:

```bash
OTEL_SDK_DISABLED=true pytest tests/ -v  # ≥ 205 tests, all passing
grep "CHARS_PER_TOKEN" .                  # must return zero matches
```

Both must pass before proceeding.

---

## Task 1 — Implement gateway/cache.py

- [ ] 1.1 Open `gateway/cache.py` (currently empty)
- [ ] 1.2 Add imports: `import dataclasses, hashlib, os`
- [ ] 1.3 Define `CacheStats` frozen dataclass: `hits: int`, `misses: int`, `size: int`
- [ ] 1.4 Define `CacheEntry` frozen dataclass: `response: str`, `embedding: list[float] | None`
- [ ] 1.5 Implement `_make_key(prompt: str, model: str) -> str`:
  - `hashlib.sha256(f"{model}:{prompt}".encode()).hexdigest()`
- [ ] 1.6 Implement `_cosine_similarity(a: list[float], b: list[float]) -> float`:
  - Pure Python — no numpy
  - Handle zero-norm vectors by returning `0.0`
- [ ] 1.7 Implement `class SemanticCache`:
  - `__init__`: initialise `_store`, `_hits`, `_misses`; add Redis upgrade path comment
  - `get(prompt, model) -> str | None`: exact lookup first; if miss and `SEMANTIC_CACHE_ENABLED=true`, try `_semantic_lookup`; update hit/miss counters
  - `put(prompt, model, response) -> None`: store `CacheEntry`; if `SEMANTIC_CACHE_ENABLED=true`, also call `_embed` and store embedding
  - `_semantic_lookup(prompt, model) -> str | None`: embed query, scan candidates, return best match above threshold or `None`
  - `_embed(text) -> list[float]`: direct `openai.embeddings.create(model="text-embedding-3-small", input=text)` call with comment explaining why it bypasses `call_llm`
  - `invalidate(prompt, model) -> None`: remove key if present
  - `clear() -> None`: empty `_store`, reset counters
  - `stats() -> CacheStats`: return frozen dataclass
- [ ] 1.8 Add module-level singleton: `_cache = SemanticCache()`
- [ ] 1.9 Add public module-level functions: `cache_get`, `cache_put`, `cache_invalidate`, `cache_clear`, `cache_stats` — each delegates to `_cache`
- [ ] 1.10 `ruff check gateway/cache.py` — zero errors
- [ ] 1.11 `mypy gateway/cache.py --ignore-missing-imports` — zero errors

**Acceptance**: Module imports. `cache_get` and `cache_put` are callable. `CacheStats` is a frozen dataclass.

---

## Task 2 — Add cache_hit to GatewayResult

- [ ] 2.1 Open `gateway/client.py` (or wherever `GatewayResult` is defined)
- [ ] 2.2 Add `cache_hit: bool = False` field to `GatewayResult`
- [ ] 2.3 Verify existing `GatewayResult(...)` constructions still work (field has a default)

**Acceptance**: `GatewayResult(text="x", ..., cache_hit=True)` and `GatewayResult(text="x", ...)` both work.

---

## Task 3 — Integrate cache into gateway/client.py

- [ ] 3.1 Import: `from gateway.cache import cache_get, cache_put`
- [ ] 3.2 After resolving `selected_model` and before opening the OTel span, add the cache-hit fast path:
  ```python
  if policy.cache_enabled:
      cached = cache_get(prompt, selected_model)
      if cached is not None:
          emit(..., cache_hit=True)
          return GatewayResult(..., tokens_in=0, tokens_out=0, estimated_cost_usd=0.0, cache_hit=True)
  ```
- [ ] 3.3 After a successful provider call, add the cache-write:
  ```python
  if policy.cache_enabled:
      cache_put(prompt, selected_model, text)
  ```
- [ ] 3.4 `ruff check gateway/client.py` — zero errors

**Acceptance**: Cache hit returns without calling `_call_provider`. Cache write happens after a successful provider call.

---

## Task 4 — Add cache_hit to telemetry emit()

- [ ] 4.1 Open `gateway/telemetry.py`
- [ ] 4.2 Add `cache_hit: bool = False` parameter to `emit()`
- [ ] 4.3 Include `"cache_hit": cache_hit` in the JSONL record dict
- [ ] 4.4 Verify existing `emit(...)` calls still work (parameter has a default)

**Acceptance**: `emit(...)` without `cache_hit` works unchanged. `cache_hit=True` appears in the JSONL record.

---

## Task 5 — Update gateway/policies.py

- [ ] 5.1 Open `gateway/policies.py`
- [ ] 5.2 Set `cache_enabled=True` on the `/answer-routed` policy
- [ ] 5.3 Keep `cache_enabled=False` on `/conversation-turn`

**Acceptance**: `/answer-routed` has `cache_enabled=True`. `/conversation-turn` has `cache_enabled=False`.

---

## Task 6 — Create tests/test_cache.py

- [ ] 6.1 Create `tests/test_cache.py`
- [ ] 6.2 Call `cache_clear()` in a `setup_function` or `autouse` fixture to reset state between tests
- [ ] 6.3 Write:
  - `test_exact_hit`: `cache_put("p", "gpt-4o-mini", "r")` then `cache_get("p", "gpt-4o-mini")` → `"r"`
  - `test_cache_miss`: `cache_get("unknown", "gpt-4o-mini")` → `None`
  - `test_stats_hit_counter`: put one entry, get it twice, check `cache_stats().hits == 2`
  - `test_stats_miss_counter`: get a non-existent key, check `cache_stats().misses == 1`
  - `test_cache_clear`: put entry, `cache_clear()`, `cache_stats().size == 0`
  - `test_cross_model_isolation`: `cache_put("p", "gpt-4o-mini", "r1")` and `cache_put("p", "gpt-4o", "r2")`;
    verify `cache_get("p", "gpt-4o-mini") == "r1"` and `cache_get("p", "gpt-4o") == "r2"`
  - `test_cache_disabled_bypassed`: with `cache_enabled=False` in the policy, verify that
    `_call_provider` is still called even after caching a result (mock `_call_provider` with `AsyncMock`,
    call `call_llm` twice, assert `_call_provider` was called twice)
  - `test_semantic_hit_mocked`: use `monkeypatch` to replace `_cache._embed` with a function that
    returns a fixed vector; put an entry with `SEMANTIC_CACHE_ENABLED=true`; call `cache_get` with a
    different but "similar" prompt (inject matching similarity via mock); verify it returns the cached response
- [ ] 6.4 Run: `OTEL_SDK_DISABLED=true pytest tests/test_cache.py -v` — all 8 tests pass

**Acceptance**: All 8 cache tests pass. No real OpenAI API key required.

---

## Task 7 — Full verification

- [ ] 7.1 `OTEL_SDK_DISABLED=true pytest tests/ -v` — all tests pass, ≥ 213 tests
- [ ] 7.2 `ruff check gateway/cache.py gateway/client.py gateway/telemetry.py` — zero errors
- [ ] 7.3 Verify JSONL telemetry: after a cache hit, `artifacts/logs/telemetry.jsonl` contains a record
  with `"cache_hit": true` and `"estimated_cost_usd": 0.0`

**Acceptance**: Full test suite green. JSONL format is backward compatible (new optional field).

---

## Completion criteria
This spec is complete when:
- `gateway/cache.py` is fully implemented (not empty)
- A second identical prompt to `/answer-routed` does not call `_call_provider`
- `cache_hit=True` and `estimated_cost_usd=0.0` appear in telemetry for cache hits
- `OTEL_SDK_DISABLED=true pytest tests/ -v` reports ≥ 213 tests, all passing
- No route handler imports from `gateway.cache` directly

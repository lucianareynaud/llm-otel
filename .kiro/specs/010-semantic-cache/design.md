# Design: 010 Semantic Cache

---

## gateway/cache.py structure

### Data classes

```python
@dataclasses.dataclass(frozen=True)
class CacheStats:
    hits: int
    misses: int
    size: int

@dataclasses.dataclass(frozen=True)
class CacheEntry:
    response: str
    embedding: list[float] | None  # None when SEMANTIC_CACHE_ENABLED=false
```

### SemanticCache class

```python
class SemanticCache:
    def __init__(self) -> None:
        self._store: dict[str, CacheEntry] = {}
        self._hits = 0
        self._misses = 0
        # For distributed deployments, replace _store with Redis HSET/HGET
        # and counters with Redis INCR on shared keys.

    def get(self, prompt: str, model: str) -> str | None: ...
    def put(self, prompt: str, model: str, response: str) -> None: ...
    def invalidate(self, prompt: str, model: str) -> None: ...
    def clear(self) -> None: ...
    def stats(self) -> CacheStats: ...
```

### Cache key construction

```python
import hashlib

def _make_key(prompt: str, model: str) -> str:
    return hashlib.sha256(f"{model}:{prompt}".encode()).hexdigest()
```

Including the model in the key prevents cross-model collisions: the same prompt sent to
`gpt-4o-mini` and `gpt-4o` must produce different cache keys because the responses can differ.

### get() logic

```python
def get(self, prompt: str, model: str) -> str | None:
    key = _make_key(prompt, model)
    if key in self._store:
        self._hits += 1
        return self._store[key].response

    if os.environ.get("SEMANTIC_CACHE_ENABLED", "false").lower() == "true":
        hit = self._semantic_lookup(prompt, model)
        if hit is not None:
            self._hits += 1
            return hit

    self._misses += 1
    return None
```

### Semantic lookup

```python
def _semantic_lookup(self, prompt: str, model: str) -> str | None:
    # Only entries with stored embeddings are candidates
    candidates = [(k, e) for k, e in self._store.items() if e.embedding is not None]
    if not candidates:
        return None
    query_embedding = self._embed(prompt)
    threshold = float(os.environ.get("SEMANTIC_CACHE_THRESHOLD", "0.97"))
    best_score = -1.0
    best_response: str | None = None
    for _, entry in candidates:
        score = _cosine_similarity(query_embedding, entry.embedding)  # type: ignore[arg-type]
        if score > best_score:
            best_score = score
            best_response = entry.response
    return best_response if best_score >= threshold else None

def _embed(self, text: str) -> list[float]:
    # Direct openai call — not via call_llm to avoid circular cost tracking
    import openai
    result = openai.embeddings.create(model="text-embedding-3-small", input=text)
    return result.data[0].embedding
```

### Cosine similarity (pure Python, no numpy)

```python
def _cosine_similarity(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = sum(x * x for x in a) ** 0.5
    norm_b = sum(x * x for x in b) ** 0.5
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)
```

### Module-level singleton and public functions

```python
_cache = SemanticCache()

def cache_get(prompt: str, model: str) -> str | None:
    return _cache.get(prompt, model)

def cache_put(prompt: str, model: str, response: str) -> None:
    _cache.put(prompt, model, response)

def cache_invalidate(prompt: str, model: str) -> None:
    _cache.invalidate(prompt, model)

def cache_clear() -> None:
    _cache.clear()

def cache_stats() -> CacheStats:
    return _cache.stats()
```

---

## gateway/client.py integration

### Cache check (before provider call)

```python
from gateway.cache import cache_get, cache_put

# After resolving selected_model, before opening the OTel span:
if policy.cache_enabled:
    cached = cache_get(prompt, selected_model)
    if cached is not None:
        emit(
            route=route,
            model=selected_model,
            tokens_in=0,
            tokens_out=0,
            latency_ms=0.0,
            estimated_cost_usd=0.0,
            status="success",
            cache_hit=True,
        )
        return GatewayResult(
            text=cached,
            selected_model=selected_model,
            tokens_in=0,
            tokens_out=0,
            latency_ms=0.0,
            estimated_cost_usd=0.0,
            cache_hit=True,
        )
```

### Cache write (after successful provider call)

```python
if policy.cache_enabled:
    cache_put(prompt, selected_model, text)
```

### GatewayResult update

Add `cache_hit: bool = False` field to the `GatewayResult` dataclass.

---

## gateway/policies.py update

Enable cache on `/answer-routed` only:

```python
"/answer-routed": RoutePolicy(
    ...
    cache_enabled=True,
),
"/conversation-turn": RoutePolicy(
    ...
    cache_enabled=False,  # conversation context changes per turn; caching is not useful
),
```

---

## Telemetry update

`gateway/telemetry.py` `emit()` function gains `cache_hit: bool = False` parameter.
It is included in the JSONL record. Existing consumers that do not read this field are unaffected.

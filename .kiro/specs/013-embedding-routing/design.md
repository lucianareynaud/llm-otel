# Design: 013 Embedding-Based Routing Classifier

---

## Architecture

The existing `determine_complexity()` becomes a dispatcher:

```
determine_complexity(message)
  │
  ├── if ROUTING_USE_EMBEDDINGS=true
  │     └── _classify_with_embeddings(message)
  │           ├── _get_anchor_embeddings()   (lazy, cached)
  │           ├── embed message              (openai.embeddings.create)
  │           └── _knn_classify(embedding)
  │
  └── (fallback or ROUTING_USE_EMBEDDINGS=false)
        └── keyword + length heuristic      (existing logic, preserved)
```

---

## Anchor set

A module-level constant `ROUTING_ANCHORS` holds labelled example strings per complexity class.
These are inspectable, versioned with the code, and easy to extend without retraining.

```python
ROUTING_ANCHORS: dict[str, list[str]] = {
    "simple": [
        "What is 2+2?",
        "What is the capital of France?",
        "What time is it in Tokyo?",
        "Who wrote Hamlet?",
        "What does HTTP stand for?",
        "Convert 100 USD to EUR",
        "What is the boiling point of water?",
        "Spell 'necessary'",
        "What language is spoken in Brazil?",
        "What year did World War II end?",
    ],
    "medium": [
        "Explain how HTTP caching works",
        "What are the main differences between REST and GraphQL?",
        "Summarize the plot of 1984 by George Orwell",
        "How does a neural network learn?",
        "What are the pros and cons of microservices?",
        "Explain the CAP theorem in simple terms",
        "How does garbage collection work in Python?",
        "What is the difference between TCP and UDP?",
        "Describe the agile development methodology",
        "What is Docker and why is it used?",
    ],
    "complex": [
        "Analyze the tradeoffs between eventual consistency and strong consistency in distributed databases",
        "Design a rate-limiting system that works across multiple data centers",
        "Write a detailed comparison of transformer architecture variants for code generation",
        "Explain the implications of Gödel's incompleteness theorems for AI alignment",
        "Critique the design of the Unix filesystem and propose improvements",
        "Analyze the economic and social impact of large language models on the labour market",
        "Compare Byzantine fault tolerance protocols and their suitability for blockchain consensus",
        "Design a schema for a multi-tenant SaaS application with row-level security",
        "Explain how attention mechanisms in transformers relate to memory and retrieval",
        "Analyze the correctness proof of Lamport's mutual exclusion algorithm",
    ],
}
```

---

## Lazy anchor embedding cache

```python
_anchor_embeddings: dict[str, list[list[float]]] | None = None

def _get_anchor_embeddings() -> dict[str, list[list[float]]]:
    global _anchor_embeddings
    if _anchor_embeddings is not None:
        return _anchor_embeddings
    result: dict[str, list[list[float]]] = {}
    for complexity, examples in ROUTING_ANCHORS.items():
        response = openai.embeddings.create(
            model="text-embedding-3-small",
            input=examples,
        )
        result[complexity] = [item.embedding for item in response.data]
    _anchor_embeddings = result
    return _anchor_embeddings
```

Computed once on first call, then returned from the module-level cache on all subsequent calls.
Not computed at module import — this prevents startup delays and import-time API calls in tests.

---

## Cosine similarity (pure Python)

```python
def _cosine_similarity(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = sum(x * x for x in a) ** 0.5
    norm_b = sum(x * x for x in b) ** 0.5
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot / (norm_a * norm_b)
```

---

## kNN classifier

```python
def _knn_classify(
    message_embedding: list[float],
    anchors: dict[str, list[list[float]]],
    k: int = 3,
) -> str:
    scored: list[tuple[float, str]] = []
    for complexity, embeddings in anchors.items():
        for emb in embeddings:
            score = _cosine_similarity(message_embedding, emb)
            scored.append((score, complexity))
    scored.sort(key=lambda x: x[0], reverse=True)
    top_k = [label for _, label in scored[:k]]
    # Majority vote
    return max(set(top_k), key=top_k.count)
```

---

## determine_complexity dispatcher

```python
def determine_complexity(message: str) -> tuple[Complexity, Tier, bool]:
    use_embeddings = os.environ.get("ROUTING_USE_EMBEDDINGS", "true").lower() == "true"
    if use_embeddings:
        try:
            return _classify_with_embeddings(message)
        except Exception:
            import logging
            logging.getLogger(__name__).warning(
                "Embedding classifier failed; falling back to keyword classifier"
            )
    return _classify_with_keywords(message)
```

`_classify_with_keywords` is the existing keyword + length logic, extracted into a private
function. `_classify_with_embeddings` embeds the message, calls `_knn_classify`, then maps
the result to the `(Complexity, Tier, bool)` return type.

---

## Complexity → Tier → needs_escalation mapping

```python
_TIER_MAP: dict[str, tuple[Complexity, Tier, bool]] = {
    "simple":  ("simple",  "cheap",     False),
    "medium":  ("medium",  "cheap",     False),
    "complex": ("complex", "expensive", True),
}
```

---

## scripts/verify_routing.py

A standalone script (not part of pytest) that:
1. Calls `determine_complexity()` with 20 labelled test messages
2. Prints each result
3. Counts correct classifications
4. Exits 0 if accuracy ≥ 90%, exits 1 otherwise

Requires `OPENAI_API_KEY` to be set. This script is run manually before merging spec 013
and the pass rate is recorded as a comment at the top of `routing.py`.

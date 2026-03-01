# Tasks: 013 Embedding-Based Routing Classifier

## Prerequisite gate
Run before starting any task:

```bash
OTEL_SDK_DISABLED=true pytest tests/ -v  # ≥ 230 tests, all passing
```

If any test fails, fix it before proceeding.

---

## Task 1 — Refactor app/services/routing.py

- [ ] 1.1 Open `app/services/routing.py`
- [ ] 1.2 Extract the existing keyword + length logic into a private function
  `_classify_with_keywords(message: str) -> tuple[Complexity, Tier, bool]`
  - Move all existing logic from `determine_complexity` into this function
  - Keep `COMPLEX_KEYWORDS`, `SIMPLE_KEYWORDS`, `SIMPLE_LENGTH_THRESHOLD`, and any other
    existing constants — they are now the fallback implementation
- [ ] 1.3 Add `import os, logging` at the top of the file
- [ ] 1.4 Run: `OTEL_SDK_DISABLED=true pytest tests/ -v` — all existing routing tests pass
  (no logic changed yet, only renamed to private function)

**Acceptance**: `_classify_with_keywords` exists. `determine_complexity` still works. Zero regressions.

---

## Task 2 — Add anchor set and helpers

- [ ] 2.1 Add the `ROUTING_ANCHORS` constant (10 examples per class: `simple`, `medium`, `complex`)
  as shown in the design
- [ ] 2.2 Add `_anchor_embeddings: dict[str, list[list[float]]] | None = None` module-level variable
- [ ] 2.3 Implement `_cosine_similarity(a: list[float], b: list[float]) -> float`:
  - Pure Python — no numpy
  - Returns `0.0` when either vector has zero norm
- [ ] 2.4 Implement `_knn_classify(message_embedding, anchors, k=3) -> str`:
  - Score all anchor embeddings with `_cosine_similarity`
  - Sort descending by score
  - Return majority class of top-k
- [ ] 2.5 Implement `_get_anchor_embeddings() -> dict[str, list[list[float]]]`:
  - Global check: if `_anchor_embeddings is not None`, return cached value immediately
  - Otherwise: call `openai.embeddings.create(model="text-embedding-3-small", input=examples)`
    for each complexity class; store result in module-level variable; return it
- [ ] 2.6 Add `_TIER_MAP` mapping `"simple"` → `("simple", "cheap", False)`, etc.
- [ ] 2.7 Implement `_classify_with_embeddings(message: str) -> tuple[Complexity, Tier, bool]`:
  - Call `_get_anchor_embeddings()`
  - Embed the message: `openai.embeddings.create(model="text-embedding-3-small", input=message)`
  - Call `_knn_classify(embedding, anchors)`
  - Return `_TIER_MAP[result]`
- [ ] 2.8 `ruff check app/services/routing.py` — zero errors

**Acceptance**: All helper functions are defined. Module imports without calling OpenAI (lazy).

---

## Task 3 — Update determine_complexity dispatcher

- [ ] 3.1 Replace the body of `determine_complexity(message: str) -> tuple[Complexity, Tier, bool]` with:
  ```python
  use_embeddings = os.environ.get("ROUTING_USE_EMBEDDINGS", "true").lower() == "true"
  if use_embeddings:
      try:
          return _classify_with_embeddings(message)
      except Exception:
          logging.getLogger(__name__).warning(
              "Embedding classifier failed; falling back to keyword classifier"
          )
  return _classify_with_keywords(message)
  ```
- [ ] 3.2 `ruff check app/services/routing.py` — zero errors
- [ ] 3.3 `mypy app/services/routing.py --ignore-missing-imports` — zero errors

**Acceptance**: `determine_complexity` is a dispatcher. Fallback is silent. Signature is unchanged.

---

## Task 4 — Add tests to tests/test_services.py

- [ ] 4.1 Open `tests/test_services.py`
- [ ] 4.2 Add a `monkeypatch` fixture for `ROUTING_USE_EMBEDDINGS=true`
- [ ] 4.3 Add a fixture that patches `openai.embeddings.create` to return a deterministic mock:
  - The mock returns an object whose `.data[i].embedding` is a fixed list of floats
  - Use distinct vectors per anchor class so `_knn_classify` can distinguish them
  - Example: simple anchors get `[1.0, 0.0, 0.0]`, complex get `[0.0, 1.0, 0.0]`
- [ ] 4.4 Write:
  - `test_determine_complexity_returns_correct_type`: with mocked embeddings and
    `ROUTING_USE_EMBEDDINGS=true`, call `determine_complexity("test")` — verify return type
    is `tuple` with 3 elements matching `(str, str, bool)`
  - `test_embedding_fallback_on_api_error`: mock `openai.embeddings.create` to raise
    `openai.APIConnectionError`; call `determine_complexity("test")` — must not raise;
    must return a valid `(Complexity, Tier, bool)` tuple (from keyword fallback)
  - `test_cosine_similarity_identical_vectors`: `_cosine_similarity([1.0, 0.5], [1.0, 0.5])` → `1.0`
  - `test_cosine_similarity_orthogonal_vectors`: `_cosine_similarity([1.0, 0.0], [0.0, 1.0])` → `0.0`
  - `test_knn_majority_vote`: construct mock anchors where 2 of 3 nearest are `"complex"`;
    verify `_knn_classify` returns `"complex"`
  - `test_keyword_fallback_when_disabled`: set `ROUTING_USE_EMBEDDINGS=false`;
    verify `openai.embeddings.create` is NOT called; verify result is still valid
- [ ] 4.5 Run: `OTEL_SDK_DISABLED=true pytest tests/test_services.py -v` — all tests pass

**Acceptance**: All 6 new tests pass. No real `OPENAI_API_KEY` required.

---

## Task 5 — Create scripts/verify_routing.py

- [ ] 5.1 Create `scripts/` directory if it does not exist
- [ ] 5.2 Create `scripts/verify_routing.py` with 20 test messages (10 per class): 10 clearly simple,
  10 clearly complex, with ground-truth labels
- [ ] 5.3 The script calls `determine_complexity(message)` for each
- [ ] 5.4 Counts correct classifications and prints accuracy
- [ ] 5.5 Exits 0 if accuracy ≥ 90%, exits 1 otherwise
- [ ] 5.6 Run manually with `OPENAI_API_KEY` set:
  ```bash
  ROUTING_USE_EMBEDDINGS=true python scripts/verify_routing.py
  ```
- [ ] 5.7 Record the accuracy in a comment at the top of `app/services/routing.py`:
  ```python
  # Embedding classifier accuracy: XX% on 20-item held-out set (YYYY-MM-DD)
  ```

**Acceptance**: Script exits 0 with ≥ 90% accuracy. Accuracy is documented in routing.py.

---

## Task 6 — Full verification

- [ ] 6.1 `OTEL_SDK_DISABLED=true pytest tests/ -v` — all tests pass, ≥ 236 tests
- [ ] 6.2 `ruff check app/services/routing.py` — zero errors
- [ ] 6.3 `mypy app/services/routing.py --ignore-missing-imports` — zero errors
- [ ] 6.4 Confirm: `python -c "from app.services.routing import determine_complexity"` does NOT call
  OpenAI at import time (anchors are lazy)
- [ ] 6.5 Confirm: `ROUTING_USE_EMBEDDINGS=false determine_complexity("test")` returns without any
  network call

**Acceptance**: Full test suite green. No import-time OpenAI calls. Fallback works.

---

## Completion criteria
This spec is complete when:
- `determine_complexity()` uses embedding-based kNN when `ROUTING_USE_EMBEDDINGS=true`
- Falls back to keyword classifier on any API failure or when `ROUTING_USE_EMBEDDINGS=false`
- Signature `(message: str) -> tuple[Complexity, Tier, bool]` is unchanged
- Anchor embeddings are lazy (computed on first call, cached thereafter)
- `scripts/verify_routing.py` exits 0 with ≥ 90% accuracy (run with real credentials)
- `OTEL_SDK_DISABLED=true pytest tests/ -v` reports ≥ 236 tests, all passing
- Accuracy is documented at the top of `routing.py` with date

---

## Sequence summary for all specs

| Spec | Gate (tests must pass before starting) | New tests added | Running total |
|------|-----------------------------------------|-----------------|---------------|
| 001–006 + hardening | 0 (fresh baseline)              | 192             | 192           |
| 007  | 192                                     | 9               | 201           |
| 008  | 201                                     | 0               | 201           |
| 009  | 201                                     | 4               | 205           |
| 010  | 205                                     | 8               | 213           |
| 011  | 213                                     | 8               | 221           |
| 012  | 221                                     | 9               | 230           |
| 013  | 230                                     | 6               | 236           |

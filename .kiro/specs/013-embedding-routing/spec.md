# Spec: 013 Embedding-Based Routing Classifier

## Goal
Replace the keyword + length heuristic in `app/services/routing.py` with a few-shot kNN
classifier backed by OpenAI embeddings. This eliminates systematic misroutes caused by verbose
simple questions and terse complex ones, improving cost efficiency without changing any API
contract or downstream logic.

## Prerequisite gate
Spec 012 must be complete before starting:

```bash
OTEL_SDK_DISABLED=true pytest tests/ -v  # ≥ 176 tests, all passing
```

All tests must be green before any task in this spec begins.

## What this spec changes
- `app/services/routing.py` — adds embedding-based kNN classifier; keeps keyword classifier
  as fallback
- `tests/test_services.py` — mock-based tests for new routing logic

## What this spec adds
- `scripts/verify_routing.py` — manual accuracy verification script (not a pytest test)

## What this spec does NOT change
The signature of `determine_complexity()` is frozen:
```python
def determine_complexity(message: str) -> tuple[Complexity, Tier, bool]
```
All callers, routes, schemas, gateway, middleware, and all prior specs are frozen.

## Problem
The keyword + length classifier produces systematic errors:
- "What is the capital of France, and can you explain all of its historical districts,
  arrondissements, notable architecture, and cultural significance?" → classified as complex
  (long), but is a factual lookup → cheap tier is correct
- "Optimize." → classified as simple (short), but is ambiguous and expensive → escalation
  needed

Keyword matching cannot distinguish verbosity from complexity. Production routing requires
semantic understanding.

## Acceptance criteria
1. `determine_complexity()` signature and return type are unchanged.
2. When `ROUTING_USE_EMBEDDINGS=true`, the embedding-based kNN path is used.
3. When `ROUTING_USE_EMBEDDINGS=false`, the keyword classifier is used directly.
4. When the embedding API raises any exception, the function falls back to keyword matching
   without propagating the error or returning a 500.
5. Anchor embeddings are computed lazily (on first call), not at module import.
6. `_cosine_similarity(v, v)` returns `1.0` for any non-zero vector.
7. `_knn_classify()` returns the majority class of the k=3 nearest anchors.
8. All existing routing tests pass with embeddings mocked.
9. `scripts/verify_routing.py` exits 0 when ≥ 90% of test messages classify correctly
   (run with real embeddings — not part of the automated test suite).
10. `OTEL_SDK_DISABLED=true pytest tests/ -v` — all tests pass.

## Testing requirements
- `tests/test_services.py` additions: mock `openai.embeddings.create` to return deterministic
  vectors; verify `determine_complexity()` still returns the correct tuple type; verify
  fallback when embedding raises `openai.APIConnectionError`.
- Tests must not require a real `OPENAI_API_KEY` — all embedding calls are mocked.
- `scripts/verify_routing.py` is a manual script only — it is not part of `pytest`.

## Hard rules
- Keyword classifier constants (`COMPLEX_KEYWORDS`, `SIMPLE_KEYWORDS`, `SIMPLE_LENGTH_THRESHOLD`)
  must remain in the file as the fallback path — do not delete them.
- Anchor embeddings are computed once per process, cached in a module-level variable.
- The embedding call goes through `openai.embeddings.create()` directly — not through `call_llm`.
- No `numpy` dependency: cosine similarity uses pure Python arithmetic.
- `ROUTING_USE_EMBEDDINGS` env var (default `"true"`) controls the active path.
- The fallback is silent (log warning only, no exception, no 500).

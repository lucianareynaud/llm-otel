"""Semantic cache for gateway LLM calls.

NOT YET IMPLEMENTED — see spec 010 (010-semantic-cache).

Spec 010 will implement:
  - Exact cache layer: SHA-256 hash of the normalised prompt as the lookup key.
  - Semantic cache layer: cosine similarity against stored embedding vectors,
    with a configurable threshold (SEMANTIC_CACHE_THRESHOLD, default 0.97).
  - Module-level singleton with public functions:
      cache_get(prompt: str) -> str | None
      cache_put(prompt: str, response: str) -> None
      cache_clear() -> None
      cache_stats() -> dict[str, int]
  - Controlled by SEMANTIC_CACHE_ENABLED env var (default false).
  - Lives exclusively here — routes may not import from this module directly.

Do not implement any part of this module until spec 010's prerequisite gate
(167 passing tests) is green and the spec's tasks.md is being executed in order.
"""


def cache_get(prompt: str) -> str | None:  # noqa: ARG001
    raise NotImplementedError("gateway.cache is not yet implemented (spec 010)")


def cache_put(prompt: str, response: str) -> None:  # noqa: ARG001
    raise NotImplementedError("gateway.cache is not yet implemented (spec 010)")


def cache_clear() -> None:
    raise NotImplementedError("gateway.cache is not yet implemented (spec 010)")


def cache_stats() -> dict[str, int]:
    raise NotImplementedError("gateway.cache is not yet implemented (spec 010)")

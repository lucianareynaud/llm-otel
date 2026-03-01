# Handoff to Kiro

## Baseline state

Specs 001–006 are **complete**. This is a verified, installable baseline.

The hardening pass (post-006) added:
- `gateway/semconv.py` — single source of truth for all `gen_ai.*` attribute/metric strings
- `tests/test_schemas.py` — schema drift guard for all public API models, JSONL schema, report shape, and `GatewayResult`
- `tests/test_semconv.py` — semconv purity test (AST-walk: no `gen_ai.*` literals outside `gateway/semconv.py`)
- `pyproject.toml` — full project metadata + `dev` extras; `pip install -e ".[dev]"` is now the install command
- `.github/workflows/ci.yml` and `regression.yml` — complete, non-empty, with pip caching

Current test count: **192 tests**.

## Install

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
```

## Quality gates (must all stay green)

```bash
OTEL_SDK_DISABLED=true python3 -m pytest -q          # 192 tests, all passing
python3 -m ruff check .
python3 -m ruff format --check .
python3 -m mypy app/ gateway/ evals/ reporting/ --ignore-missing-imports
```

CI (`.github/workflows/ci.yml`) runs these four gates on every push and pull request. A red CI run means the next spec's prerequisite gate is not met — do not proceed.

## Frozen contracts — do not change without updating tests

| Contract | Location | Guard |
|---|---|---|
| `ClassifyComplexityRequest/Response` | `app/schemas/classify_complexity_*.py` | `tests/test_schemas.py` |
| `AnswerRoutedRequest/Response` | `app/schemas/answer_routed_*.py` | `tests/test_schemas.py` |
| `ConversationTurnRequest/Response` | `app/schemas/conversation_turn_*.py` | `tests/test_schemas.py` |
| JSONL telemetry event schema | `gateway/telemetry.py::_write_jsonl_event` | `tests/test_schemas.py` |
| `NormalizedTelemetryRow` / `AggregateMetrics` | `reporting/make_report.py` | `tests/test_schemas.py` |
| `GatewayResult` dataclass | `gateway/client.py` | `tests/test_schemas.py` |
| GenAI semconv string constants | `gateway/semconv.py` | `tests/test_semconv.py` |

**Rule**: `gen_ai.*` string literals are forbidden outside `gateway/semconv.py`. The purity test will fail if any are introduced. Add new constants to `gateway/semconv.py` first.

## Next spec for Kiro: **007-auth**

Start from `.kiro/specs/007-auth/`. The prerequisite gate is:

```bash
OTEL_SDK_DISABLED=true pytest tests/ -v  # must report ≥ 192 tests, all passing
```

Spec 007 adds API key authentication and per-key rate limiting. After 007, the test count should reach ≥ 201.

## Spec sequence (007 → 013)

| Spec | Gate before starting | Adds | Total after |
|---|---|---|---|
| 007-auth | ≥ 192 | 9 | 201 |
| 008-async-retry | ≥ 201 | 0 | 201 |
| 009-token-counting | ≥ 201 | 4 | 205 |
| 010-semantic-cache | ≥ 205 | 8 | 213 |
| 011-circuit-breaker | ≥ 213 | 8 | 221 |
| 012-conversation-persistence | ≥ 221 | 9 | 230 |
| 013-embedding-routing | ≥ 230 | 6 | 236 |

## What Kiro must not change casually

1. **Schema contracts** listed above — any field rename or type change requires updating `tests/test_schemas.py` explicitly.
2. **Semconv module** — `gateway/semconv.py` is the only place for `gen_ai.*` strings. Do not add inline string literals in other files.
3. **Install command** — use `pip install -e ".[dev]"`, not `pip install -r requirements.txt`.
4. **Test count gate** — the prerequisite gate for each spec uses the counts in `tasks.md`. Do not lower them.
5. **`OTEL_SDK_DISABLED=true`** — all tests must run with this env var. Never introduce tests that require live OTel connections.
6. **`gateway/cache.py`, `app/services/documents.py`, `app/services/retrieval.py`** — intentionally stubbed with `NotImplementedError`. Do not implement them ahead of their specs.
7. **`scripts/loadgen.py`, `scripts/benchmark_before_after.py`, `scripts/make_report.py`** — intentionally stubbed. Implement only when their spec is assigned.

## Intentionally deferred (future specs)

- Auth middleware (`app/middleware/auth.py`) — Spec 007
- Rate limiting (`app/middleware/rate_limit.py`) — Spec 007
- Async gateway rewrite — Spec 008
- tiktoken token counting (`gateway/token_counter.py`) — Spec 009
- Semantic cache implementation (`gateway/cache.py`) — Spec 010
- Circuit breaker (`gateway/circuit_breaker.py`) — Spec 011
- Server-side conversation store (`app/services/conversation_store.py`) — Spec 012
- Embedding-based routing (`ROUTING_USE_EMBEDDINGS` env var) — Spec 013
- Live credential smoke tests (marked `- [ ]` in specs 002 and 005) — require `OPENAI_API_KEY`

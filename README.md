# LLM Cost Control Reference App

A minimal reference app for measuring, controlling, and reporting the operational cost behavior of LLM-based inference flows.

The repository demonstrates three controlled LLM workflows that make cost, routing decisions, context growth, telemetry, and bounded regression detection inspectable. OpenTelemetry instrumentation is a first-class concern — every LLM call produces both OTel spans/metrics and an append-only JSONL telemetry file.

**OTel signal stability posture:** Traces and metrics are at Stable stability in the Python SDK and are the primary portfolio signals. The GenAI semantic conventions (`gen_ai.*` attributes) remain at Development stability in `opentelemetry-semantic-conventions 0.60b1` and can rename attributes between releases. All `gen_ai.*` attribute strings are centralized in `gateway/semconv.py` — the only file that imports from `opentelemetry.semconv._incubating`. When the spec evolves, only that file changes.

## Tech Stack

| Layer | Package | Version |
|---|---|---|
| Web framework | `fastapi` | 0.134.0 |
| ASGI server | `uvicorn[standard]` | 0.41.0 |
| Data validation | `pydantic` | 2.12.5 |
| LLM provider | `openai` | 2.24.0 |
| Test runner | `pytest` | 9.0.2 |
| OTel API/SDK | `opentelemetry-api/sdk` | 1.39.1 |
| OTLP HTTP exporter | `opentelemetry-exporter-otlp-proto-http` | 1.39.1 |
| FastAPI auto-instrumentation | `opentelemetry-instrumentation-fastapi` | 0.60b1 |
| GenAI semantic conventions | `opentelemetry-semantic-conventions` | 0.60b1 |

## Setup

Install the project and all development dependencies into a virtual environment:

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
```

This installs the project in editable mode from `pyproject.toml` (which supersedes `requirements.txt`) along with `pytest`, `ruff`, and `mypy` via the `dev` extras.

## Environment Variables

### Required for live LLM calls

```bash
OPENAI_API_KEY="your_key_here"
```

Without a valid API key, requests to gateway-backed routes (`/answer-routed`, `/conversation-turn`) will fail.

### OTel exporter (optional)

| Variable | Default | Description |
|---|---|---|
| `OTEL_EXPORTER_OTLP_ENDPOINT` | _(none — console fallback)_ | OTLP HTTP collector URL (e.g. Grafana Cloud, Datadog, Jaeger) |
| `OTEL_SDK_DISABLED` | `false` | Set `true` in CI to suppress OTel I/O |
| `OTEL_SERVICE_NAME` | `llm-cost-control` | Reported service name in traces |
| `OTEL_SERVICE_VERSION` | `0.1.0` | Reported service version |
| `OTEL_DEPLOYMENT_ENVIRONMENT` | `development` | Deployment environment label |
| `OTEL_METRIC_EXPORT_INTERVAL` | `30000` | Metric export interval in ms |
| `OTEL_SEMCONV_STABILITY_OPT_IN` | _(not set)_ | GenAI convention migration mode: `gen_ai_latest_experimental` (new names only) or `gen_ai_latest_experimental/dup` (old + new simultaneously) |

### Gateway behavior (optional)

| Variable | Default | Description |
|---|---|---|
| `RATE_LIMIT_RPM` | `60` | Requests per minute (spec 007, not yet enforced) |
| `MAX_CONTEXT_TOKENS` | `8192` | Maximum context tokens allowed |
| `ROUTING_USE_EMBEDDINGS` | `true` | Embedding-based routing classifier (spec 013, not yet active) |

## End-to-End Workflow

1. Start the FastAPI app locally.
2. Call routes to generate telemetry in `artifacts/logs/telemetry.jsonl`.
3. Run eval runners to generate bounded regression artifacts in `artifacts/reports/`.
4. Generate a markdown report from telemetry and eval artifacts.

## Running the App

```bash
uvicorn app.main:app --reload
```

The app will be available at `http://127.0.0.1:8000`. Interactive API docs at `http://127.0.0.1:8000/docs`.

On startup, `setup_otel()` configures the global `TracerProvider` and `MeterProvider`. `FastAPIInstrumentor` wraps every business route handler in an OTel `SERVER` span (health paths are excluded). On shutdown, buffered spans and metrics are flushed before exit.

## Routes

### GET /healthz

Liveness probe — always returns `{"status": "ok"}` with HTTP 200. No auth required.

### GET /readyz

Readiness probe — returns `{"status": "ready"}` / 200 after startup completes, `{"status": "not_ready"}` / 503 otherwise. No auth required.

### POST /classify-complexity

Classify message complexity and recommend a model tier.

This route is local and deterministic. It does not call the gateway or provider.

```bash
curl -X POST http://127.0.0.1:8000/classify-complexity \
  -H "Content-Type: application/json" \
  -d '{"message": "What is 2+2?"}'
```

```json
{
  "complexity": "simple",
  "recommended_tier": "cheap",
  "needs_escalation": false
}
```

### POST /answer-routed

Generate an answer using routing-based model selection.

Classifies the message locally, then calls the gateway with the resulting tier.

```bash
curl -X POST http://127.0.0.1:8000/answer-routed \
  -H "Content-Type: application/json" \
  -d '{"message": "Analyze the complex implications of quantum computing"}'
```

```json
{
  "answer": "string",
  "selected_model": "string",
  "routing_decision": "cheap or expensive"
}
```

### POST /conversation-turn

Process a conversation turn with context strategy application.

Prepares context locally using the requested strategy, then calls the gateway.

```bash
curl -X POST http://127.0.0.1:8000/conversation-turn \
  -H "Content-Type: application/json" \
  -d '{
    "conversation_id": "conv-123",
    "history": ["Hello", "How are you?"],
    "message": "Tell me about Python",
    "context_strategy": "full"
  }'
```

```json
{
  "answer": "string",
  "turn_index": 2,
  "context_tokens_used": 15,
  "context_strategy_applied": "full"
}
```

`context_tokens_used` is derived from the character-based token estimation heuristic in `app/services/context_manager.py`.

## Context Strategies

The `/conversation-turn` route supports three context strategies:

- `full`: include all conversation history
- `sliding_window`: keep only the most recent 5 turns
- `summarized`: deterministic placeholder summary for older history + last 5 turns verbatim

## Gateway

`gateway/client.py` is the single choke point for all LLM provider calls. Every call to `call_llm()`:

1. Looks up the route policy (`gateway/policies.py`) for model selection and retry configuration.
2. Opens an OTel `CLIENT` span with GenAI semantic convention attributes (`gen_ai.system`, `gen_ai.request.model`, `gen_ai.usage.input_tokens`, `gen_ai.usage.output_tokens`, etc.).
3. Calls the OpenAI Responses API (`client.responses.create()`) with exponential-backoff retry.
4. Estimates cost locally via the pricing snapshot in `gateway/cost_model.py`.
5. Emits dual telemetry: OTel metrics (four instruments) + appends a JSON event to `artifacts/logs/telemetry.jsonl` (file-locked for multi-worker safety).

### Models and pricing

Source: <https://platform.openai.com/docs/models> — retrieved 2026-02-28

| Tier | Model | Input ($/1M tokens) | Output ($/1M tokens) |
|---|---|---|---|
| `cheap` | `gpt-4o-mini` | $0.15 | $0.60 |
| `expensive` | `gpt-4o` | $2.50 | $10.00 |

### Route policies

Both gateway-backed routes use `max_output_tokens=500`, `retry_attempts=2`, `cache_enabled=False`.

### OTel trace structure

```
POST /answer-routed  [kind=SERVER, FastAPIInstrumentor]
  └── chat gpt-4o-mini  [kind=CLIENT, gateway/client.py]
```

Span status follows the OTel spec: `UNSET` on success (UNSET means no error); `Status(StatusCode.ERROR, description)` on failure.

### OTel metrics emitted per call

| Instrument | Type | Description |
|---|---|---|
| `gen_ai.client.token.usage` | Histogram | Input and output token counts |
| `gen_ai.client.operation.duration` | Histogram | Latency in seconds |
| `llm_gateway.estimated_cost_usd` | Counter | Accumulated estimated USD cost |
| `llm_gateway.requests` | Counter | Request count by status |

If `OTEL_EXPORTER_OTLP_ENDPOINT` is set, spans and metrics are exported via OTLP HTTP/protobuf. Otherwise they fall back to the console exporter.

### Telemetry output

Gateway telemetry is appended as JSON lines to:

```text
artifacts/logs/telemetry.jsonl
```

Example telemetry event:

```json
{
  "timestamp": "2026-02-28T22:58:56.195450+00:00",
  "request_id": "46835b9b-90a0-4a06-83aa-999db8388c4e",
  "route": "/conversation-turn",
  "provider": "openai",
  "model": "gpt-4o",
  "latency_ms": 3751.665540970862,
  "status": "success",
  "tokens_in": 28,
  "tokens_out": 118,
  "estimated_cost_usd": 0.00124,
  "cache_hit": false,
  "schema_valid": true,
  "error_type": null,
  "conversation_id": "conv-123",
  "turn_index": 2,
  "context_strategy": "full",
  "context_strategy_applied": "full",
  "context_tokens_used": 15,
  "selected_model": "gpt-4o"
}
```

## Eval Harness

The repository includes a bounded eval harness for operational regression detection.

The eval harness checks:

- schema compliance
- required field presence
- bounded response behavior
- routing metadata behavior
- context metadata behavior

It does not perform semantic evaluation, model-judge scoring, or open-ended quality judgment.

### Run evals

Run eval runners from repo root in module mode:

```bash
OTEL_SDK_DISABLED=true python3 -m evals.runners.run_classify_eval
OTEL_SDK_DISABLED=true python3 -m evals.runners.run_answer_routed_eval
OTEL_SDK_DISABLED=true python3 -m evals.runners.run_conversation_turn_eval
```

Use module execution (`-m`) — not direct script execution — to ensure consistent import resolution.

### Eval behavior

- `/classify-complexity` eval runs against the local deterministic route.
- `/answer-routed` eval uses mocked gateway behavior by default.
- `/conversation-turn` eval uses mocked gateway behavior by default.
- Eval execution does not require `OPENAI_API_KEY`.

### Eval artifacts

```text
artifacts/reports/classify_eval_results.json
artifacts/reports/answer_routed_eval_results.json
artifacts/reports/conversation_turn_eval_results.json
```

## Reporting

Generate operational reports from telemetry and eval artifacts.

The reporting layer is downstream-only: it reads existing artifact files and does not execute routes, call providers, or run evals.

### Single-run report

```bash
python3 -m reporting.make_report \
  --after-log artifacts/logs/telemetry.jsonl \
  --output artifacts/reports/report.md
```

### Before/after comparison report

```bash
python3 -m reporting.make_report \
  --before-log artifacts/logs/before_telemetry.jsonl \
  --after-log artifacts/logs/telemetry.jsonl \
  --output artifacts/reports/report_before_after.md
```

### Include eval results

```bash
python3 -m reporting.make_report \
  --after-log artifacts/logs/telemetry.jsonl \
  --classify-eval artifacts/reports/classify_eval_results.json \
  --answer-eval artifacts/reports/answer_routed_eval_results.json \
  --conversation-eval artifacts/reports/conversation_turn_eval_results.json \
  --output artifacts/reports/report.md
```

Reports include: per-route aggregate tables (p50/p95 latency, total cost, error rate), before/after delta comparison, Pareto cost/error analysis, eval summary, and rule-based recommendations.

## GenAI Semantic Convention Isolation

The GenAI semantic conventions (`gen_ai.*` attribute names) are at [Development stability](https://opentelemetry.io/docs/specs/semconv/gen-ai/gen-ai-spans/) and can change without a deprecation window. The repository is designed to survive a convention rename without touching any business logic:

**`gateway/semconv.py`** is the single source of truth for all `gen_ai.*` attribute strings. `client.py` and `telemetry.py` import constants from here — never from `opentelemetry.semconv._incubating` directly.

**`_PENDING_RENAMES`** in `gateway/semconv.py` contains the **active** migration from the v1.36.0 legacy name to the current spec-required name:

```python
_PENDING_RENAMES = {
    "gen_ai.system": "gen_ai.provider.name",  # v1.36.0 → latest experimental
}
```

The [current OpenAI semconv spec](https://opentelemetry.io/docs/specs/semconv/gen-ai/openai/) states `gen_ai.provider.name` MUST be set to `"openai"`. The v1.36.0 name `gen_ai.system` is the default for backward compatibility with backends that have not yet migrated.

**`resolve_attrs()`** applies the `OTEL_SEMCONV_STABILITY_OPT_IN` opt-in flag:

| `OTEL_SEMCONV_STABILITY_OPT_IN` | Behavior |
|---|---|
| _(not set)_ | Emit v1.36.0 names only (`gen_ai.system = "openai"`) — default, backward-compatible |
| `gen_ai_latest_experimental/dup` | Emit **both** legacy and new names simultaneously — use during migration window |
| `gen_ai_latest_experimental` | Emit only the new name (`gen_ai.provider.name = "openai"`) — use once migration is complete |
| `http,gen_ai_latest_experimental/dup` | Comma-separated tokens for multiple semconv families are supported |

This mechanism is live and fully tested (`tests/test_semconv.py`). Adding a future rename is a one-line change to `_PENDING_RENAMES`.

## Tests

```bash
OTEL_SDK_DISABLED=true python3 -m pytest tests/ -q
```

Run focused test modules:

```bash
OTEL_SDK_DISABLED=true python3 -m pytest tests/test_routes.py -q    # route handlers (mocked gateway)
OTEL_SDK_DISABLED=true python3 -m pytest tests/test_gateway.py -q   # cost model, policies, call_llm, error categorization
OTEL_SDK_DISABLED=true python3 -m pytest tests/test_services.py -q  # routing heuristic, context strategies
OTEL_SDK_DISABLED=true python3 -m pytest tests/test_evals.py -q     # eval datasets, assertion helpers, runner smoke tests
OTEL_SDK_DISABLED=true python3 -m pytest tests/test_reporting.py -q # telemetry normalization, aggregation, markdown rendering
OTEL_SDK_DISABLED=true python3 -m pytest tests/test_schemas.py -q   # Pydantic schema validation
OTEL_SDK_DISABLED=true python3 -m pytest tests/test_health.py -q    # /healthz and /readyz endpoints
OTEL_SDK_DISABLED=true python3 -m pytest tests/test_semconv.py -q   # semconv constants and OTEL_SEMCONV_STABILITY_OPT_IN
```

`OTEL_SDK_DISABLED=true` prevents the OTel SDK from starting background threads and attempting OTLP connections during tests.

## Linting and Type Checking

The exact local gate that CI enforces:

```bash
python3 -m ruff check .
python3 -m ruff format --check .
python3 -m mypy app/ gateway/ evals/ reporting/ --ignore-missing-imports
```

Configuration lives in `pyproject.toml`. All three checks run in CI on every push and pull request. A PR that fails any check is blocked from merging.

## CI

| Workflow | Trigger | Steps |
|---|---|---|
| `ci.yml` | push / pull_request | ruff lint → ruff format check → mypy → pytest |
| `regression.yml` | push to main / workflow_dispatch | all three eval runners → fail if any `failed > 0` |

No secrets are required in CI. Eval runners mock the gateway and do not call OpenAI.

## Artifact Paths

| Artifact | Path |
|---|---|
| Live telemetry | `artifacts/logs/telemetry.jsonl` |
| Classify eval results | `artifacts/reports/classify_eval_results.json` |
| Answer-routed eval results | `artifacts/reports/answer_routed_eval_results.json` |
| Conversation-turn eval results | `artifacts/reports/conversation_turn_eval_results.json` |
| Single-run report | `artifacts/reports/report.md` |
| Before/after report | `artifacts/reports/report_before_after.md` |

## Stub Modules

The following modules are scaffolded but not yet implemented. Each raises `NotImplementedError` with a pointer to the implementing spec:

| Module | Implementing Spec |
|---|---|
| `gateway/cache.py` | spec 010 (semantic cache) |
| `app/services/documents.py` | no spec yet assigned |
| `app/services/retrieval.py` | no spec yet assigned |
| `scripts/loadgen.py` | no spec yet assigned |
| `scripts/benchmark_before_after.py` | no spec yet assigned |
| `scripts/make_report.py` | no spec yet assigned |

## Production-Readiness Roadmap

The following specs are pending in sequential order (gate = required passing test count before starting):

| Spec | Feature | Gate |
|---|---|---|
| 007 | Auth middleware (`X-API-Key`) + rate limiting (sliding window, 429) | 141 |
| 008 | Async gateway retry (`AsyncOpenAI` + `asyncio.sleep`) | 150 |
| 009 | Accurate token counting (`tiktoken`) | 150 |
| 010 | Semantic cache (SHA-256 exact + cosine similarity layer) | 154 |
| 011 | Circuit breaker (three-state: closed/open/half-open) | 162 |
| 012 | Server-side conversation persistence (`InMemoryConversationStore` + Redis) | 170 |
| 013 | Embedding-based routing classifier (kNN with OpenAI embeddings, keyword fallback) | 179 |

Run `OTEL_SDK_DISABLED=true pytest tests/ -v | tail -1` to determine the current position in the sequence.

## Scope Notes

This repository is intentionally narrow.

It is not:

- a general-purpose agent framework
- a multi-provider platform
- a notebook-based experimentation repo
- a semantic evaluation suite
- a dashboard product
- a production SaaS system

It is a small, inspectable engineering kit for controlled LLM route behavior, gateway-backed telemetry (OTel + JSONL), bounded regression detection, and markdown reporting.

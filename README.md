# LLM Cost Control Reference App

A minimal reference app for measuring, controlling, and reporting the operational cost behavior of LLM-based inference flows.

The repository demonstrates three controlled LLM workflows that make cost, routing decisions, context growth, telemetry, and bounded regression detection inspectable. OpenTelemetry instrumentation is a first-class concern — every LLM call produces both OTel spans/metrics and an append-only JSONL telemetry file.

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

Install dependencies into a virtual environment:

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

## Environment Variables

### Required for live LLM calls

```bash
OPENAI_API_KEY="your_key_here"
```

Without a valid API key, requests to gateway-backed routes (`/answer-routed`, `/conversation-turn`) will fail.

### OTel exporter (optional)

| Variable | Default | Description |
|---|---|---|
| `OTEL_EXPORTER_OTLP_ENDPOINT` | _(none — falls back to console)_ | OTLP HTTP collector URL (e.g. Grafana Cloud, Datadog, Jaeger) |
| `OTEL_SDK_DISABLED` | `false` | Set `true` in CI to suppress OTel I/O |
| `OTEL_SERVICE_NAME` | `llm-cost-control` | Reported service name in traces |
| `OTEL_SERVICE_VERSION` | `0.1.0` | Reported service version |
| `OTEL_DEPLOYMENT_ENVIRONMENT` | `development` | Deployment environment label |
| `OTEL_METRIC_EXPORT_INTERVAL` | `30000` | Metric export interval in ms |

### Gateway behavior (optional)

| Variable | Default | Description |
|---|---|---|
| `RATE_LIMIT_RPM` | `60` | Requests per minute (not yet enforced) |
| `MAX_CONTEXT_TOKENS` | `8192` | Maximum context tokens allowed |
| `ROUTING_USE_EMBEDDINGS` | `true` | Enable embedding-based routing classifier (spec 013, not yet active) |

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

On startup, `setup_otel()` configures the global `TracerProvider` and `MeterProvider`. `FastAPIInstrumentor` wraps every route handler in an OTel `SERVER` span. On shutdown, buffered spans and metrics are flushed before exit.

## Routes

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
5. Emits dual telemetry: OTel metrics (four instruments) + appends a JSON event to `artifacts/logs/telemetry.jsonl`.

### Models and pricing

| Tier | Model | Input ($/1M tokens) | Output ($/1M tokens) |
|---|---|---|---|
| `cheap` | `gpt-5-mini` | $0.25 | $2.00 |
| `expensive` | `gpt-5.2` | $1.75 | $14.00 |

### Route policies

Both gateway-backed routes use `max_output_tokens=500`, `retry_attempts=2`, `cache_enabled=False`.

### OTel trace structure

```
POST /answer-routed  [kind=SERVER, FastAPIInstrumentor]
  └── chat gpt-5-mini  [kind=CLIENT, gateway/client.py]
```

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
  "timestamp": "2026-02-27T22:58:56.195450+00:00",
  "request_id": "46835b9b-90a0-4a06-83aa-999db8388c4e",
  "route": "/conversation-turn",
  "provider": "openai",
  "model": "gpt-5.2",
  "latency_ms": 3751.665540970862,
  "status": "success",
  "tokens_in": 28,
  "tokens_out": 118,
  "estimated_cost_usd": 0.0017009999999999998,
  "cache_hit": false,
  "schema_valid": true,
  "error_type": null,
  "conversation_id": "conv-123",
  "turn_index": 2,
  "context_strategy": "full",
  "context_strategy_applied": "full",
  "context_tokens_used": 15,
  "selected_model": "gpt-5.2"
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
python3 -m evals.runners.run_classify_eval
python3 -m evals.runners.run_answer_routed_eval
python3 -m evals.runners.run_conversation_turn_eval
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

## Scripts

Utility scripts in `scripts/` for load generation and benchmarking. Run from repo root:

```bash
python3 -m scripts.loadgen          # drive request volume to generate telemetry
python3 -m scripts.benchmark_before_after  # capture before/after snapshots
python3 -m scripts.make_report      # report generation shortcut
```

## Tests

Run the full test suite:

```bash
python3 -m pytest tests/ -q
```

Run focused test modules:

```bash
python3 -m pytest tests/test_routes.py -q       # route handlers (mocked gateway)
python3 -m pytest tests/test_gateway.py -q      # cost model, policies, call_llm, error categorization
python3 -m pytest tests/test_services.py -q     # routing heuristic, context strategies
python3 -m pytest tests/test_evals.py -q        # eval datasets, assertion helpers, runner smoke tests
python3 -m pytest tests/test_reporting.py -q    # telemetry normalization, aggregation, markdown rendering
python3 -m pytest tests/test_schemas.py -q      # Pydantic schema validation
```

Set `OTEL_SDK_DISABLED=true` to suppress OTel I/O during test runs.

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

The following modules are scaffolded but not yet implemented:

- `gateway/cache.py` — semantic cache (exact SHA-256 lookup + cosine similarity layer)
- `app/services/documents.py` — document store for retrieval
- `app/services/retrieval.py` — retrieval service

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

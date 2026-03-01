# LLM Cost Control Gateway

A production-minded LLM gateway and FinOps control plane built with FastAPI and OpenTelemetry. The project demonstrates how to instrument, route, measure, and report on the operational cost behavior of LLM inference flows — not as a prototype, but as an engineering kit that is continuously verified by automated tests, schema guards, and CI gates.

## The Problem

When you add LLMs to a production system, costs compound quickly and silently. A single misrouted request — sending a simple query to `gpt-4o` instead of `gpt-4o-mini` — can be 16× more expensive. Multiply that across thousands of daily requests and routing decisions become a FinOps concern, not just a UX preference.

Existing observability tools give you traces and metrics for HTTP requests, but they do not natively give you:

- **Per-request cost attribution** tied to actual token usage
- **Routing decision visibility** — which model was selected, and why
- **Context growth tracking** — how much conversation history is being sent per turn
- **Regression detection** — whether a new model or prompt change moves the cost/quality Pareto frontier

This repository is a reference implementation of those capabilities.

## What's Built

| Layer | What it does |
|---|---|
| **FastAPI app** | Three instrumented routes covering different cost profiles: deterministic classification, model-tier routing, multi-turn conversation |
| **Gateway** | Single choke point for all LLM provider calls — enforces policies, measures latency, estimates cost, emits dual telemetry |
| **Telemetry** | Every gateway call produces an OTel `CLIENT` span with GenAI attributes *and* appends a structured event to an append-only JSONL file |
| **Cost model** | Local deterministic pricing snapshot; no external API calls needed to estimate cost |
| **Eval harness** | Dataset-driven regression runner with schema, routing, and context assertions per route |
| **Reporting** | Offline markdown report generator — p50/p95 latency, total cost, error rate, before/after delta, eval summary |
| **Semconv adapter** | `gateway/semconv.py` centralizes all `gen_ai.*` attribute strings and implements the `OTEL_SEMCONV_STABILITY_OPT_IN` dual-emission migration mechanism |

**Test coverage:** 192 tests passing. Every public schema, telemetry event structure, report output shape, and gateway contract is covered by schema drift guards that fail loudly on unintentional breaking changes.

## What Works Right Now

This project is under active development, but the core observability, evaluation, and reporting pipeline is **fully operational today**. You do not need to wait for the roadmap items to get value from it.

### Observability — ready

- Point `OTEL_EXPORTER_OTLP_ENDPOINT` at any OTLP-compatible backend (Grafana Cloud, Datadog, Jaeger, Honeycomb) and full traces with GenAI attributes start flowing immediately — no extra configuration.
- Every LLM call produces an OTel `CLIENT` span nested under the HTTP `SERVER` span, with model name, token counts, latency, and error status as span attributes.
- Four OTel metrics instruments emit per call: token usage, latency, estimated cost, request count. These feed directly into any dashboard connected to your collector.
- In parallel, a structured JSON event is written to `artifacts/logs/telemetry.jsonl` — append-only, file-locked, works completely offline without a collector.

### Cost attribution — ready

- Every request has a `estimated_cost_usd` field computed locally from a pricing snapshot, tied to the exact model and token counts returned by the API.
- The routing decision (`cheap` → `gpt-4o-mini`, `expensive` → `gpt-4o`) is recorded on every telemetry event — so you can immediately see the cost breakdown by tier.
- The reporting CLI generates a markdown report with per-route total cost, average cost, p50/p95 latency, and error rate from any JSONL file.

### Regression detection — ready

- Three eval runners (one per route) run against versioned JSONL datasets and check schema compliance, routing metadata, and context metadata.
- The CI regression workflow runs all three runners on every push to main and blocks the pipeline if any case fails.
- Before/after comparison reports quantify the cost and latency delta between two telemetry snapshots — useful for validating that a model change or prompt change moved metrics in the intended direction.

### What requires the roadmap to be complete

| Capability | Needs |
|---|---|
| Per-user / per-key cost attribution | Spec 007 — auth middleware |
| Exact pre-call token counts | Spec 009 — `tiktoken` integration |
| Cache hit savings as explicit billing events | Spec 010 — semantic cache |
| Automatic degradation detection | Spec 011 — circuit breaker |
| Cost attribution across conversation sessions | Spec 012 — server-side persistence |

Everything else in this section is functional with the current codebase.

## Tech Stack

| Layer | Package | Version |
|---|---|---|
| Web framework | `fastapi` | 0.134.0 |
| ASGI server | `uvicorn[standard]` | 0.41.0 |
| Data validation | `pydantic` | 2.12.5 |
| LLM provider | `openai` | 2.24.0 |
| OTel API/SDK | `opentelemetry-api/sdk` | 1.39.1 |
| OTLP HTTP exporter | `opentelemetry-exporter-otlp-proto-http` | 1.39.1 |
| FastAPI auto-instrumentation | `opentelemetry-instrumentation-fastapi` | 0.60b1 |
| GenAI semantic conventions | `opentelemetry-semantic-conventions` | 0.60b1 |
| Test runner | `pytest` | 9.0.2 |

## Setup

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
```

This installs the project in editable mode with all runtime and development dependencies (`pytest`, `ruff`, `mypy`) via the `dev` extras declared in `pyproject.toml`.

## Environment Variables

### Required for live LLM calls

```bash
OPENAI_API_KEY="your_key_here"
```

Without a valid key, gateway-backed routes (`/answer-routed`, `/conversation-turn`) will return errors. All tests and eval runners work without credentials.

### OTel exporter

| Variable | Default | Description |
|---|---|---|
| `OTEL_EXPORTER_OTLP_ENDPOINT` | _(none — console fallback)_ | OTLP HTTP collector URL (Grafana Cloud, Datadog, Jaeger, etc.) |
| `OTEL_SDK_DISABLED` | `false` | Set `true` in CI to suppress OTel I/O |
| `OTEL_SERVICE_NAME` | `llm-cost-control` | Reported service name in traces |
| `OTEL_SEMCONV_STABILITY_OPT_IN` | _(not set)_ | Semconv migration mode — see [GenAI Semantic Convention Isolation](#genai-semantic-convention-isolation) |

### Gateway behavior

| Variable | Default | Description |
|---|---|---|
| `MAX_CONTEXT_TOKENS` | `8192` | Maximum context tokens per conversation turn |

## Running the App

```bash
uvicorn app.main:app --reload
```

The app starts at `http://127.0.0.1:8000`. Interactive API docs at `/docs`.

On startup, `setup_otel()` configures the global `TracerProvider` and `MeterProvider`. `FastAPIInstrumentor` wraps every business route in an OTel `SERVER` span (health paths excluded). Buffered spans and metrics are flushed on shutdown.

## Routes

### GET /healthz and GET /readyz

Kubernetes-style probes. `/healthz` always returns 200. `/readyz` returns 503 until the lifespan startup sequence completes, then 200. No auth required on either.

### POST /classify-complexity

Classify message complexity and recommend a model tier — locally, without any LLM call.

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

This route represents the cheapest possible code path — zero token cost — and serves as the routing oracle for `/answer-routed`.

### POST /answer-routed

Generate an answer with automatic model-tier routing. The routing decision is surfaced in the response so callers can observe which cost tier was selected.

```bash
curl -X POST http://127.0.0.1:8000/answer-routed \
  -H "Content-Type: application/json" \
  -d '{"message": "Analyze the implications of quantum computing on cryptography"}'
```

```json
{
  "answer": "...",
  "selected_model": "gpt-4o",
  "routing_decision": "expensive"
}
```

### POST /conversation-turn

Process a multi-turn conversation with explicit context strategy control. Returns the number of tokens committed to context so the cost impact of history growth is visible to the caller.

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
  "answer": "...",
  "turn_index": 2,
  "context_tokens_used": 15,
  "context_strategy_applied": "full"
}
```

**Context strategies:** `full` (all history), `sliding_window` (last 5 turns), `summarized` (deterministic placeholder summary for older turns + last 5 verbatim).

## Gateway Architecture

`gateway/client.py` is the single choke point for every LLM provider call. Its execution path per request:

1. **Policy lookup** — `gateway/policies.py` maps route → model tier, max tokens, retry limit, cache flag
2. **OTel span** — opens a `CLIENT` span with GenAI semantic convention attributes
3. **Provider call** — calls `client.responses.create()` with exponential-backoff retry
4. **Cost estimation** — local arithmetic from `gateway/cost_model.py` pricing snapshot
5. **Dual telemetry emit** — OTel metrics (four instruments) + JSON line appended to `artifacts/logs/telemetry.jsonl` with `fcntl.flock` for multi-worker safety
6. **Structured result** — returns `GatewayResult(text, selected_model, request_id, tokens_in, tokens_out, estimated_cost_usd, cache_hit)`

### Models and pricing

Source: <https://platform.openai.com/docs/models> — retrieved 2026-02-28

| Tier | Model | Input ($/1M tokens) | Output ($/1M tokens) |
|---|---|---|---|
| `cheap` | `gpt-4o-mini` | $0.15 | $0.60 |
| `expensive` | `gpt-4o` | $2.50 | $10.00 |

Routing to `gpt-4o-mini` for simple queries costs roughly **16× less per output token** than defaulting to `gpt-4o` for everything. The reporting layer makes this delta visible.

### OTel trace structure

```
POST /answer-routed          [kind=SERVER, FastAPIInstrumentor]
  └── chat gpt-4o-mini       [kind=CLIENT, gateway/client.py]
```

Span status follows the OTel spec: `UNSET` on success; `Status(StatusCode.ERROR, description)` on failure.

### OTel metrics emitted per call

| Instrument | Type | Description |
|---|---|---|
| `gen_ai.client.token.usage` | Histogram | Input and output token counts |
| `gen_ai.client.operation.duration` | Histogram | End-to-end latency in seconds |
| `llm_gateway.estimated_cost_usd` | Counter | Accumulated estimated USD cost |
| `llm_gateway.requests` | Counter | Request count by status |

If `OTEL_EXPORTER_OTLP_ENDPOINT` is set, spans and metrics are exported via OTLP HTTP/protobuf. Otherwise they fall back to the console exporter.

### Telemetry event schema

Every gateway call appends a structured event to `artifacts/logs/telemetry.jsonl`:

```json
{
  "timestamp": "2026-02-28T22:58:56.195450+00:00",
  "request_id": "46835b9b-90a0-4a06-83aa-999db8388c4e",
  "route": "/conversation-turn",
  "provider": "openai",
  "model": "gpt-4o",
  "latency_ms": 3751.7,
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
  "context_tokens_used": 15,
  "selected_model": "gpt-4o"
}
```

The schema is frozen and protected by `tests/test_schemas.py`. Adding a field requires updating both the writer and the test simultaneously.

## GenAI Semantic Convention Isolation

The GenAI semantic conventions (`gen_ai.*` attribute names) are at [Development stability](https://opentelemetry.io/docs/specs/semconv/gen-ai/) and can be renamed between releases.

**Design decision:** all `gen_ai.*` strings live exclusively in `gateway/semconv.py`. No other file contains `gen_ai.*` string literals — enforced by an AST-walk test in `tests/test_semconv.py`. When a convention renames, only one file changes.

The adapter implements the `OTEL_SEMCONV_STABILITY_OPT_IN` mechanism from the OTel spec:

| `OTEL_SEMCONV_STABILITY_OPT_IN` | Behavior |
|---|---|
| _(not set)_ | Emit v1.36.0 names only (`gen_ai.system = "openai"`) — default, backward-compatible |
| `gen_ai_latest_experimental/dup` | Emit **both** legacy and current names simultaneously — use during migration window |
| `gen_ai_latest_experimental` | Emit only the current name (`gen_ai.provider.name = "openai"`) — use post-migration |

The active migration (`gen_ai.system` → `gen_ai.provider.name`) is declared in `_PENDING_RENAMES`. Adding a future rename is a one-line change.

## Eval Harness

Dataset-driven regression detection for all three routes. The harness checks:

- **Schema compliance** — every response matches its declared Pydantic shape
- **Required field presence** — no missing fields under any execution path
- **Routing metadata** — correct tier and model reflected in response and telemetry
- **Context metadata** — token usage and strategy applied match request parameters

The harness does not perform semantic evaluation, model-judge scoring, or open-ended quality judgment. Its job is to detect operational regressions, not measure answer quality.

### Run evals

```bash
OTEL_SDK_DISABLED=true python3 -m evals.runners.run_classify_eval
OTEL_SDK_DISABLED=true python3 -m evals.runners.run_answer_routed_eval
OTEL_SDK_DISABLED=true python3 -m evals.runners.run_conversation_turn_eval
```

Eval runners mock the gateway by default — no `OPENAI_API_KEY` required.

Artifacts written to `artifacts/reports/`.

## Reporting

Generate operational reports from telemetry and eval artifacts. The reporting layer is downstream-only: it reads existing artifact files, does not call any provider, and produces deterministic output.

### Single-run report

```bash
python3 -m reporting.make_report \
  --after-log artifacts/logs/telemetry.jsonl \
  --output artifacts/reports/report.md
```

### Before/after comparison

```bash
python3 -m reporting.make_report \
  --before-log artifacts/logs/before_telemetry.jsonl \
  --after-log artifacts/logs/telemetry.jsonl \
  --output artifacts/reports/report_before_after.md
```

Reports include: per-route p50/p95 latency, total and average estimated cost, error rate, schema-valid rate, before/after delta table, Pareto cost/error analysis, eval summary, and rule-based recommendations.

## Tests and Quality Gates

### Running tests

```bash
OTEL_SDK_DISABLED=true python3 -m pytest tests/ -q
```

192 tests. All run without network access or API keys.

| Module | What it covers |
|---|---|
| `tests/test_routes.py` | Route handlers with mocked gateway |
| `tests/test_gateway.py` | Cost model, policies, `call_llm()`, error categorization |
| `tests/test_services.py` | Routing heuristic, context strategy logic |
| `tests/test_evals.py` | Eval datasets, assertion helpers, runner smoke tests |
| `tests/test_reporting.py` | Telemetry normalization, aggregation, markdown rendering |
| `tests/test_schemas.py` | Schema drift guards for all public contracts |
| `tests/test_health.py` | `/healthz` and `/readyz` probes |
| `tests/test_semconv.py` | Semconv constants, `OTEL_SEMCONV_STABILITY_OPT_IN`, purity enforcement |

### Linting and type checking

```bash
python3 -m ruff check .
python3 -m ruff format --check .
python3 -m mypy app/ gateway/ evals/ reporting/ --ignore-missing-imports
```

All configuration lives in `pyproject.toml`. Ruff rule set: `E`, `F`, `I`, `UP`, `W`, `B`, `C4`.

### CI

| Workflow | Trigger | Steps |
|---|---|---|
| `ci.yml` | push / pull_request | ruff lint → ruff format check → mypy → pytest |
| `regression.yml` | push to main / `workflow_dispatch` | all three eval runners → fail if `failed > 0` |

No secrets required in CI. Eval runners mock the gateway.

## Artifact Paths

| Artifact | Path |
|---|---|
| Live telemetry | `artifacts/logs/telemetry.jsonl` |
| Eval results (per route) | `artifacts/reports/*_eval_results.json` |
| Single-run report | `artifacts/reports/report.md` |
| Before/after report | `artifacts/reports/report_before_after.md` |

## Roadmap

The following capabilities are planned in a sequential, gated implementation sequence. Each feature is spec'd with a design doc, acceptance criteria, and a minimum passing-test prerequisite gate.

| # | Feature | What it adds |
|---|---|---|
| **007** | **API key auth + rate limiting** | Per-key `X-API-Key` authentication middleware; sliding-window rate limiter returning 429 when exceeded; per-key usage tracked in telemetry |
| **008** | **Async gateway** | Full `async/await` rewrite using `AsyncOpenAI`; eliminates synchronous `time.sleep` on retries; unblocks concurrent request handling under load |
| **009** | **Accurate token counting** | Replace character-based estimation with `tiktoken`; exact pre-call token counts visible in telemetry; context window enforcement becomes precise |
| **010** | **Semantic cache** | Two-tier cache: SHA-256 exact match first, then cosine-similarity lookup on embeddings; cache hits reflected in cost telemetry as billing-avoidance events |
| **011** | **Circuit breaker** | Three-state FSM (closed/open/half-open) on the gateway; fast-fail behavior when provider error rate exceeds threshold; state transitions visible in OTel spans |
| **012** | **Server-side conversation persistence** | `InMemoryConversationStore` with a Redis-backed persistence layer; removes the need for clients to send full history on each turn; enables per-session cost attribution |
| **013** | **Embedding-based routing classifier** | Replace keyword heuristics with a kNN classifier using OpenAI embeddings; keyword fallback when embeddings unavailable; routing accuracy measurable via `scripts/verify_routing.py` |

Each spec increments the verified test count. The full sequence targets **236 tests** after spec 013. Progress is always checkable with:

```bash
OTEL_SDK_DISABLED=true pytest tests/ -v | tail -1
```

## Scope

This is a focused engineering kit, not a general-purpose framework. It is not:

- a multi-provider LLM platform
- a notebook-based experimentation environment
- a semantic evaluation suite or model judge
- a dashboard product or SaaS system

It is a small, inspectable control plane for measuring, routing, and reporting on LLM inference cost — with the engineering rigor (typed, linted, tested, CI-gated, OTel-instrumented) expected in production infrastructure.

# LLM Cost Control Gateway

A reference implementation of the LLM control plane core for cost-aware, observable inference in production systems.

This repository demonstrates how to instrument, route, measure, evaluate, and report on LLM inference behavior using FastAPI and OpenTelemetry. It is designed as an engineering reference for teams that need to understand the operational cost profile of LLM traffic, not as a consumer-facing application or a full enterprise platform.

## What this repository is

This project is a focused reference implementation of the core control-plane concerns behind LLM traffic:

- a single gateway choke point for provider calls
- route-aware cost attribution
- OpenTelemetry-based tracing and metrics
- append-only structured telemetry artifacts
- dataset-driven regression checks
- deterministic reporting from run artifacts
- semantic-convention isolation for evolving GenAI telemetry

The goal is not to simulate every platform-adjacent concern. The goal is to make the control-plane core inspectable, testable, and reusable as an engineering artifact.

## What problem it solves

As soon as LLM traffic enters production, model choice becomes an operational and financial concern.

A simple request sent to a premium model when a cheaper model would suffice can multiply cost with no meaningful product benefit. Once that behavior is repeated across many requests, teams need more than generic HTTP observability. They need to know:

- which route selected which model
- how much that request likely cost
- how much context was sent
- how latency behaves by route
- whether a routing or prompt change improved or degraded the cost/quality trade-off
- whether a new change introduced operational regressions

This repository is a reference implementation of that control-plane layer.

## What is implemented

### FastAPI application
The app exposes three instrumented routes that represent distinct cost profiles:

- deterministic complexity classification
- model-tier routed answer generation
- multi-turn conversation handling with explicit context strategies

### Gateway
`gateway/client.py` is the single choke point for all LLM provider calls. It enforces route policy, measures latency, estimates cost, emits telemetry, and returns normalized results.

### OpenTelemetry instrumentation
Each gateway call produces an OTel `CLIENT` span and emits OTel metrics. The telemetry model includes provider/model metadata, token usage, latency, and estimated cost.

### Structured local telemetry
In parallel with OTel emission, each gateway call appends a structured event to `artifacts/logs/telemetry.jsonl`. This supports offline analysis and report generation without requiring a telemetry backend.

### Cost model
Pricing is computed locally from a deterministic pricing snapshot. No external billing lookup is required for cost estimation.

### Eval harness
The repository includes dataset-driven regression runners that validate route behavior, schema integrity, and context-related assertions.

### Reporting
A deterministic markdown report generator summarizes cost, latency, error rate, route behavior, and before/after comparisons from artifact files.

### GenAI semantic-convention isolation
`gateway/semconv.py` centralizes GenAI-related semantic-convention strings and contains the migration mechanism for evolving OTel GenAI attribute names.

## What works today

The core observability, evaluation, and reporting pipeline is operational today. fileciteturn2file1L8-L29

### Observability
- Full OTel tracing and metrics for gateway calls
- OTel `CLIENT` spans nested under FastAPI `SERVER` spans
- structured append-only local telemetry output
- vendor-neutral telemetry foundation with semantic-convention isolation

### Cost attribution
- per-request estimated USD cost
- route-aware model selection surfaced in telemetry
- deterministic reporting of route-level total and average cost

### Regression detection
- dataset-driven eval runners
- CI regression workflow
- before/after comparison reports from telemetry snapshots

## What this repository is not

This repository is intentionally **not**:

- a full enterprise platform
- a complete SaaS product
- a frontend application
- an auth system
- a billing engine
- a multi-provider orchestration framework
- a dashboard product
- a semantic-evaluation or model-judge suite

Those concerns may exist around a production system, but they are not required to make the control-plane core valuable as a reference implementation.

## Architecture at a glance

The request path is:

1. request enters a FastAPI route
2. route-level logic selects the relevant policy path
3. the gateway executes the provider call
4. latency, token usage, and estimated cost are captured
5. OTel telemetry is emitted
6. a structured local run artifact is appended
7. downstream reporting consumes those artifacts deterministically

The repository is intentionally organized around this core path.

## Routes

### `GET /healthz`
Liveness probe.

### `GET /readyz`
Readiness probe.

### `POST /classify-complexity`
Classifies request complexity and recommends a model tier locally, without an LLM call.

### `POST /answer-routed`
Performs answer generation with model-tier routing and returns the selected model and routing decision.

### `POST /conversation-turn`
Processes a multi-turn conversation with explicit context strategy control and surfaces context-token usage in the response.

## Gateway model routing

The current model-tier routing uses:

- `cheap` → `gpt-4o-mini`
- `expensive` → `gpt-4o`

This repository is designed to make the operational implications of that distinction visible in telemetry and reports.

## Running locally

### Setup

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
```

### Environment

For live gateway-backed LLM calls:

```bash
OPENAI_API_KEY="your_key_here"
```

Optional OTel exporter configuration:

- `OTEL_EXPORTER_OTLP_ENDPOINT`
- `OTEL_SDK_DISABLED`
- `OTEL_SERVICE_NAME`
- `OTEL_SEMCONV_STABILITY_OPT_IN`

### Run the app

```bash
uvicorn app.main:app --reload
```

Interactive docs are available at `/docs`.

## Running tests

```bash
OTEL_SDK_DISABLED=true python3 -m pytest tests/ -q
```

The repository currently reports 192 passing tests across route behavior, gateway behavior, reporting, schema guards, health probes, and semantic-convention isolation. fileciteturn2file0L32-L32 fileciteturn2file4L38-L76

## Linting and typing

```bash
python3 -m ruff check .
python3 -m ruff format --check .
python3 -m mypy app/ gateway/ evals/ reporting/ --ignore-missing-imports
```

## Eval runners

```bash
OTEL_SDK_DISABLED=true python3 -m evals.runners.run_classify_eval
OTEL_SDK_DISABLED=true python3 -m evals.runners.run_answer_routed_eval
OTEL_SDK_DISABLED=true python3 -m evals.runners.run_conversation_turn_eval
```

The eval harness is designed for operational regression detection rather than semantic answer scoring. fileciteturn2file4L1-L13

## Reporting

Generate a markdown report from telemetry artifacts:

```bash
python3 -m reporting.make_report \
  --after-log artifacts/logs/telemetry.jsonl \
  --output artifacts/reports/report.md
```

Generate a before/after comparison report:

```bash
python3 -m reporting.make_report \
  --before-log artifacts/logs/before_telemetry.jsonl \
  --after-log artifacts/logs/telemetry.jsonl \
  --output artifacts/reports/report_before_after.md
```

Reports summarize route-level latency, cost, error rate, schema validity, and before/after deltas. fileciteturn2file4L15-L36

## Artifact paths

- `artifacts/logs/telemetry.jsonl`
- `artifacts/reports/*_eval_results.json`
- `artifacts/reports/report.md`
- `artifacts/reports/report_before_after.md`

## Scope boundary

This repository intentionally focuses on the core control-plane implementation.

Some adjacent capabilities are valid future extensions, but they are not required for the repository to be considered useful or complete as a reference implementation. That includes concerns such as:

- auth hardening
- exact pre-call token counting
- semantic caching
- circuit breaking
- persistent conversation storage

These are extension points, not proof that the current repository is unfinished. The current repository already stands on its own as a working reference for gateway-based LLM cost control, telemetry, evaluation, and reporting.

## Why this repository matters

This is not a generic LLM demo. It is a small, inspectable engineering artifact that shows how to build the core of an LLM control plane with:

- explicit gateway boundaries
- cost-aware routing visibility
- OpenTelemetry instrumentation
- local run artifacts for offline analysis
- regression discipline
- deterministic reporting

That is the point of the repository, and that is the standard by which it should be evaluated.

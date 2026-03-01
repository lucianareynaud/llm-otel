# LLM Cost Control Reference App

A minimal reference app for measuring, controlling, and reporting the operational cost behavior of LLM-based inference flows.

This repository demonstrates three controlled LLM workflows that make cost, routing decisions, context growth, telemetry, and bounded regression detection inspectable.

## Setup

Install dependencies:

```bash
python3 -m pip install -r requirements.txt
```

## End-to-End Workflow

The intended repository workflow is:

1. Start the FastAPI app locally.
2. Call routes to generate telemetry in `artifacts/logs/telemetry.jsonl`.
3. Run eval runners to generate bounded regression artifacts in `artifacts/reports/`.
4. Generate a markdown report from telemetry and eval artifacts.

## Running the Reference App

Start the app locally:

```bash
uvicorn app.main:app --reload
```

The app will be available at `http://127.0.0.1:8000`.

## Routes

### POST /classify-complexity

Classify message complexity and recommend a model tier.

This route is local and deterministic. It does not call the gateway or the provider.

Example request:

```bash
curl -X POST http://127.0.0.1:8000/classify-complexity \
  -H "Content-Type: application/json" \
  -d '{"message": "What is 2+2?"}'
```

Expected response shape:

```json
{
  "complexity": "simple",
  "recommended_tier": "cheap",
  "needs_escalation": false
}
```

### POST /answer-routed

Generate an answer using routing-based model selection.

This route uses the routing service to choose a logical tier and then calls the gateway.

Example request:

```bash
curl -X POST http://127.0.0.1:8000/answer-routed \
  -H "Content-Type: application/json" \
  -d '{"message": "Analyze the complex implications of quantum computing"}'
```

Expected response shape:

```json
{
  "answer": "string",
  "selected_model": "string",
  "routing_decision": "cheap or expensive"
}
```

### POST /conversation-turn

Process a conversation turn with context strategy application.

This route prepares context locally and then calls the gateway.

Example request:

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

Expected response shape:

```json
{
  "answer": "string",
  "turn_index": 2,
  "context_tokens_used": 15,
  "context_strategy_applied": "full"
}
```

`context_tokens_used` is derived from the current deterministic token-estimation heuristic in `app/services/context_manager.py`.

## Context Strategies

The `/conversation-turn` route supports three context strategies:

- `full`: include all conversation history
- `sliding_window`: keep only the most recent bounded portion
- `summarized`: use deterministic placeholder summarization for older history and keep recent messages verbatim

## Gateway

The app uses a concrete OpenAI-backed gateway for gateway-backed routes.

Current gateway-backed routes:

- `/answer-routed`
- `/conversation-turn`

### Required environment variable for live gateway calls

```bash
export OPENAI_API_KEY="your_key_here"
```

Without a valid API key, live requests to gateway-backed routes will fail.

### Telemetry output

Gateway telemetry is written as JSON lines to:

```text
artifacts/logs/telemetry.jsonl
```

### Example telemetry event shape

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

Run the eval runners from repo root in module mode:

```bash
python3 -m evals.runners.run_classify_eval
python3 -m evals.runners.run_answer_routed_eval
python3 -m evals.runners.run_conversation_turn_eval
```

### Eval artifacts

Eval result files are written to:

```text
artifacts/reports/
```

Expected files:

- `artifacts/reports/classify_eval_results.json`
- `artifacts/reports/answer_routed_eval_results.json`
- `artifacts/reports/conversation_turn_eval_results.json`

### Important eval behavior

- `/classify-complexity` eval runs against the local deterministic route.
- `/answer-routed` eval uses mocked gateway behavior by default.
- `/conversation-turn` eval uses mocked gateway behavior by default.
- Eval execution does not require `OPENAI_API_KEY`.

## Notes on Execution

Use module execution for eval runners:

```bash
python3 -m evals.runners.run_classify_eval
```

Do not rely on direct script execution such as `python3 evals/runners/run_classify_eval.py`, because import resolution may differ depending on the current working path.

## Reporting

Generate operational reports from telemetry and eval artifacts.

The reporting layer is downstream-only: it reads existing artifact files and does not execute routes, call providers, or run evals.

### Single-run report

Generate a report from one telemetry snapshot:

```bash
python3 -m reporting.make_report \
  --after-log artifacts/logs/telemetry.jsonl \
  --output artifacts/reports/report.md
```

### Before/after comparison report

Generate a report comparing two telemetry snapshots:

```bash
python3 -m reporting.make_report \
  --before-log artifacts/logs/before_telemetry.jsonl \
  --after-log artifacts/logs/telemetry.jsonl \
  --output artifacts/reports/report_before_after.md
```

### Include eval results

Optionally include eval summaries in the report:

```bash
python3 -m reporting.make_report \
  --after-log artifacts/logs/telemetry.jsonl \
  --classify-eval artifacts/reports/classify_eval_results.json \
  --answer-eval artifacts/reports/answer_routed_eval_results.json \
  --conversation-eval artifacts/reports/conversation_turn_eval_results.json \
  --output artifacts/reports/report.md
```

### Report artifacts

Generated reports are written to:

```text
artifacts/reports/
```

Typical report outputs include:

- `artifacts/reports/report.md`
- `artifacts/reports/report_before_after.md`

## Verification

Run the following commands to verify the MVP from the routes, gateway, eval, and reporting layers.

### Run eval runners

```bash
python3 -m evals.runners.run_classify_eval
python3 -m evals.runners.run_answer_routed_eval
python3 -m evals.runners.run_conversation_turn_eval
```

### Run focused test modules

```bash
python3 -m pytest tests/test_routes.py -q
python3 -m pytest tests/test_gateway.py -q
python3 -m pytest tests/test_evals.py -q
python3 -m pytest tests/test_reporting.py -q
```

### Run the full test suite

```bash
python3 -m pytest tests/ -q
```

## Main Artifact Paths

Important generated artifact locations:

- `artifacts/logs/telemetry.jsonl`
- `artifacts/reports/classify_eval_results.json`
- `artifacts/reports/answer_routed_eval_results.json`
- `artifacts/reports/conversation_turn_eval_results.json`
- `artifacts/reports/report.md`
- `artifacts/reports/report_before_after.md`

## Scope Notes

This repository is intentionally narrow.

It is not:

- a general-purpose agent framework
- a multi-provider platform
- a notebook-based experimentation repo
- a semantic evaluation suite
- a dashboard product
- a production SaaS system

It is a small, inspectable engineering kit for controlled LLM route behavior, gateway-backed telemetry, bounded regression detection, and markdown reporting.

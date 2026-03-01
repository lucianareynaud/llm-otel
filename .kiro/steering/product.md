# Product Steering

## Project name
LLM Cost Control

## What this project is
A production-grade FastAPI reference implementation for controlling and observing the
operational cost of LLM inference. It demonstrates:

- Route-level cost visibility via OpenTelemetry metrics and JSONL telemetry
- Model routing based on request complexity (keyword heuristic → embedding-based kNN)
- Context-window growth measurement and control across conversation turns
- Semantic caching to eliminate redundant provider billing
- Circuit breaking for resilience under provider degradation
- Server-side conversation persistence with Redis fallback
- Authenticated, rate-limited API surface with health probes for orchestrator compatibility
- Automated quality gates: ruff lint, mypy type checks, pytest regression tests, eval runners

The project exists to prove three operational ideas:
1. A significant fraction of requests can be served by a cheaper model with no quality loss.
2. Multi-turn context growth can be measured, bounded, and controlled at the gateway layer.
3. Route-level telemetry makes cost and reliability trade-offs explicit and comparable.

## What this project is not
- A consumer-facing application
- A multi-tenant SaaS product
- A general-purpose agent platform
- A multi-provider abstraction layer
- A generalized routing framework
- A persistent chat-memory product
- A streaming or function-calling demo
- A dashboard or UI project

## Current state of the project

### Completed (specs 001–004 + OTel hardening)
- Three-route FastAPI app: `/classify-complexity`, `/answer-routed`, `/conversation-turn`
- Gateway choke point: `gateway/client.py` (now `async def`, `AsyncOpenAI`, OTel spans)
- Route-level policies: `gateway/policies.py` (frozen dataclass, model selection, context strategy)
- Cost estimation: `gateway/cost_model.py` (gpt-4o-mini, gpt-4o with real pricing)
- Dual-write telemetry: OTel metrics (primary) + JSONL (secondary for reporting pipeline)
- Eval harness: versioned JSONL datasets, route-specific runners, assertion framework
- Markdown reporting: `reporting/make_report.py` consuming JSONL artifacts
- OpenTelemetry: TracerProvider + MeterProvider, OTLP exporter, FastAPI instrumentation,
  `gen_ai.*` semantic conventions on all LLM spans and metrics
- All gateway tests pass with `isinstance`-based OpenAI error classification

### In progress (specs 005–013)
The production-readiness sequence. Specs must be completed in order:
```
005 → real model names + pricing
006 → health endpoints + CI/CD
007 → auth middleware + rate limiting
008 → async-safe retry (asyncio.sleep)
009 → tiktoken token counting
010 → semantic cache implementation
011 → circuit breaker
012 → server-side conversation persistence
013 → embedding-based routing classifier
```

**The prerequisite gate for each spec is a passing test suite from the prior spec.**
Never start a spec until `OTEL_SDK_DISABLED=true pytest tests/ -v` is fully green.

## Fixed API surface
The following are frozen and must not change under any circumstance:

- The three route paths: `/classify-complexity`, `/answer-routed`, `/conversation-turn`
- All Pydantic request and response schemas for those routes
- The JSONL telemetry format (existing fields must not be removed or renamed)
- The `reporting/make_report.py` interface (reads from artifact paths)
- The eval harness structure (`evals/` datasets and runners)

## Product success criteria
The project is complete when all of the following are true:
1. A live call to `/answer-routed` returns a real OpenAI response (not a 404).
2. Unauthenticated requests return HTTP 401. Over-limit requests return HTTP 429.
3. Health probes work: `/healthz` always 200, `/readyz` 200/503 based on startup state.
4. A PR with a failing test is blocked by CI.
5. A second identical prompt hits the cache (no provider call, `estimated_cost_usd=0`).
6. An open circuit returns HTTP 503 in < 50 ms without a provider call.
7. Server-side conversation history is loaded on the second turn without client retransmission.
8. Embedding-based classifier routes ≥ 90% of a held-out test set correctly.
9. All 182+ tests pass. `ruff` and `mypy` pass on all modified files.
10. A third party can clone, install, and run the full workload without manual intervention.

## Product boundaries — what requires explicit approval to add
- New routes beyond the three existing ones
- New LLM providers beyond OpenAI
- Streaming response support
- Tool/function calling
- A/B testing or prompt versioning
- Distributed tracing across services
- OAuth or multi-user auth
- Dashboard or UI
- Background task queues

## Final constraint
If a proposed change does not improve measurability, reproducibility, cost visibility,
routing clarity, context-control visibility, or regression detection, it belongs outside
this project's scope.

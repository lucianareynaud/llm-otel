# OpenTelemetry Steering

## OTel is already implemented — do not reinitialise it
The OpenTelemetry SDK is fully configured. The following are complete and frozen:
- `gateway/otel_setup.py` — `setup_otel()` / `shutdown_otel()` with BatchSpanProcessor,
  PeriodicExportingMetricReader, OTLP exporter (with console fallback), and resource attributes
- `gateway/telemetry.py` — `emit()` with OTel metrics (primary) + JSONL (secondary)
- `app/main.py` — lifespan handler calling `setup_otel()` then `FastAPIInstrumentor`
- All OTel packages pinned in `requirements.txt`

**Do not add a second `setup_otel()` call. Do not create a second TracerProvider or
MeterProvider. Do not import `set_tracer_provider` or `set_meter_provider` outside
`gateway/otel_setup.py`.**

---

## SDK disable in tests
All test runs must set `OTEL_SDK_DISABLED=true`:
```bash
OTEL_SDK_DISABLED=true pytest tests/ -v
```
This uses the OTel Python SDK's kill-switch. It prevents:
- OTLP exporter connection attempts to a non-existent collector
- BatchSpanProcessor background threads interfering with test teardown
- Console exporter noise polluting test output

In CI, this env var must be set on every test step.

---

## How to add OTel spans

Use the global tracer from `opentelemetry.trace`:
```python
from opentelemetry import trace

_tracer = trace.get_tracer("llm_gateway", version="0.1.0")

with _tracer.start_as_current_span("llm.call", kind=trace.SpanKind.CLIENT) as span:
    span.set_attribute("gen_ai.system", "openai")
    span.set_attribute("gen_ai.request.model", model)
    span.set_attribute("gen_ai.operation.name", "chat")
    try:
        # ... call provider ...
        span.set_attribute("gen_ai.response.model", model)
        span.set_attribute("gen_ai.usage.input_tokens", tokens_in)
        span.set_attribute("gen_ai.usage.output_tokens", tokens_out)
    except Exception as exc:
        span.record_exception(exc)
        span.set_status(trace.Status(trace.StatusCode.ERROR, str(exc)))
        raise
```

The OTel Python proxy pattern means `trace.get_tracer(...)` called at module level is safe —
it upgrades to the real tracer once `setup_otel()` sets the global provider.

---

## Span kind rules

| Span context | SpanKind |
|---|---|
| HTTP request processing (route handler) | `SERVER` — set automatically by `FastAPIInstrumentor` |
| Outgoing LLM provider call | `CLIENT` |
| Internal service call (routing, token counting) | No span — too noisy for the MVP |

Do not add spans to `determine_complexity()`, `prepare_context()`, or `count_tokens()`.
These are synchronous internal calls with sub-millisecond duration and no I/O.

---

## Semantic conventions to follow

All LLM-related spans and metrics must use the `gen_ai.*` semantic conventions from
`opentelemetry-semantic-conventions`:

### Span attributes (from `gateway/client.py` CLIENT span)
| Attribute | Value |
|---|---|
| `gen_ai.system` | `"openai"` |
| `gen_ai.operation.name` | `"chat"` |
| `gen_ai.request.model` | model string (e.g. `"gpt-4o-mini"`) |
| `gen_ai.response.model` | model string (confirmed from response) |
| `gen_ai.usage.input_tokens` | integer |
| `gen_ai.usage.output_tokens` | integer |
| `llm_gateway.route` | route path (e.g. `"/answer-routed"`) |
| `llm_gateway.cache_hit` | `True` / `False` |
| `llm_gateway.circuit_state` | `"closed"` / `"open"` / `"half_open"` |
| `error.type` | error category string (on error spans only) |

### Metrics (from `gateway/telemetry.py`)
| Metric name | Kind | Unit | Description |
|---|---|---|---|
| `gen_ai.client.token.usage` | Histogram | `{token}` | Input + output tokens per call |
| `gen_ai.client.operation.duration` | Histogram | `s` | Wall-clock duration per call |
| `llm_gateway.estimated_cost_usd` | Counter | `USD` | Cumulative estimated cost |
| `llm_gateway.requests` | Counter | `{request}` | Request count by status |

Do not invent new metric names. If a new metric is needed, check the GenAI semantic
conventions specification first.

---

## What FastAPIInstrumentor does automatically
`FastAPIInstrumentor.instrument_app(application, excluded_urls="healthz,readyz")` adds:
- A `SERVER` span for every HTTP request (except the excluded paths)
- W3C `traceparent` header propagation for distributed tracing
- HTTP status code and method as span attributes

You do not need to add route-level spans manually. The instrumentor handles the HTTP layer.

---

## OTLP exporter configuration
The OTLP endpoint is set via env var:
```
OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4318
```

If this env var is not set, `gateway/otel_setup.py` falls back to the console exporter
(prints spans and metrics to stdout). This is intentional — the app must not fail to start
when no collector is running.

---

## Adding new OTel metrics
If a spec requires a new metric, add it to `gateway/telemetry.py` alongside the existing metrics:

```python
_my_new_counter = _meter.create_counter(
    "llm_gateway.my_metric",
    unit="{unit}",
    description="What this counts",
)
```

Then call it inside `emit()` with the appropriate labels (attributes dict).

Do not create meters in route handlers, services, or middleware. All metrics live in
`gateway/telemetry.py`.

---

## JSONL telemetry format (frozen fields)
These fields in the JSONL record must never change name or type:

```json
{
  "timestamp": "ISO-8601 string",
  "route": "/answer-routed",
  "model": "gpt-4o-mini",
  "tokens_in": 42,
  "tokens_out": 128,
  "latency_ms": 834.5,
  "estimated_cost_usd": 0.000094,
  "status": "success",
  "error_type": null,
  "cache_hit": false
}
```

New optional fields may be appended. Existing fields may not be renamed, removed, or change type.
The `reporting/make_report.py` pipeline reads these fields by name — a rename breaks it silently.

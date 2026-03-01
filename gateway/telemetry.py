"""Telemetry emission for the LLM Cost Control gateway.

TWO-LAYER DESIGN
────────────────
This module has two explicitly separated responsibilities:

  Layer 1 — OTel Metrics (PRIMARY observability)
  ────────────────────────────────────────────────
  Records structured metrics using the OpenTelemetry Metrics API. These
  metrics are exported to any configured OTLP backend (Grafana, Datadog,
  Prometheus, …) via the MeterProvider configured in gateway/otel_setup.py.

  The metric instruments follow the OpenTelemetry GenAI Semantic Conventions
  (https://opentelemetry.io/docs/specs/semconv/gen-ai/):

    gen_ai.client.token.usage       — Histogram  — token counts per call
    gen_ai.client.operation.duration — Histogram  — end-to-end latency in seconds
    llm_gateway.estimated_cost_usd  — Counter    — cumulative USD cost
    llm_gateway.requests            — Counter    — total requests by route/status

  Layer 2 — JSONL local artifact (SECONDARY, for reporting pipeline)
  ──────────────────────────────────────────────────────────────────
  Appends one JSON line per call to artifacts/logs/telemetry.jsonl.
  This file is consumed by reporting/make_report.py to generate Markdown
  reports. It is intentionally kept as a simple local file so the reporting
  pipeline works without a running OTel backend.

  This is a deliberate dual-write: OTel for live observability, JSONL for
  batch reporting. The two sinks are kept independent — a failure to write
  JSONL does not suppress OTel metrics, and vice versa.

INSTRUMENT CREATION PATTERN
────────────────────────────
Instruments are created once at module import time via ``metrics.get_meter()``.
Before ``setup_otel()`` is called, this returns a ProxyMeter. When
``setup_otel()`` calls ``metrics.set_meter_provider()``, the ProxyMeter
upgrades to the real SDK implementation transparently (see otel_setup.py
docstring for details). This means no lazy initialisation or global state
guards are needed here.
"""

from __future__ import annotations

import fcntl
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from opentelemetry import metrics

from gateway.semconv import (
    ATTR_GEN_AI_OPERATION_NAME,
    ATTR_GEN_AI_REQUEST_MODEL,
    ATTR_GEN_AI_SYSTEM,
    ATTR_GEN_AI_TOKEN_TYPE,
    ATTR_GEN_AI_USAGE_INPUT_TOKENS,
    ATTR_GEN_AI_USAGE_OUTPUT_TOKENS,
    VAL_GEN_AI_OPERATION_CHAT,
    VAL_GEN_AI_SYSTEM_OPENAI,
    VAL_GEN_AI_TOKEN_TYPE_INPUT,
    VAL_GEN_AI_TOKEN_TYPE_OUTPUT,
    resolve_attrs,
)

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# JSONL artifact path
#
# Critically: resolved relative to THIS FILE's location, not the process CWD.
# Using Path(__file__) makes the path absolute and stable regardless of which
# directory the process is started from (uvicorn ., pytest from parent, etc.).
# ─────────────────────────────────────────────────────────────────────────────
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
TELEMETRY_PATH = _PROJECT_ROOT / "artifacts" / "logs" / "telemetry.jsonl"

# ─────────────────────────────────────────────────────────────────────────────
# OTel Meter — module-level singleton
#
# ``metrics.get_meter(__name__)`` returns a ProxyMeter before setup_otel() runs
# and upgrades to the real MeterProvider-backed meter automatically once
# setup_otel() calls metrics.set_meter_provider(). We include the version so
# backends can group metrics by instrumentation version independently of the
# service version.
# ─────────────────────────────────────────────────────────────────────────────
_meter = metrics.get_meter("llm_gateway", version="0.1.0")

# ─────────────────────────────────────────────────────────────────────────────
# Metric Instruments
#
# Each instrument is a module-level singleton. OTel instruments are thread-safe
# and designed to be created once and reused for the entire process lifetime.
# Creating an instrument with the same name twice on the same meter returns
# the same object, so this is also safe if the module is somehow imported
# multiple times.
# ─────────────────────────────────────────────────────────────────────────────

# gen_ai.client.token.usage
# ─────────────────────────
# Standard GenAI semantic convention histogram for token counts.
# Spec: https://opentelemetry.io/docs/specs/semconv/gen-ai/gen-ai-metrics/
#
# This histogram is recorded twice per successful call:
#   once for input tokens  (attribute gen_ai.token.type = "input")
#   once for output tokens (attribute gen_ai.token.type = "output")
#
# Separating input and output into distinct recordings (rather than summing)
# is mandated by the spec because their cost coefficients differ by model.
# Backends can then compute cost = input_tokens * price_in + output_tokens * price_out.
#
# Unit "{token}" follows the OTel convention for dimensionless counts of
# domain-specific items (curly-braces notation = custom units).
_token_usage_histogram = _meter.create_histogram(
    name="gen_ai.client.token.usage",
    unit="{token}",
    description=(
        "Measures number of input and output tokens used per LLM call. "
        "Recorded separately for input (gen_ai.token.type=input) and "
        "output (gen_ai.token.type=output) to enable per-type cost analysis."
    ),
)

# gen_ai.client.operation.duration
# ─────────────────────────────────
# Standard GenAI semantic convention histogram for end-to-end latency.
# Unit is SECONDS (not milliseconds) — this is the OTel convention for
# durations. Internally the gateway measures latency_ms; we convert on record.
#
# This histogram includes retry wait time (exponential backoff), making it
# the true wall-clock latency experienced by the caller, which is the metric
# that matters for SLO compliance.
_operation_duration_histogram = _meter.create_histogram(
    name="gen_ai.client.operation.duration",
    unit="s",
    description=(
        "Measures end-to-end wall-clock duration of LLM operations including "
        "retries. Unit is seconds per OTel convention."
    ),
)

# llm_gateway.estimated_cost_usd
# ───────────────────────────────
# Custom counter for cumulative USD cost. A Counter is appropriate here
# because cost is monotonically increasing — it can never decrease.
# Backends render this as a rate (cost per second, per minute) or as a
# running total, both of which are useful for cost alerting.
_cost_counter = _meter.create_counter(
    name="llm_gateway.estimated_cost_usd",
    unit="USD",
    description=(
        "Cumulative estimated LLM call cost in USD based on local pricing "
        "snapshot (see gateway/cost_model.py). Not a billing source of truth."
    ),
)

# llm_gateway.requests
# ─────────────────────
# Custom counter for total request volume by route, tier, and status.
# The combination of route + model_tier + status attributes enables:
#   - "how often does /answer-routed go to cheap vs expensive tier?"
#   - "what is the error rate per route?"
#   - "is routing distribution changing over time?"
_request_counter = _meter.create_counter(
    name="llm_gateway.requests",
    unit="{request}",
    description=(
        "Total LLM gateway requests by route, model tier, and outcome status. "
        "Use to track routing distribution and per-route error rates."
    ),
)


def emit(
    request_id: str,
    route: str,
    provider: str,
    model: str,
    latency_ms: float,
    status: Literal["success", "error"],
    tokens_in: int,
    tokens_out: int,
    estimated_cost_usd: float,
    cache_hit: bool = False,
    schema_valid: bool = True,
    error_type: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> None:
    """Emit telemetry for one completed LLM gateway call.

    This function is the single telemetry emission point. It performs two
    actions in sequence:

    1. Records OTel metrics — writes to the MeterProvider instrument buffers.
       These are aggregated in-process and exported to the OTel backend on the
       PeriodicExportingMetricReader interval (default 30 s). Zero I/O on the
       hot path; recording is a pure in-memory operation.

    2. Appends a JSONL line — writes one JSON object to telemetry.jsonl for
       the offline reporting pipeline. This is a synchronous append with a
       file open/write/close cycle. It is intentionally kept simple: the JSONL
       file is a local development artifact, not a production data sink.

    Args:
        request_id:            UUID identifying this specific call.
        route:                 Gateway route name (e.g. "/answer-routed").
        provider:              LLM provider name (e.g. "openai").
        model:                 Concrete model name (e.g. "gpt-4o-mini").
        latency_ms:            Wall-clock duration in milliseconds.
        status:                "success" or "error".
        tokens_in:             Input token count (0 on error).
        tokens_out:            Output token count (0 on error).
        estimated_cost_usd:    Estimated USD cost (0.0 on error).
        cache_hit:             Whether the response was served from cache.
        schema_valid:          Whether the response passed schema validation.
        error_type:            Categorised error type string, or None.
        metadata:              Additional route-specific key-value pairs merged
                               into the JSONL event (e.g. routing_decision).
    """
    _record_otel_metrics(
        route=route,
        model=model,
        latency_ms=latency_ms,
        status=status,
        tokens_in=tokens_in,
        tokens_out=tokens_out,
        estimated_cost_usd=estimated_cost_usd,
        error_type=error_type,
        metadata=metadata,
    )

    _write_jsonl_event(
        request_id=request_id,
        route=route,
        provider=provider,
        model=model,
        latency_ms=latency_ms,
        status=status,
        tokens_in=tokens_in,
        tokens_out=tokens_out,
        estimated_cost_usd=estimated_cost_usd,
        cache_hit=cache_hit,
        schema_valid=schema_valid,
        error_type=error_type,
        metadata=metadata,
    )


def _record_otel_metrics(
    route: str,
    model: str,
    latency_ms: float,
    status: str,
    tokens_in: int,
    tokens_out: int,
    estimated_cost_usd: float,
    error_type: str | None,
    metadata: dict[str, Any] | None,
) -> None:
    """Record all OTel metric instruments for one gateway call.

    WHY THESE SPECIFIC ATTRIBUTES
    ──────────────────────────────
    Attributes on metric recordings become dimensions in the backend's metric
    aggregation. Choosing the right cardinality is critical:

    - High cardinality (e.g. request_id, user_id) should NEVER be an attribute
      because it creates one time-series per unique value, which can exhaust
      backend storage and break ingestion.
    - Low cardinality (e.g. route, model, status) is ideal: a small finite
      set of values, producing a manageable number of time-series.

    All attributes here are low-cardinality: route has 2 values, model has 2,
    status has 2, error_type has 6.

    ATTRIBUTE KEY NAMING
    ─────────────────────
    All gen_ai.* attribute names are imported from ``gateway.semconv``, never
    from ``opentelemetry.semconv._incubating`` directly. This isolates the
    metrics layer from Development-stability GenAI convention renames.
    ``resolve_attrs()`` applies OTEL_SEMCONV_STABILITY_OPT_IN dual-emission
    automatically during any migration window.

    The ``llm_gateway.*`` attributes are custom to this application and stable.
    """
    # ── Shared dimension attributes ──────────────────────────────────────────
    # All four instruments share these base attributes for cross-metric correlation.
    base_attrs: dict[str, Any] = resolve_attrs({
        ATTR_GEN_AI_SYSTEM: VAL_GEN_AI_SYSTEM_OPENAI,
        ATTR_GEN_AI_OPERATION_NAME: VAL_GEN_AI_OPERATION_CHAT,
        ATTR_GEN_AI_REQUEST_MODEL: model,
        "llm_gateway.route": route,
    })

    # ── gen_ai.client.operation.duration ────────────────────────────────────
    # error.type added only on failures per OTel spec.
    duration_attrs = dict(base_attrs)
    if status == "error" and error_type:
        duration_attrs["error.type"] = error_type

    _operation_duration_histogram.record(
        latency_ms / 1000.0,  # convert ms → s per OTel spec
        attributes=duration_attrs,
    )

    # ── gen_ai.client.token.usage ────────────────────────────────────────────
    # Two recordings (input + output) distinguished by gen_ai.token.type.
    # Skipped on error because tokens_in/tokens_out are 0 and would pollute histograms.
    if status == "success":
        _token_usage_histogram.record(
            tokens_in,
            attributes=resolve_attrs({
                **base_attrs,
                ATTR_GEN_AI_TOKEN_TYPE: VAL_GEN_AI_TOKEN_TYPE_INPUT,
                ATTR_GEN_AI_USAGE_INPUT_TOKENS: tokens_in,
            }),
        )
        _token_usage_histogram.record(
            tokens_out,
            attributes=resolve_attrs({
                **base_attrs,
                ATTR_GEN_AI_TOKEN_TYPE: VAL_GEN_AI_TOKEN_TYPE_OUTPUT,
                ATTR_GEN_AI_USAGE_OUTPUT_TOKENS: tokens_out,
            }),
        )

    # ── llm_gateway.estimated_cost_usd ──────────────────────────────────────
    model_tier = (metadata or {}).get("routing_decision", "unknown")

    _cost_counter.add(
        estimated_cost_usd,
        attributes={
            ATTR_GEN_AI_SYSTEM: VAL_GEN_AI_SYSTEM_OPENAI,
            ATTR_GEN_AI_REQUEST_MODEL: model,
            "llm_gateway.route": route,
            "llm_gateway.model_tier": model_tier,
        },
    )

    # ── llm_gateway.requests ─────────────────────────────────────────────────
    # Increment by 1 for every call regardless of success/failure.
    # The status attribute makes this a multi-dimensional counter from which
    # backends can derive error_rate = error / (success + error).
    _request_counter.add(
        1,
        attributes={
            "llm_gateway.route": route,
            "llm_gateway.model_tier": model_tier,
            "status": status,
        },
    )


def _write_jsonl_event(
    request_id: str,
    route: str,
    provider: str,
    model: str,
    latency_ms: float,
    status: str,
    tokens_in: int,
    tokens_out: int,
    estimated_cost_usd: float,
    cache_hit: bool,
    schema_valid: bool,
    error_type: str | None,
    metadata: dict[str, Any] | None,
) -> None:
    """Append one telemetry event as a JSON line to the local artifact file.

    This is the secondary (reporting-pipeline) emission layer. The JSONL file
    at artifacts/logs/telemetry.jsonl is consumed by reporting/make_report.py
    to generate Markdown cost and latency reports.

    JSONL format: one complete JSON object per line, no trailing comma.
    This format is append-friendly (no need to parse existing content to add a
    new record) and readable by tools like jq, DuckDB, pandas read_json, etc.

    The ``metadata`` dict is merged (flat) into the event object. This allows
    route-specific fields (routing_decision, conversation_id, turn_index, …)
    to appear as top-level keys in the JSONL record without requiring the
    telemetry schema to enumerate every possible route field.

    PATH NOTE: TELEMETRY_PATH is resolved relative to this file's directory
    (see module top) so it is stable regardless of process CWD.
    """
    event: dict[str, Any] = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "request_id": request_id,
        "route": route,
        "provider": provider,
        "model": model,
        "latency_ms": latency_ms,
        "status": status,
        "tokens_in": tokens_in,
        "tokens_out": tokens_out,
        "estimated_cost_usd": estimated_cost_usd,
        "cache_hit": cache_hit,
        "schema_valid": schema_valid,
        "error_type": error_type,
    }

    if metadata:
        # Flat merge: metadata keys overwrite base event keys on collision.
        # This is intentional — routes can override base fields if needed.
        event.update(metadata)

    TELEMETRY_PATH.parent.mkdir(parents=True, exist_ok=True)

    with TELEMETRY_PATH.open("a", encoding="utf-8") as fh:
        # Advisory exclusive lock so concurrent uvicorn workers cannot interleave
        # partial JSON lines. fcntl.LOCK_EX blocks until the lock is acquired;
        # LOCK_UN is released automatically when the file handle is closed.
        # This is a POSIX advisory lock — it does not prevent access from
        # processes that do not also call fcntl.flock (e.g. log tailers).
        fcntl.flock(fh, fcntl.LOCK_EX)
        json.dump(event, fh, ensure_ascii=False)
        fh.write("\n")

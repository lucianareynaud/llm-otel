"""OpenTelemetry provider initialisation for the LLM Cost Control gateway.

WHY THIS MODULE EXISTS
──────────────────────
OpenTelemetry separates the *API* (how you record telemetry — create spans,
record metrics) from the *SDK* (how telemetry is processed and exported).
Library code depends only on the API; this module owns the SDK configuration.

It creates and registers the global TracerProvider and MeterProvider so that
every call to ``opentelemetry.trace.get_tracer()`` or
``opentelemetry.metrics.get_meter()`` anywhere in the process returns
instruments backed by a real, configured SDK — not the default no-op.

PROVIDER HIERARCHY
──────────────────
  Resource  (service.name, service.version, deployment.environment)
    ├── TracerProvider
    │     └── BatchSpanProcessor
    │           └── OTLPSpanExporter  (primary: sends to OTLP receiver)
    │               or ConsoleSpanExporter  (fallback: prints to stdout)
    └── MeterProvider
          └── PeriodicExportingMetricReader
                └── OTLPMetricExporter  (primary)
                    or ConsoleMetricExporter  (fallback)

CONFIGURATION  —  standard OTel environment variables, zero-code config
─────────────────────────────────────────────────────────────────────────
  OTEL_SERVICE_NAME            logical service name  (default: llm-cost-control)
  OTEL_SERVICE_VERSION         deployed version      (default: 0.1.0)
  OTEL_DEPLOYMENT_ENVIRONMENT  e.g. production, staging (default: development)
  OTEL_EXPORTER_OTLP_ENDPOINT  OTLP receiver base URL  (e.g. http://localhost:4318)
  OTEL_EXPORTER_OTLP_HEADERS   auth headers  (e.g. "Authorization=Bearer <token>")
  OTEL_METRIC_EXPORT_INTERVAL  metric flush interval in ms  (default: 30000)
  OTEL_SDK_DISABLED            set "true" to silence all OTel (useful in CI)

OTLP COMPATIBILITY
──────────────────
The OTLP HTTP exporter is backend-agnostic. The same code works unchanged
with Grafana Cloud, Datadog OTLP ingest, Jaeger, New Relic, Honeycomb, or a
self-hosted OpenTelemetry Collector. Only the env vars change between envs.

If OTEL_EXPORTER_OTLP_ENDPOINT is not set, both exporters fall back to the
Console variant, which prints human-readable telemetry to stdout. This is the
correct behaviour for local development — traces are never silently dropped.

PROXY METER / TRACER — WHY MODULE-LEVEL INSTRUMENT CREATION IS SAFE
────────────────────────────────────────────────────────────────────
The OTel Python SDK implements a "proxy" pattern for the global API. Before
``setup_otel()`` is called, ``trace.get_tracer()`` and ``metrics.get_meter()``
return ProxyTracer / ProxyMeter objects. These objects buffer any instrument
creations internally. When ``setup_otel()`` calls ``set_tracer_provider()`` /
``set_meter_provider()``, all proxy objects upgrade to the real SDK
implementation transparently. This means other modules (telemetry.py,
client.py) can safely call ``get_tracer()`` / ``get_meter()`` at module
import time, before this setup runs, and still get live instruments.
"""

from __future__ import annotations

import logging
import os
from typing import Optional

from opentelemetry import metrics, trace
from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import (
    ConsoleMetricExporter,
    PeriodicExportingMetricReader,
)
from opentelemetry.sdk.resources import (
    DEPLOYMENT_ENVIRONMENT,
    SERVICE_NAME,
    SERVICE_VERSION,
    Resource,
)
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter

logger = logging.getLogger(__name__)

# Metric export interval in milliseconds.
# In production, lower this (e.g. 10 000 = 10 s) for tighter observability.
# Controlled via env var so it can be adjusted without code changes.
_METRIC_EXPORT_INTERVAL_MS = int(os.getenv("OTEL_METRIC_EXPORT_INTERVAL", "30000"))

# Module-level provider references kept for clean shutdown.
_tracer_provider: Optional[TracerProvider] = None
_meter_provider: Optional[MeterProvider] = None


def _build_resource() -> Resource:
    """Build the OTel Resource describing this service instance.

    A Resource is a set of key-value attributes that identify the entity
    producing telemetry. Every span and metric emitted by this process
    carries these attributes, which observability backends use for:

    - Filtering: "show me only spans from service llm-cost-control"
    - Release correlation: "did latency change after version 0.2.0?"
    - Environment isolation: "production vs staging metrics"

    The three attributes used here are part of the stable OTel Resource
    Semantic Conventions (resource.schema_url v1.25.0+).
    """
    return Resource.create(
        {
            # service.name  →  groups all telemetry for this logical service
            SERVICE_NAME: os.getenv("OTEL_SERVICE_NAME", "llm-cost-control"),
            # service.version  →  enables release-based analysis
            SERVICE_VERSION: os.getenv("OTEL_SERVICE_VERSION", "0.1.0"),
            # deployment.environment  →  separates prod/staging/dev in backend UI
            DEPLOYMENT_ENVIRONMENT: os.getenv("OTEL_DEPLOYMENT_ENVIRONMENT", "development"),
        }
    )


def _build_span_exporter():
    """Build the SpanExporter appropriate for the current environment.

    The OTLPSpanExporter sends spans to any OTel-compatible backend using
    the OpenTelemetry Protocol over HTTP/protobuf. It automatically reads:
      - OTEL_EXPORTER_OTLP_ENDPOINT  (e.g. http://localhost:4318)
      - OTEL_EXPORTER_OTLP_HEADERS   (e.g. for auth tokens)

    We use HTTP/protobuf (not gRPC) to avoid pulling in the heavy grpcio
    dependency. Both transports are fully spec-compliant; the only difference
    is the port (4318 for HTTP, 4317 for gRPC).

    ConsoleSpanExporter is the local-dev fallback — it prints spans as
    human-readable JSON to stdout so developers can see traces immediately
    without running a collector.
    """
    otlp_endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT")
    if otlp_endpoint:
        logger.info("OTel traces: OTLP HTTP exporter → %s", otlp_endpoint)
        # OTLPSpanExporter picks up OTEL_EXPORTER_OTLP_ENDPOINT and
        # OTEL_EXPORTER_OTLP_HEADERS automatically from the environment.
        return OTLPSpanExporter()

    logger.info(
        "OTel traces: OTEL_EXPORTER_OTLP_ENDPOINT not set — "
        "falling back to ConsoleSpanExporter (stdout)"
    )
    return ConsoleSpanExporter()


def _build_metric_exporter():
    """Build the MetricExporter appropriate for the current environment.

    Follows the same OTLP-or-console fallback pattern as the span exporter.
    The PeriodicExportingMetricReader calls this exporter on a fixed interval
    to push aggregated metric data (histograms, counters) to the backend.
    """
    otlp_endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT")
    if otlp_endpoint:
        logger.info("OTel metrics: OTLP HTTP exporter → %s", otlp_endpoint)
        return OTLPMetricExporter()

    logger.info(
        "OTel metrics: OTEL_EXPORTER_OTLP_ENDPOINT not set — "
        "falling back to ConsoleMetricExporter (stdout)"
    )
    return ConsoleMetricExporter()


def setup_otel() -> None:
    """Initialise and register the global OTel TracerProvider and MeterProvider.

    Must be called once at application startup, before any instrumented code
    runs. In FastAPI, call this from the lifespan handler's startup section.
    Subsequent calls are safe no-ops — the check on ``_tracer_provider``
    prevents double-initialisation.

    What this function does, step by step:

    1. Reads OTEL_SDK_DISABLED — if "true", returns immediately with no-op
       providers. This is the standard way to silence OTel in unit tests
       without mocking anything.

    2. Builds a shared Resource describing this service instance.

    3. Creates a TracerProvider with a BatchSpanProcessor.
       BatchSpanProcessor is the production-grade span processor: it collects
       completed spans in a bounded in-memory queue and exports them to the
       backend asynchronously in batches. The hot path (request handling) is
       never blocked by I/O to the OTel backend.

    4. Calls ``trace.set_tracer_provider()`` to register the TracerProvider
       globally. After this call, any code that does
       ``opentelemetry.trace.get_tracer("name")`` gets a real tracer.

    5. Creates a MeterProvider with a PeriodicExportingMetricReader.
       The reader wakes up on the configured interval, reads the current
       state of all registered instruments (counters, histograms), and
       exports the aggregated data to the backend.

    6. Calls ``metrics.set_meter_provider()`` to register it globally.
       After this call, any code that does
       ``opentelemetry.metrics.get_meter("name")`` gets a real meter.
    """
    global _tracer_provider, _meter_provider

    # Guard: already initialised — do nothing.
    if _tracer_provider is not None:
        return

    # Standard OTel kill-switch. Set OTEL_SDK_DISABLED=true in test
    # environments where you want zero OTel overhead and no stdout noise.
    if os.getenv("OTEL_SDK_DISABLED", "").lower() == "true":
        logger.info("OTel: SDK disabled via OTEL_SDK_DISABLED=true — no-op providers active")
        return

    resource = _build_resource()

    # ── Tracer Provider ──────────────────────────────────────────────────────
    # BatchSpanProcessor buffers spans in memory and exports them in background
    # batches. This is always preferred over SimpleSpanProcessor in production
    # because it decouples span export I/O from the request hot path.
    _tracer_provider = TracerProvider(resource=resource)
    _tracer_provider.add_span_processor(
        BatchSpanProcessor(_build_span_exporter())
    )
    # Register as global. Any call to ``trace.get_tracer()`` anywhere in this
    # process now returns a tracer backed by this provider.
    trace.set_tracer_provider(_tracer_provider)

    # ── Meter Provider ───────────────────────────────────────────────────────
    # PeriodicExportingMetricReader reads all registered instruments at the
    # configured interval and pushes aggregated data to the exporter.
    # The interval is intentionally long (30 s default) to batch many requests
    # into a single export payload, reducing backend write pressure.
    metric_reader = PeriodicExportingMetricReader(
        _build_metric_exporter(),
        export_interval_millis=_METRIC_EXPORT_INTERVAL_MS,
    )
    _meter_provider = MeterProvider(resource=resource, metric_readers=[metric_reader])
    # Register as global.
    metrics.set_meter_provider(_meter_provider)

    logger.info(
        "OTel: initialised (service=%s  version=%s  env=%s  metric_interval=%dms)",
        os.getenv("OTEL_SERVICE_NAME", "llm-cost-control"),
        os.getenv("OTEL_SERVICE_VERSION", "0.1.0"),
        os.getenv("OTEL_DEPLOYMENT_ENVIRONMENT", "development"),
        _METRIC_EXPORT_INTERVAL_MS,
    )


def shutdown_otel() -> None:
    """Flush in-flight telemetry and shut down all providers cleanly.

    Must be called on application shutdown. Without this, the last N seconds
    of spans (held in BatchSpanProcessor's queue) and the last metric
    export cycle are silently lost when the process exits.

    In FastAPI, call this from the lifespan handler's cleanup section (after
    the ``yield``). The ASGI server guarantees the lifespan cleanup runs
    before the process terminates.
    """
    global _tracer_provider, _meter_provider

    if _tracer_provider is not None:
        # shutdown() flushes the BatchSpanProcessor queue synchronously.
        _tracer_provider.shutdown()
        _tracer_provider = None

    if _meter_provider is not None:
        # shutdown() triggers a final metric export cycle.
        _meter_provider.shutdown()
        _meter_provider = None

    logger.info("OTel: providers flushed and shut down")

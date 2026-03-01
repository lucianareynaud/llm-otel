"""Main FastAPI application for the LLM Cost Control reference app.

OTEL INTEGRATION POINTS
────────────────────────
Two OTel integration points live in this file:

1. Lifespan handler
   ─────────────────
   ``setup_otel()`` is called at startup (before any request is served) and
   ``shutdown_otel()`` is called at shutdown (after the last request completes).
   This ensures that:
   - The global TracerProvider and MeterProvider are configured before any
     span or metric instrument is first used.
   - All in-flight spans and buffered metric data are flushed to the OTel
     backend before the process exits. Without the shutdown call, the
     BatchSpanProcessor's queue may be silently discarded on exit.

2. FastAPIInstrumentor
   ────────────────────
   ``FastAPIInstrumentor.instrument_app(app)`` wraps every route handler in
   an OTel span automatically. It also:

   - Extracts W3C Trace Context headers (``traceparent``, ``tracestate``)
     from incoming requests. If a calling service (e.g. an API gateway or a
     load generator) propagates these headers, the HTTP span becomes a child
     of the caller's trace — enabling end-to-end distributed tracing across
     service boundaries.

   - Injects ``traceparent`` into outgoing responses so callers can correlate
     their traces with the spans created here.

   - Records standard HTTP span attributes: http.method, http.route,
     http.status_code, http.url, net.host.name, etc.

   The resulting trace for a routed request looks like:

     POST /answer-routed  [kind=SERVER, FastAPIInstrumentor]
       └── chat gpt-4o-mini  [kind=CLIENT, gateway/client.py]

   The child CLIENT span is linked to the SERVER span because both run on
   the same OS thread and share the same OTel context. FastAPIInstrumentor
   sets the context when the request arrives; ``call_llm`` reads it when
   it opens its span.

INSTRUMENTATION CALL ORDER
───────────────────────────
``setup_otel()`` must be called before ``FastAPIInstrumentor.instrument_app()``.
If the order is reversed, the HTTP spans created by the instrumentation would
use the ProxyTracer (which upgrades later), but the spans would be created
against a no-op provider and might not record correctly on all SDK versions.
Calling setup first guarantees the TracerProvider is fully configured before
any span is created.
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

from app.routes import answer_routed, classify_complexity, conversation_turn, health
from app.routes.health import set_ready
from gateway.otel_setup import setup_otel, shutdown_otel


@asynccontextmanager
async def lifespan(application: FastAPI):
    """FastAPI lifespan handler for startup and shutdown hooks.

    Using the lifespan pattern (rather than deprecated ``on_event`` decorators)
    is the current FastAPI best practice. The ASGI server (uvicorn) guarantees:
    - Code before ``yield`` runs before the first request is accepted.
    - Code after ``yield`` runs after the last request completes and before
      the process exits.

    This guarantee makes it safe to initialise OTel here — all instrumentation
    is ready before any request triggers a span creation.
    """
    # STARTUP ─────────────────────────────────────────────────────────────────
    # 1. Configure global TracerProvider + MeterProvider.
    #    Must happen before instrument_app() so the HTTP spans are backed by
    #    the real SDK provider, not the ProxyTracer.
    setup_otel()

    # 2. Mark the process as ready so /readyz returns 200.
    set_ready(True)

    # 3. Wrap every FastAPI route handler in an OTel SERVER span.
    #    health paths are excluded — they must never fail due to OTel state.
    FastAPIInstrumentor.instrument_app(application, excluded_urls="healthz,readyz")

    yield

    # SHUTDOWN ────────────────────────────────────────────────────────────────
    # Signal not-ready immediately so load balancers stop routing before teardown.
    set_ready(False)

    # Flush BatchSpanProcessor queue and PeriodicExportingMetricReader.
    # Without this, the last N seconds of telemetry are silently discarded.
    shutdown_otel()

    # Undo FastAPIInstrumentor patches so the app can be cleanly restarted
    # in tests without duplicate instrumentation warnings.
    FastAPIInstrumentor.uninstrument_app(application)


app = FastAPI(
    title="LLM Cost Control Reference App",
    version="0.1.0",
    description="Minimal reference app for measuring LLM cost, routing, and context behaviour",
    lifespan=lifespan,
)

app.include_router(health.router)
app.include_router(classify_complexity.router, tags=["classification"])
app.include_router(answer_routed.router, tags=["routing"])
app.include_router(conversation_turn.router, tags=["conversation"])

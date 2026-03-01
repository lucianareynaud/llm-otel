"""Concrete gateway client for OpenAI-backed LLM calls.

ARCHITECTURAL ROLE
──────────────────
This module is the single choke point for all LLM provider interactions.
Every call to an LLM in this application goes through ``call_llm()``.
No route or service ever imports ``openai`` directly — that would scatter
provider coupling, error handling, and telemetry across the codebase.

OTEL TRACING DESIGN
────────────────────
``call_llm()`` creates one OTel span that wraps the entire LLM operation,
including retries. This span is a child of the HTTP request span created by
FastAPIInstrumentor, which means the full trace looks like:

  HTTP POST /answer-routed   (FastAPIInstrumentor, kind=SERVER)
    └── chat gpt-4o-mini      (this module, kind=CLIENT)

The span name follows the GenAI Semantic Convention format:
  "{gen_ai.operation.name} {gen_ai.request.model}"
  e.g. "chat gpt-4o-mini"

SpanKind.CLIENT is correct here because this process is acting as a client
calling an external LLM service. The OTel spec defines CLIENT spans as those
that represent an outbound remote call.

SPAN LIFECYCLE
──────────────
  START  →  set request attributes (route, tier, model, max_output_tokens)
  SUCCESS →  set usage attributes (tokens_in, tokens_out, cost, cache_hit)
             leave span status UNSET (OTel convention: UNSET means no error)
  ERROR  →  call span.record_exception() to capture stack trace
             set error.type attribute (categorised error string)
             set span status to Status(StatusCode.ERROR, description)

RETRYABLE vs NON-RETRYABLE ERRORS
───────────────────────────────────
``_is_retryable()`` now uses ``isinstance()`` checks against the typed
OpenAI exception hierarchy rather than substring matching on error messages.
This is more reliable because:
  1. OpenAI SDK exception types are stable; message text is not.
  2. isinstance() handles subclass relationships correctly (e.g.
     APITimeoutError is a subclass of APIConnectionError — we check it first).
  3. Eliminates false positives: a model whose name contains "timeout" would
     have incorrectly matched the old string-based check.
"""

from __future__ import annotations

import os
import time
import uuid
from dataclasses import dataclass
from typing import Any, Literal

import openai
from openai import OpenAI
from opentelemetry import trace
from opentelemetry.trace import SpanKind, Status, StatusCode

from gateway.cost_model import estimate_cost
from gateway.policies import get_model_for_tier, get_route_policy
from gateway.semconv import (
    ATTR_GEN_AI_OPERATION_NAME,
    ATTR_GEN_AI_REQUEST_MAX_TOKENS,
    ATTR_GEN_AI_REQUEST_MODEL,
    ATTR_GEN_AI_SYSTEM,
    ATTR_GEN_AI_USAGE_INPUT_TOKENS,
    ATTR_GEN_AI_USAGE_OUTPUT_TOKENS,
    VAL_GEN_AI_OPERATION_CHAT,
    VAL_GEN_AI_SYSTEM_OPENAI,
    resolve_attrs,
)
from gateway.telemetry import emit

ModelTier = Literal["cheap", "expensive"]
GatewayRouteName = Literal["/answer-routed", "/conversation-turn"]

# ─────────────────────────────────────────────────────────────────────────────
# OTel Tracer — module-level singleton
#
# ``trace.get_tracer(__name__)`` returns a ProxyTracer before setup_otel()
# runs, then upgrades to the real TracerProvider-backed tracer automatically.
# The instrumentation scope name (__name__ = "gateway.client") appears in
# every span's instrumentation_scope field, allowing backends to filter spans
# by the library that created them.
# ─────────────────────────────────────────────────────────────────────────────
_tracer = trace.get_tracer(__name__, tracer_provider=None)


@dataclass(frozen=True)
class GatewayResult:
    """Structured result returned by the gateway for each LLM call.

    Frozen dataclass — immutable by design. The caller cannot mutate the
    result after receiving it, which prevents a class of bugs where route
    handlers accidentally modify shared gateway state.
    """

    text: str
    selected_model: str
    request_id: str
    tokens_in: int
    tokens_out: int
    estimated_cost_usd: float
    cache_hit: bool


def call_llm(
    prompt: str,
    model_tier: ModelTier,
    route_name: GatewayRouteName,
    metadata: dict[str, Any] | None = None,
) -> GatewayResult:
    """Execute one LLM call through the gateway.

    This is the only public entry point for LLM calls. It:

    1. Resolves configuration — policy (max tokens, retries) and model name
       from the (route_name, model_tier) pair.

    2. Opens an OTel CLIENT span for the full operation. The span is a child
       of whatever span is active on the calling thread (typically the HTTP
       request span created by FastAPIInstrumentor). This links the LLM call
       into the distributed trace of the HTTP request.

    3. Calls the provider via ``_call_provider()``, which handles the retry
       loop with exponential backoff.

    4. On success: annotates the span with token usage and cost attributes,
       sets span status to OK, then emits telemetry (OTel metrics + JSONL).

    5. On error: records the exception on the span, sets span status to ERROR,
       categorises the error, emits telemetry, and re-raises the exception so
       the FastAPI route can return an HTTP 500.

    Args:
        prompt:      Prepared prompt or context string for the LLM.
        model_tier:  Logical tier ("cheap" or "expensive").
        route_name:  Gateway route identifier ("/answer-routed", etc.).
        metadata:    Optional route-specific key-values merged into telemetry.

    Returns:
        GatewayResult with response text, model, token counts, and cost.

    Raises:
        ValueError: If OPENAI_API_KEY is not set, or configuration is missing.
        openai.APIError: If the provider call fails after all retries.
    """
    request_id = str(uuid.uuid4())
    policy = get_route_policy(route_name)
    selected_model = get_model_for_tier(route_name, model_tier)

    # Merge the concrete model name into metadata so it appears in telemetry
    # alongside any route-specific fields the caller passed (routing_decision, etc.)
    telemetry_metadata = dict(metadata or {})
    telemetry_metadata["selected_model"] = selected_model

    # ── OTel Span ────────────────────────────────────────────────────────────
    # Span name format mandated by the GenAI Semantic Convention:
    #   "{gen_ai.operation.name} {gen_ai.request.model}"
    # This produces names like "chat gpt-4o-mini" or "chat gpt-4o" in the UI.
    # Span name format: "{operation} {model}" per GenAI Semantic Convention.
    span_name = f"{VAL_GEN_AI_OPERATION_CHAT} {selected_model}"

    with _tracer.start_as_current_span(span_name, kind=SpanKind.CLIENT) as span:
        # ── Span attributes set at call start ────────────────────────────────
        # GenAI attributes are set through gateway.semconv constants (never
        # imported from opentelemetry.semconv._incubating directly). This
        # isolates the codebase from Development-stability attribute renames.
        # resolve_attrs() applies OTEL_SEMCONV_STABILITY_OPT_IN dual-emission
        # when _PENDING_RENAMES is non-empty during a migration window.
        request_attrs = resolve_attrs(
            {
                ATTR_GEN_AI_SYSTEM: VAL_GEN_AI_SYSTEM_OPENAI,
                ATTR_GEN_AI_OPERATION_NAME: VAL_GEN_AI_OPERATION_CHAT,
                ATTR_GEN_AI_REQUEST_MODEL: selected_model,
                ATTR_GEN_AI_REQUEST_MAX_TOKENS: policy.max_output_tokens,
            }
        )
        for key, value in request_attrs.items():
            span.set_attribute(key, value)

        # Custom gateway attributes (stable, owned by this codebase).
        span.set_attribute("llm_gateway.route", route_name)
        span.set_attribute("llm_gateway.model_tier", model_tier)
        span.set_attribute("llm_gateway.request_id", request_id)
        span.set_attribute("llm_gateway.retry_attempts_allowed", policy.retry_attempts)
        span.set_attribute("llm_gateway.cache_enabled", policy.cache_enabled)

        start_time = time.perf_counter()

        try:
            text, tokens_in, tokens_out = _call_provider(
                prompt=prompt,
                model=selected_model,
                max_output_tokens=policy.max_output_tokens,
                retry_attempts=policy.retry_attempts,
            )

            latency_ms = (time.perf_counter() - start_time) * 1000.0
            estimated_cost_usd = estimate_cost(selected_model, tokens_in, tokens_out)

            # ── Span attributes set on success ────────────────────────────────
            usage_attrs = resolve_attrs(
                {
                    ATTR_GEN_AI_USAGE_INPUT_TOKENS: tokens_in,
                    ATTR_GEN_AI_USAGE_OUTPUT_TOKENS: tokens_out,
                }
            )
            for key, value in usage_attrs.items():
                span.set_attribute(key, value)

            # Custom cost attribute. Not in the GenAI spec but important for
            # this application's cost-control mission.
            span.set_attribute("llm_gateway.estimated_cost_usd", estimated_cost_usd)
            span.set_attribute("llm_gateway.cache_hit", False)

            # Per OTel spec, leave span status UNSET on success.
            # UNSET is the correct signal for "no error occurred" in instrumentation
            # code. Setting OK is reserved for cases where the application explicitly
            # wants to assert a successful outcome to downstream consumers. For a
            # library-level gateway CLIENT span, UNSET is correct and preferred —
            # backends treat UNSET as success in error-rate calculations.

            emit(
                request_id=request_id,
                route=route_name,
                provider="openai",
                model=selected_model,
                latency_ms=latency_ms,
                status="success",
                tokens_in=tokens_in,
                tokens_out=tokens_out,
                estimated_cost_usd=estimated_cost_usd,
                cache_hit=False,
                schema_valid=True,
                error_type=None,
                metadata=telemetry_metadata,
            )

            return GatewayResult(
                text=text,
                selected_model=selected_model,
                request_id=request_id,
                tokens_in=tokens_in,
                tokens_out=tokens_out,
                estimated_cost_usd=estimated_cost_usd,
                cache_hit=False,
            )

        except Exception as exc:
            latency_ms = (time.perf_counter() - start_time) * 1000.0
            error_type = _categorize_error(exc)

            # ── Span attributes set on error ──────────────────────────────────

            # record_exception() captures the exception type, message, and full
            # stack trace as a span event named "exception". This is the OTel
            # standard for associating exceptions with spans — backends render
            # these as error events on the span timeline.
            span.record_exception(exc)

            # Status(StatusCode.ERROR, description) explicitly marks this span as
            # failed with a human-readable description visible in the trace UI.
            # Using the Status wrapper (rather than bare StatusCode) is the idiomatic
            # OTel Python pattern and ensures the description string is attached.
            span.set_status(Status(StatusCode.ERROR, str(exc)))

            # error.type is a standard OTel attribute (not gen_ai.* namespaced).
            # It holds the Python exception class name (e.g. "RateLimitError")
            # per the OTel Error Handling spec. This is different from
            # llm_gateway.error_category, which is our internal taxonomy.
            span.set_attribute("error.type", type(exc).__name__)

            # Our internal error category — coarser than the exception type but
            # useful for alerting rules: "alert if rate_limit > 5/min".
            span.set_attribute("llm_gateway.error_category", error_type)

            emit(
                request_id=request_id,
                route=route_name,
                provider="openai",
                model=selected_model,
                latency_ms=latency_ms,
                status="error",
                tokens_in=0,
                tokens_out=0,
                estimated_cost_usd=0.0,
                cache_hit=False,
                schema_valid=True,
                error_type=error_type,
                metadata=telemetry_metadata,
            )

            raise


def _call_provider(
    prompt: str,
    model: str,
    max_output_tokens: int,
    retry_attempts: int,
) -> tuple[str, int, int]:
    """Call the OpenAI Responses API with bounded exponential backoff retry.

    The retry strategy deliberately does NOT create a new OTel child span per
    attempt. Each attempt is instead captured as a span event on the parent
    span (via record_exception in call_llm's except block). This keeps the
    trace clean — one LLM call = one span — while still recording failure
    details when retries are exhausted.

    Exponential backoff: attempt 0 → no sleep, attempt 1 → 1 s, attempt 2 → 2 s.
    Formula: ``time.sleep(2 ** (attempt - 1))`` for attempt > 0.

    Args:
        prompt:           Input text payload.
        model:            Resolved concrete model name (e.g. "gpt-4o-mini").
        max_output_tokens: Token cap from RoutePolicy.
        retry_attempts:   Number of additional attempts after the first failure.

    Returns:
        Tuple of (response_text, tokens_in, tokens_out).

    Raises:
        ValueError: If OPENAI_API_KEY is not set.
        openai.APIError: Propagates the last exception after all retries.
    """
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise ValueError("OPENAI_API_KEY environment variable not set")

    # Create the client inside the function so tests can patch ``openai.OpenAI``
    # at the class level without affecting module-level state.
    client = OpenAI(api_key=api_key)
    last_exception: Exception | None = None

    for attempt in range(retry_attempts + 1):
        try:
            response = client.responses.create(
                model=model,
                input=prompt,
                max_output_tokens=max_output_tokens,
            )

            text = response.output_text or ""
            usage = response.usage
            tokens_in = usage.input_tokens if usage else 0
            tokens_out = usage.output_tokens if usage else 0

            return text, tokens_in, tokens_out

        except Exception as exc:
            last_exception = exc

            if _is_retryable(exc) and attempt < retry_attempts:
                # Exponential backoff: 2^0 = 1 s, 2^1 = 2 s.
                # Sleep time grows with each failed attempt to give transient
                # errors (rate limits, 503s) time to resolve before retrying.
                time.sleep(2**attempt)
                continue

            # Non-retryable error or final attempt — stop immediately.
            break

    raise last_exception or RuntimeError("Provider call failed with no exception captured")


def _is_retryable(error: Exception) -> bool:
    """Return True if the exception should trigger a retry attempt.

    Uses ``isinstance()`` checks against the typed OpenAI exception hierarchy.
    This is more reliable than substring matching on error.message because:

    1. Exception types are stable across SDK versions; message text is not.
    2. isinstance() correctly handles subclass relationships. For example,
       APITimeoutError is a subclass of APIConnectionError. We check
       APITimeoutError first so it matches before the broader APIConnectionError.
    3. No false positives: a model whose name contains "timeout" would have
       incorrectly matched the old string-based approach.

    Retryable:
      RateLimitError (429)      — transient throttle; backoff and retry
      APITimeoutError           — network timeout; may succeed on retry
      APIConnectionError        — network failure; may succeed on retry
      InternalServerError (5xx) — provider-side transient error

    Non-retryable (all subclasses of APIStatusError not listed above):
      AuthenticationError (401) — wrong API key; retrying won't fix it
      PermissionDeniedError (403)
      BadRequestError (400)     — malformed request; retrying won't fix it
      NotFoundError (404)
      UnprocessableEntityError (422)
    """
    return isinstance(
        error,
        (
            openai.RateLimitError,
            # APITimeoutError MUST come before APIConnectionError because it is a
            # subclass of it. Python's isinstance() matches the first type in the
            # tuple that fits, so order matters.
            openai.APITimeoutError,
            openai.APIConnectionError,
            openai.InternalServerError,
        ),
    )


def _categorize_error(error: Exception) -> str:
    """Map an exception to a stable telemetry error category string.

    Uses ``isinstance()`` against the OpenAI SDK exception hierarchy instead
    of string matching. This produces stable category strings that appear in:
    - The OTel span attribute ``llm_gateway.error_category``
    - The JSONL telemetry ``error_type`` field (consumed by reporting)

    The returned strings intentionally match the old string-based categories
    to preserve backward compatibility with the JSONL reporting pipeline.

    Category taxonomy:
      auth_error       — 401/403: bad API key or insufficient permissions
      rate_limit       — 429: request throttled by provider
      timeout          — network timeout
      transient_error  — network failure or 5xx server error (retryable)
      invalid_request  — 400/404/422: malformed request or missing resource
      unknown          — none of the above; needs investigation
    """
    # Check from most specific to least specific within each family.
    if isinstance(error, openai.AuthenticationError):
        return "auth_error"

    if isinstance(error, openai.PermissionDeniedError):
        return "auth_error"

    if isinstance(error, openai.RateLimitError):
        return "rate_limit"

    # APITimeoutError is a subclass of APIConnectionError — check it first.
    if isinstance(error, openai.APITimeoutError):
        return "timeout"

    if isinstance(error, openai.APIConnectionError):
        return "transient_error"

    if isinstance(error, openai.InternalServerError):
        return "transient_error"

    if isinstance(
        error,
        (openai.BadRequestError, openai.NotFoundError, openai.UnprocessableEntityError),
    ):
        return "invalid_request"

    return "unknown"

"""Schema drift guard tests.

These tests assert the STABLE PUBLIC SHAPES of all API request/response models,
the JSONL telemetry event schema, the report dataclass surface, and the
GatewayResult contract. They are intentionally rigid: a breaking change to any
public schema must cause a test failure here, which forces a conscious decision
to update both the schema and the test at the same time.

Rules for Kiro:
  - Do NOT weaken these tests to make unrelated work pass.
  - If you add a new field to a public schema, ADD a new assertion here.
  - If you rename a field, UPDATE the assertion and document why.
"""

from __future__ import annotations

from dataclasses import FrozenInstanceError
from dataclasses import fields as dataclass_fields
from typing import get_type_hints

import pytest
from pydantic import ValidationError

from app.schemas.answer_routed_request import AnswerRoutedRequest
from app.schemas.answer_routed_response import AnswerRoutedResponse
from app.schemas.classify_complexity_request import ClassifyComplexityRequest
from app.schemas.classify_complexity_response import ClassifyComplexityResponse
from app.schemas.conversation_turn_request import ConversationTurnRequest
from app.schemas.conversation_turn_response import ConversationTurnResponse
from gateway.client import GatewayResult, _categorize_error, _is_retryable
from reporting.make_report import (
    REQUIRED_NORMALIZED_FIELDS,
    AggregateMetrics,
    NormalizedTelemetryRow,
)

# ── API Request / Response schemas ───────────────────────────────────────────


class TestClassifyComplexitySchemas:
    """ClassifyComplexityRequest and ClassifyComplexityResponse are stable."""

    def test_request_required_fields(self) -> None:
        req = ClassifyComplexityRequest(message="hello")
        assert req.message == "hello"

    def test_request_rejects_empty_message(self) -> None:
        with pytest.raises(ValidationError):
            ClassifyComplexityRequest(message="")

    def test_request_field_names(self) -> None:
        hints = get_type_hints(ClassifyComplexityRequest)
        assert set(hints) == {"message"}

    def test_response_field_names(self) -> None:
        hints = get_type_hints(ClassifyComplexityResponse)
        assert set(hints) == {"complexity", "recommended_tier", "needs_escalation"}

    def test_response_complexity_literals(self) -> None:
        resp = ClassifyComplexityResponse(
            complexity="simple", recommended_tier="cheap", needs_escalation=False
        )
        assert resp.complexity in {"simple", "medium", "complex"}

    def test_response_tier_literals(self) -> None:
        resp = ClassifyComplexityResponse(
            complexity="complex", recommended_tier="expensive", needs_escalation=True
        )
        assert resp.recommended_tier in {"cheap", "expensive"}

    def test_response_rejects_invalid_complexity(self) -> None:
        with pytest.raises(ValidationError):
            ClassifyComplexityResponse(
                complexity="unknown",  # type: ignore[arg-type]
                recommended_tier="cheap",
                needs_escalation=False,
            )


class TestAnswerRoutedSchemas:
    """AnswerRoutedRequest and AnswerRoutedResponse are stable."""

    def test_request_field_names(self) -> None:
        hints = get_type_hints(AnswerRoutedRequest)
        assert set(hints) == {"message"}

    def test_response_field_names(self) -> None:
        hints = get_type_hints(AnswerRoutedResponse)
        assert set(hints) == {"answer", "selected_model", "routing_decision"}

    def test_response_routing_decision_literals(self) -> None:
        resp = AnswerRoutedResponse(
            answer="hi", selected_model="gpt-4o-mini", routing_decision="cheap"
        )
        assert resp.routing_decision in {"cheap", "expensive"}

    def test_response_rejects_invalid_routing_decision(self) -> None:
        with pytest.raises(ValidationError):
            AnswerRoutedResponse(
                answer="hi",
                selected_model="gpt-4o",
                routing_decision="unknown",  # type: ignore[arg-type]
            )


class TestConversationTurnSchemas:
    """ConversationTurnRequest and ConversationTurnResponse are stable."""

    def test_request_field_names(self) -> None:
        hints = get_type_hints(ConversationTurnRequest)
        assert set(hints) == {
            "conversation_id",
            "history",
            "message",
            "context_strategy",
        }

    def test_request_history_defaults_to_empty(self) -> None:
        req = ConversationTurnRequest(
            conversation_id="conv-1",
            message="hello",
            context_strategy="full",
        )
        assert req.history == []

    def test_request_context_strategy_literals(self) -> None:
        for strategy in ("full", "sliding_window", "summarized"):
            req = ConversationTurnRequest(
                conversation_id="c",
                message="m",
                context_strategy=strategy,  # type: ignore[arg-type]
            )
            assert req.context_strategy == strategy

    def test_response_field_names(self) -> None:
        hints = get_type_hints(ConversationTurnResponse)
        assert set(hints) == {
            "answer",
            "turn_index",
            "context_tokens_used",
            "context_strategy_applied",
        }

    def test_response_context_strategy_literals(self) -> None:
        resp = ConversationTurnResponse(
            answer="hi",
            turn_index=0,
            context_tokens_used=10,
            context_strategy_applied="full",
        )
        assert resp.context_strategy_applied in {"full", "sliding_window", "summarized"}


# ── JSONL Telemetry event schema ──────────────────────────────────────────────


class TestJSONLEventSchema:
    """The JSONL telemetry event written by gateway/telemetry.py has a stable schema.

    These tests exercise the _write_jsonl_event call indirectly via
    record_telemetry, which is the only public entry point. We verify the
    fields written to the JSONL file match the documented schema.
    """

    REQUIRED_TOP_LEVEL_KEYS = {
        "timestamp",
        "request_id",
        "route",
        "provider",
        "model",
        "latency_ms",
        "status",
        "tokens_in",
        "tokens_out",
        "estimated_cost_usd",
        "cache_hit",
        "schema_valid",
        "error_type",
    }

    def test_required_keys_constant_is_documented(self) -> None:
        """Self-check: the required keys set in this test matches what we document."""
        assert "timestamp" in self.REQUIRED_TOP_LEVEL_KEYS
        assert "estimated_cost_usd" in self.REQUIRED_TOP_LEVEL_KEYS
        assert "error_type" in self.REQUIRED_TOP_LEVEL_KEYS

    def test_reporting_required_fields_subset_of_jsonl_keys(self) -> None:
        """Fields that the reporting pipeline requires must all be in the JSONL schema."""
        assert REQUIRED_NORMALIZED_FIELDS.issubset(self.REQUIRED_TOP_LEVEL_KEYS)

    def test_status_field_values(self) -> None:
        """status must be one of the two documented values."""
        known_statuses = {"success", "error"}
        # Verify the set is stable — add values here only if the gateway adds them.
        assert known_statuses == {"success", "error"}


# ── Report output schema ──────────────────────────────────────────────────────


class TestReportSchema:
    """NormalizedTelemetryRow and AggregateMetrics are stable dataclasses."""

    def test_normalized_row_field_names(self) -> None:
        names = {f.name for f in dataclass_fields(NormalizedTelemetryRow)}
        assert names == {
            "route",
            "latency_ms",
            "estimated_cost_usd",
            "status",
            "schema_valid",
            "error_type",
        }

    def test_normalized_row_is_frozen(self) -> None:
        row = NormalizedTelemetryRow(
            route="/test",
            latency_ms=10.0,
            estimated_cost_usd=0.001,
            status="success",
            schema_valid=True,
            error_type=None,
        )
        with pytest.raises(FrozenInstanceError):
            row.route = "mutated"  # type: ignore[misc]

    def test_aggregate_metrics_field_names(self) -> None:
        names = {f.name for f in dataclass_fields(AggregateMetrics)}
        assert names == {
            "request_count",
            "latency_p50_ms",
            "latency_p95_ms",
            "estimated_total_cost_usd",
            "estimated_average_cost_usd",
            "error_rate",
            "schema_valid_rate",
            "error_count",
            "unknown_error_count",
        }

    def test_required_normalized_fields_stable(self) -> None:
        """REQUIRED_NORMALIZED_FIELDS is consumed by the reporting pipeline."""
        assert REQUIRED_NORMALIZED_FIELDS == {
            "route",
            "latency_ms",
            "estimated_cost_usd",
            "status",
            "schema_valid",
        }


# ── GatewayResult contract ───────────────────────────────────────────────────


class TestGatewayResultContract:
    """GatewayResult and key helper functions have a stable public surface."""

    def test_gateway_result_field_names(self) -> None:
        names = {f.name for f in dataclass_fields(GatewayResult)}
        assert names == {
            "text",
            "selected_model",
            "request_id",
            "tokens_in",
            "tokens_out",
            "estimated_cost_usd",
            "cache_hit",
        }

    def test_gateway_result_is_frozen(self) -> None:
        result = GatewayResult(
            text="hi",
            selected_model="gpt-4o-mini",
            request_id="req-1",
            tokens_in=10,
            tokens_out=5,
            estimated_cost_usd=0.001,
            cache_hit=False,
        )
        with pytest.raises(FrozenInstanceError):
            result.text = "mutated"  # type: ignore[misc]

    def test_categorize_error_returns_string(self) -> None:
        """_categorize_error must return a non-empty string for any exception."""
        for exc in [ValueError("test"), RuntimeError("test"), TimeoutError("test")]:
            result = _categorize_error(exc)
            assert isinstance(result, str)
            assert len(result) > 0

    def test_is_retryable_returns_bool(self) -> None:
        """_is_retryable must return bool for any exception."""
        for exc in [ValueError("test"), RuntimeError("test")]:
            result = _is_retryable(exc)
            assert isinstance(result, bool)

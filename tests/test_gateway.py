"""Tests for gateway components.

These tests verify gateway behavior with mocked OpenAI API calls for determinism.

ERROR CLASSIFICATION TESTS — WHY REAL OPENAI EXCEPTION TYPES
─────────────────────────────────────────────────────────────
``_categorize_error()`` and ``_is_retryable()`` now use ``isinstance()``
checks against the typed OpenAI exception hierarchy. This means tests must
construct real ``openai.*Error`` instances rather than plain ``Exception``
objects with matching message strings.

Helper ``_make_response(status_code)`` builds a minimal ``httpx.Response``
that satisfies the OpenAI SDK's constructor requirements. The request and
response objects are synthetic — only their type matters for isinstance checks.
"""

import json
from unittest.mock import Mock, patch

import httpx
import openai
import pytest

from gateway import cost_model, policies
from gateway.client import GatewayResult, _categorize_error, _is_retryable, call_llm


# ─────────────────────────────────────────────────────────────────────────────
# Test helpers for constructing OpenAI exceptions
# ─────────────────────────────────────────────────────────────────────────────

def _make_response(status_code: int) -> httpx.Response:
    """Build a minimal fake httpx.Response for OpenAI exception constructors.

    OpenAI's APIStatusError subclasses (RateLimitError, AuthenticationError, …)
    require a real httpx.Response so they can expose .status_code and .headers
    attributes. We pass a synthetic one — the test only cares about the exception
    type, not the response content.
    """
    return httpx.Response(
        status_code,
        request=httpx.Request("POST", "https://api.openai.com/v1/test"),
    )


def _make_request() -> httpx.Request:
    """Build a minimal fake httpx.Request for APIConnectionError constructors."""
    return httpx.Request("POST", "https://api.openai.com/v1/test")


class TestCostModel:
    """Tests for cost_model module."""

    def test_estimate_cost_gpt5_mini(self):
        """Cost estimation for gpt-4o-mini should be deterministic."""
        # 1M input * $0.15/1M + 500K output * $0.60/1M = $0.15 + $0.30 = $0.45
        cost = cost_model.estimate_cost("gpt-4o-mini", 1_000_000, 500_000)
        assert cost == pytest.approx(0.45)

    def test_estimate_cost_gpt52(self):
        """Cost estimation for gpt-4o should be deterministic."""
        # 1M input * $2.50/1M + 500K output * $10.00/1M = $2.50 + $5.00 = $7.50
        cost = cost_model.estimate_cost("gpt-4o", 1_000_000, 500_000)
        assert cost == pytest.approx(7.50)

    def test_estimate_cost_small_values(self):
        """Cost estimation should work with small token counts."""
        # 1000 input * $0.15/1M + 500 output * $0.60/1M = $0.00015 + $0.0003 = $0.00045
        cost = cost_model.estimate_cost("gpt-4o-mini", 1000, 500)
        assert cost == pytest.approx(0.00045)

    def test_estimate_cost_unknown_model(self):
        """Unknown model should raise ValueError."""
        with pytest.raises(ValueError, match="Unknown model"):
            cost_model.estimate_cost("unknown-model", 1000, 500)

    def test_estimate_cost_negative_tokens(self):
        """Negative token counts should raise ValueError."""
        with pytest.raises(ValueError, match="non-negative"):
            cost_model.estimate_cost("gpt-4o-mini", -100, 500)

        with pytest.raises(ValueError, match="non-negative"):
            cost_model.estimate_cost("gpt-4o-mini", 1000, -50)

    def test_get_pricing(self):
        """get_pricing should return pricing configuration."""
        pricing = cost_model.get_pricing()

        assert "gpt-4o-mini" in pricing
        assert "gpt-4o" in pricing
        assert pricing["gpt-4o-mini"]["input_per_1m"] == 0.15
        assert pricing["gpt-4o"]["output_per_1m"] == 10.00


class TestPolicies:
    """Tests for policies module."""

    def test_get_route_policy_answer_routed(self):
        """Policy for /answer-routed should be configured."""
        policy = policies.get_route_policy("/answer-routed")

        assert policy.max_output_tokens == 500
        assert policy.retry_attempts == 2
        assert policy.cache_enabled is False
        assert "cheap" in policy.model_for_tier
        assert "expensive" in policy.model_for_tier

    def test_get_route_policy_conversation_turn(self):
        """Policy for /conversation-turn should be configured."""
        policy = policies.get_route_policy("/conversation-turn")

        assert policy.max_output_tokens == 500
        assert policy.retry_attempts == 2
        assert policy.cache_enabled is False

    def test_get_route_policy_unknown_route(self):
        """Unknown route should raise ValueError."""
        with pytest.raises(ValueError, match="No gateway policy"):
            policies.get_route_policy("/unknown-route")

    def test_get_model_for_tier_cheap(self):
        """Cheap tier should resolve to gpt-4o-mini."""
        model = policies.get_model_for_tier("/answer-routed", "cheap")
        assert model == "gpt-4o-mini"

    def test_get_model_for_tier_expensive(self):
        """Expensive tier should resolve to gpt-4o."""
        model = policies.get_model_for_tier("/answer-routed", "expensive")
        assert model == "gpt-4o"

    def test_get_model_for_tier_unknown_tier(self):
        """Unknown tier should raise ValueError."""
        with pytest.raises(ValueError, match="not configured"):
            policies.get_model_for_tier("/answer-routed", "invalid")  # type: ignore[arg-type]


class TestGatewayClient:
    """Tests for gateway client module."""

    def test_gateway_result_structure(self):
        """GatewayResult should have all required fields."""
        result = GatewayResult(
            text="test response",
            selected_model="gpt-4o-mini",
            request_id="test-id",
            tokens_in=100,
            tokens_out=50,
            estimated_cost_usd=0.001,
            cache_hit=False,
        )

        assert result.text == "test response"
        assert result.selected_model == "gpt-4o-mini"
        assert result.request_id == "test-id"
        assert result.tokens_in == 100
        assert result.tokens_out == 50
        assert result.estimated_cost_usd == 0.001
        assert result.cache_hit is False

    @patch("gateway.client.OpenAI")
    @patch.dict("os.environ", {"OPENAI_API_KEY": "test-key"})
    def test_call_llm_success(self, mock_openai_class, tmp_path, monkeypatch):
        """Successful call_llm should return GatewayResult and emit telemetry."""
        test_telemetry = tmp_path / "telemetry.jsonl"
        monkeypatch.setattr("gateway.telemetry.TELEMETRY_PATH", test_telemetry)

        mock_client = Mock()
        mock_openai_class.return_value = mock_client

        mock_usage = Mock()
        mock_usage.input_tokens = 100
        mock_usage.output_tokens = 50

        mock_response = Mock()
        mock_response.output_text = "Test response"
        mock_response.usage = mock_usage

        mock_client.responses.create.return_value = mock_response

        result = call_llm(
            prompt="Test prompt",
            model_tier="cheap",
            route_name="/answer-routed",
            metadata={"routing_decision": "cheap"},
        )

        assert isinstance(result, GatewayResult)
        assert result.text == "Test response"
        assert result.selected_model == "gpt-4o-mini"
        assert result.tokens_in == 100
        assert result.tokens_out == 50
        assert result.estimated_cost_usd > 0
        assert result.cache_hit is False
        assert len(result.request_id) > 0

        assert test_telemetry.exists()

        with test_telemetry.open() as file_handle:
            event = json.loads(file_handle.readline())

        assert event["status"] == "success"
        assert event["route"] == "/answer-routed"
        assert event["model"] == "gpt-4o-mini"
        assert event["tokens_in"] == 100
        assert event["tokens_out"] == 50
        assert event["routing_decision"] == "cheap"
        assert event["selected_model"] == "gpt-4o-mini"

    @patch("gateway.client.OpenAI")
    @patch.dict("os.environ", {"OPENAI_API_KEY": "test-key"})
    def test_call_llm_error(self, mock_openai_class, tmp_path, monkeypatch):
        """Failed call_llm should emit error telemetry and raise exception."""
        test_telemetry = tmp_path / "telemetry.jsonl"
        monkeypatch.setattr("gateway.telemetry.TELEMETRY_PATH", test_telemetry)

        mock_client = Mock()
        mock_openai_class.return_value = mock_client
        # Use a real openai.BadRequestError so isinstance() in _categorize_error
        # correctly maps it to "invalid_request". A plain Exception("invalid request")
        # no longer matches because we switched from substring to isinstance checks.
        mock_client.responses.create.side_effect = openai.BadRequestError(
            "invalid request",
            response=_make_response(400),
            body=None,
        )

        with pytest.raises(openai.BadRequestError):
            call_llm(
                prompt="Test prompt",
                model_tier="cheap",
                route_name="/answer-routed",
            )

        assert test_telemetry.exists()

        with test_telemetry.open() as file_handle:
            event = json.loads(file_handle.readline())

        assert event["status"] == "error"
        assert event["error_type"] == "invalid_request"
        assert event["tokens_in"] == 0
        assert event["tokens_out"] == 0

    def test_categorize_error_rate_limit(self):
        """RateLimitError (429) should be categorised as rate_limit."""
        error = openai.RateLimitError(
            "rate limit exceeded",
            response=_make_response(429),
            body=None,
        )
        assert _categorize_error(error) == "rate_limit"

    def test_categorize_error_invalid_request(self):
        """BadRequestError (400) should be categorised as invalid_request."""
        error = openai.BadRequestError(
            "invalid request",
            response=_make_response(400),
            body=None,
        )
        assert _categorize_error(error) == "invalid_request"

    def test_categorize_error_auth(self):
        """AuthenticationError (401) should be categorised as auth_error."""
        error = openai.AuthenticationError(
            "incorrect API key",
            response=_make_response(401),
            body=None,
        )
        assert _categorize_error(error) == "auth_error"

    def test_categorize_error_permission_denied(self):
        """PermissionDeniedError (403) should be categorised as auth_error."""
        error = openai.PermissionDeniedError(
            "forbidden",
            response=_make_response(403),
            body=None,
        )
        assert _categorize_error(error) == "auth_error"

    def test_categorize_error_timeout(self):
        """APITimeoutError should be categorised as timeout."""
        error = openai.APITimeoutError(request=_make_request())
        assert _categorize_error(error) == "timeout"

    def test_categorize_error_transient_connection(self):
        """APIConnectionError (non-timeout) should be categorised as transient_error."""
        error = openai.APIConnectionError(request=_make_request())
        assert _categorize_error(error) == "transient_error"

    def test_categorize_error_transient_server(self):
        """InternalServerError (5xx) should be categorised as transient_error."""
        error = openai.InternalServerError(
            "server error",
            response=_make_response(503),
            body=None,
        )
        assert _categorize_error(error) == "transient_error"

    def test_categorize_error_unknown(self):
        """A plain Exception (not an openai type) should be categorised as unknown."""
        error = Exception("something unexpected")
        assert _categorize_error(error) == "unknown"

    def test_is_retryable_rate_limit(self):
        """RateLimitError should be retryable."""
        error = openai.RateLimitError(
            "rate limit",
            response=_make_response(429),
            body=None,
        )
        assert _is_retryable(error) is True

    def test_is_retryable_timeout(self):
        """APITimeoutError should be retryable."""
        error = openai.APITimeoutError(request=_make_request())
        assert _is_retryable(error) is True

    def test_is_retryable_transient_server_error(self):
        """InternalServerError should be retryable."""
        error = openai.InternalServerError(
            "server error",
            response=_make_response(503),
            body=None,
        )
        assert _is_retryable(error) is True

    def test_is_retryable_connection_error(self):
        """APIConnectionError should be retryable."""
        error = openai.APIConnectionError(request=_make_request())
        assert _is_retryable(error) is True

    def test_is_retryable_invalid_request(self):
        """BadRequestError should NOT be retryable."""
        error = openai.BadRequestError(
            "invalid request",
            response=_make_response(400),
            body=None,
        )
        assert _is_retryable(error) is False

    def test_is_retryable_auth_error(self):
        """AuthenticationError should NOT be retryable."""
        error = openai.AuthenticationError(
            "bad key",
            response=_make_response(401),
            body=None,
        )
        assert _is_retryable(error) is False

    def test_is_retryable_plain_exception(self):
        """A plain Exception (not an openai type) should NOT be retryable."""
        error = Exception("something unexpected")
        assert _is_retryable(error) is False


class TestTelemetryEmission:
    """Tests for telemetry emission."""

    def test_telemetry_event_shape(self, tmp_path, monkeypatch):
        """Telemetry events should have all required fields."""
        from gateway import telemetry

        test_telemetry = tmp_path / "telemetry.jsonl"
        monkeypatch.setattr("gateway.telemetry.TELEMETRY_PATH", test_telemetry)

        telemetry.emit(
            request_id="test-id",
            route="/answer-routed",
            provider="openai",
            model="gpt-4o-mini",
            latency_ms=123.45,
            status="success",
            tokens_in=100,
            tokens_out=50,
            estimated_cost_usd=0.001,
            cache_hit=False,
            schema_valid=True,
            error_type=None,
            metadata={
                "routing_decision": "cheap",
                "selected_model": "gpt-4o-mini",
            },
        )

        assert test_telemetry.exists()

        with test_telemetry.open() as file_handle:
            event = json.loads(file_handle.readline())

        assert "timestamp" in event
        assert event["request_id"] == "test-id"
        assert event["route"] == "/answer-routed"
        assert event["provider"] == "openai"
        assert event["model"] == "gpt-4o-mini"
        assert event["latency_ms"] == 123.45
        assert event["status"] == "success"
        assert event["tokens_in"] == 100
        assert event["tokens_out"] == 50
        assert event["estimated_cost_usd"] == 0.001
        assert event["cache_hit"] is False
        assert event["schema_valid"] is True
        assert event["error_type"] is None
        assert event["routing_decision"] == "cheap"
        assert event["selected_model"] == "gpt-4o-mini"
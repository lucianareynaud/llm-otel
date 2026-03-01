"""Tests for reference app routes.

These tests verify that all three routes:
- accept valid inputs
- reject invalid inputs
- return schema-compliant outputs
- expose routing and context metadata explicitly
"""

from unittest.mock import patch

from fastapi.testclient import TestClient

from app.main import app
from gateway.client import GatewayResult

client = TestClient(app)


class TestClassifyComplexityRoute:
    """Tests for /classify-complexity route."""

    def test_simple_message(self):
        response = client.post(
            "/classify-complexity",
            json={"message": "What is 2+2?"},
        )

        assert response.status_code == 200
        data = response.json()

        assert data["complexity"] == "simple"
        assert data["recommended_tier"] == "cheap"
        assert data["needs_escalation"] is False

    def test_complex_message(self):
        response = client.post(
            "/classify-complexity",
            json={"message": "Analyze the complex implications of quantum computing"},
        )

        assert response.status_code == 200
        data = response.json()

        assert data["complexity"] == "complex"
        assert data["recommended_tier"] == "expensive"
        assert data["needs_escalation"] is True

    def test_medium_message(self):
        response = client.post(
            "/classify-complexity",
            json={
                "message": (
                    "Can you help me understand how photosynthesis works"
                    " in plants and why light matters?"
                )
            },
        )

        assert response.status_code == 200
        data = response.json()

        assert data["complexity"] == "medium"
        assert data["recommended_tier"] == "cheap"
        assert data["needs_escalation"] is False

    def test_missing_message_field(self):
        response = client.post("/classify-complexity", json={})
        assert response.status_code == 422

    def test_empty_message(self):
        response = client.post(
            "/classify-complexity",
            json={"message": ""},
        )
        assert response.status_code == 422

    def test_response_schema_compliance(self):
        response = client.post(
            "/classify-complexity",
            json={"message": "Test message"},
        )

        assert response.status_code == 200
        data = response.json()

        assert "complexity" in data
        assert "recommended_tier" in data
        assert "needs_escalation" in data


class TestAnswerRoutedRoute:
    """Tests for /answer-routed route."""

    @patch("app.routes.answer_routed.call_llm")
    def test_cheap_routing(self, mock_call_llm):
        mock_call_llm.return_value = GatewayResult(
            text="Test cheap response",
            selected_model="gpt-4o-mini",
            request_id="req-1",
            tokens_in=10,
            tokens_out=5,
            estimated_cost_usd=0.001,
            cache_hit=False,
        )

        response = client.post(
            "/answer-routed",
            json={"message": "What is 2+2?"},
        )

        assert response.status_code == 200
        data = response.json()

        assert data["answer"] == "Test cheap response"
        assert data["routing_decision"] == "cheap"
        assert data["selected_model"] == "gpt-4o-mini"

    @patch("app.routes.answer_routed.call_llm")
    def test_expensive_routing(self, mock_call_llm):
        mock_call_llm.return_value = GatewayResult(
            text="Test expensive response",
            selected_model="gpt-4o",
            request_id="req-2",
            tokens_in=20,
            tokens_out=10,
            estimated_cost_usd=0.01,
            cache_hit=False,
        )

        response = client.post(
            "/answer-routed",
            json={"message": "Analyze the complex implications of AI"},
        )

        assert response.status_code == 200
        data = response.json()

        assert data["answer"] == "Test expensive response"
        assert data["routing_decision"] == "expensive"
        assert data["selected_model"] == "gpt-4o"

    @patch("app.routes.answer_routed.call_llm")
    def test_routing_metadata_present(self, mock_call_llm):
        mock_call_llm.return_value = GatewayResult(
            text="Test response",
            selected_model="gpt-4o-mini",
            request_id="req-3",
            tokens_in=10,
            tokens_out=5,
            estimated_cost_usd=0.001,
            cache_hit=False,
        )

        response = client.post(
            "/answer-routed",
            json={"message": "Test message"},
        )

        assert response.status_code == 200
        data = response.json()

        assert "routing_decision" in data
        assert "selected_model" in data
        assert data["routing_decision"] in ["cheap", "expensive"]

    def test_missing_message_field(self):
        response = client.post("/answer-routed", json={})
        assert response.status_code == 422

    def test_empty_message(self):
        response = client.post(
            "/answer-routed",
            json={"message": ""},
        )
        assert response.status_code == 422

    @patch("app.routes.answer_routed.call_llm")
    def test_response_schema_compliance(self, mock_call_llm):
        mock_call_llm.return_value = GatewayResult(
            text="Test response",
            selected_model="gpt-4o-mini",
            request_id="req-4",
            tokens_in=10,
            tokens_out=5,
            estimated_cost_usd=0.001,
            cache_hit=False,
        )

        response = client.post(
            "/answer-routed",
            json={"message": "Test message"},
        )

        assert response.status_code == 200
        data = response.json()

        assert "answer" in data
        assert "selected_model" in data
        assert "routing_decision" in data


class TestConversationTurnRoute:
    """Tests for /conversation-turn route."""

    @patch("app.routes.conversation_turn.call_llm")
    def test_full_strategy_empty_history(self, mock_call_llm):
        mock_call_llm.return_value = GatewayResult(
            text="Conversation response",
            selected_model="gpt-4o",
            request_id="req-5",
            tokens_in=15,
            tokens_out=8,
            estimated_cost_usd=0.01,
            cache_hit=False,
        )

        response = client.post(
            "/conversation-turn",
            json={
                "conversation_id": "conv-1",
                "history": [],
                "message": "Hello",
                "context_strategy": "full",
            },
        )

        assert response.status_code == 200
        data = response.json()

        assert "answer" in data
        assert data["turn_index"] == 0
        assert data["context_tokens_used"] > 0
        assert data["context_strategy_applied"] == "full"

    @patch("app.routes.conversation_turn.call_llm")
    def test_full_strategy_with_history(self, mock_call_llm):
        mock_call_llm.return_value = GatewayResult(
            text="Conversation response",
            selected_model="gpt-4o",
            request_id="req-6",
            tokens_in=20,
            tokens_out=10,
            estimated_cost_usd=0.02,
            cache_hit=False,
        )

        response = client.post(
            "/conversation-turn",
            json={
                "conversation_id": "conv-2",
                "history": ["First", "Second", "Third"],
                "message": "Fourth",
                "context_strategy": "full",
            },
        )

        assert response.status_code == 200
        data = response.json()

        assert data["turn_index"] == 3
        assert data["context_tokens_used"] > 0
        assert data["context_strategy_applied"] == "full"

    @patch("app.routes.conversation_turn.call_llm")
    def test_sliding_window_strategy(self, mock_call_llm):
        mock_call_llm.return_value = GatewayResult(
            text="Conversation response",
            selected_model="gpt-4o",
            request_id="req-7",
            tokens_in=20,
            tokens_out=10,
            estimated_cost_usd=0.02,
            cache_hit=False,
        )

        response = client.post(
            "/conversation-turn",
            json={
                "conversation_id": "conv-3",
                "history": ["Message 1", "Message 2"],
                "message": "Message 3",
                "context_strategy": "sliding_window",
            },
        )

        assert response.status_code == 200
        data = response.json()

        assert data["context_strategy_applied"] == "sliding_window"
        assert data["context_tokens_used"] > 0

    @patch("app.routes.conversation_turn.call_llm")
    def test_summarized_strategy(self, mock_call_llm):
        mock_call_llm.return_value = GatewayResult(
            text="Conversation response",
            selected_model="gpt-4o",
            request_id="req-8",
            tokens_in=20,
            tokens_out=10,
            estimated_cost_usd=0.02,
            cache_hit=False,
        )

        response = client.post(
            "/conversation-turn",
            json={
                "conversation_id": "conv-4",
                "history": ["Message 1", "Message 2"],
                "message": "Message 3",
                "context_strategy": "summarized",
            },
        )

        assert response.status_code == 200
        data = response.json()

        assert data["context_strategy_applied"] == "summarized"
        assert data["context_tokens_used"] > 0

    @patch("app.routes.conversation_turn.call_llm")
    def test_context_metadata_present(self, mock_call_llm):
        mock_call_llm.return_value = GatewayResult(
            text="Conversation response",
            selected_model="gpt-4o",
            request_id="req-9",
            tokens_in=15,
            tokens_out=8,
            estimated_cost_usd=0.01,
            cache_hit=False,
        )

        response = client.post(
            "/conversation-turn",
            json={
                "conversation_id": "conv-5",
                "history": [],
                "message": "Test",
                "context_strategy": "full",
            },
        )

        assert response.status_code == 200
        data = response.json()

        assert "context_strategy_applied" in data
        assert "context_tokens_used" in data
        assert "turn_index" in data

    @patch("app.routes.conversation_turn.call_llm")
    def test_turn_index_calculation(self, mock_call_llm):
        mock_call_llm.return_value = GatewayResult(
            text="Conversation response",
            selected_model="gpt-4o",
            request_id="req-10",
            tokens_in=15,
            tokens_out=8,
            estimated_cost_usd=0.01,
            cache_hit=False,
        )

        for history_length in [0, 1, 5, 10]:
            history = [f"Message {i}" for i in range(history_length)]

            response = client.post(
                "/conversation-turn",
                json={
                    "conversation_id": f"conv-{history_length}",
                    "history": history,
                    "message": "Current",
                    "context_strategy": "full",
                },
            )

            assert response.status_code == 200
            data = response.json()
            assert data["turn_index"] == history_length

    def test_missing_required_fields(self):
        response = client.post(
            "/conversation-turn",
            json={"message": "Test"},
        )
        assert response.status_code == 422

    def test_invalid_context_strategy(self):
        response = client.post(
            "/conversation-turn",
            json={
                "conversation_id": "conv-x",
                "history": [],
                "message": "Test",
                "context_strategy": "invalid_strategy",
            },
        )
        assert response.status_code == 422

    @patch("app.routes.conversation_turn.call_llm")
    def test_response_schema_compliance(self, mock_call_llm):
        mock_call_llm.return_value = GatewayResult(
            text="Conversation response",
            selected_model="gpt-4o",
            request_id="req-11",
            tokens_in=15,
            tokens_out=8,
            estimated_cost_usd=0.01,
            cache_hit=False,
        )

        response = client.post(
            "/conversation-turn",
            json={
                "conversation_id": "conv-test",
                "history": [],
                "message": "Test",
                "context_strategy": "full",
            },
        )

        assert response.status_code == 200
        data = response.json()

        assert "answer" in data
        assert "turn_index" in data
        assert "context_tokens_used" in data
        assert "context_strategy_applied" in data


class TestRouteIntegration:
    """Integration tests across routes."""

    @patch("app.routes.answer_routed.call_llm")
    @patch("app.routes.conversation_turn.call_llm")
    def test_all_routes_accessible(self, mock_conversation_call_llm, mock_answer_call_llm):
        mock_answer_call_llm.return_value = GatewayResult(
            text="Answer routed response",
            selected_model="gpt-4o-mini",
            request_id="req-12",
            tokens_in=10,
            tokens_out=5,
            estimated_cost_usd=0.001,
            cache_hit=False,
        )
        mock_conversation_call_llm.return_value = GatewayResult(
            text="Conversation response",
            selected_model="gpt-4o",
            request_id="req-13",
            tokens_in=15,
            tokens_out=8,
            estimated_cost_usd=0.01,
            cache_hit=False,
        )

        routes = [
            ("/classify-complexity", {"message": "Test"}),
            ("/answer-routed", {"message": "Test"}),
            (
                "/conversation-turn",
                {
                    "conversation_id": "test",
                    "history": [],
                    "message": "Test",
                    "context_strategy": "full",
                },
            ),
        ]

        for route, payload in routes:
            response = client.post(route, json=payload)
            assert response.status_code == 200

    @patch("app.routes.answer_routed.call_llm")
    def test_consistent_routing_logic(self, mock_call_llm):
        mock_call_llm.return_value = GatewayResult(
            text="Expensive response",
            selected_model="gpt-4o",
            request_id="req-14",
            tokens_in=20,
            tokens_out=10,
            estimated_cost_usd=0.02,
            cache_hit=False,
        )

        message = "Analyze the complex implications"

        classify_response = client.post(
            "/classify-complexity",
            json={"message": message},
        )
        classify_data = classify_response.json()

        answer_response = client.post(
            "/answer-routed",
            json={"message": message},
        )
        answer_data = answer_response.json()

        assert classify_data["recommended_tier"] == answer_data["routing_decision"]

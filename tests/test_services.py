"""Tests for routing and context manager services.

These tests verify that service logic is deterministic, stable, and
produces reproducible outputs for bounded test inputs.
"""

import pytest

from app.services.context_manager import prepare_context
from app.services.routing import determine_complexity


class TestRoutingService:
    """Tests for routing.determine_complexity()."""

    def test_simple_message_short_length(self):
        """Short messages should be classified as simple and routed to cheap tier."""
        message = "What is 2+2?"
        complexity, tier, escalation = determine_complexity(message)

        assert complexity == "simple"
        assert tier == "cheap"
        assert escalation is False

    def test_simple_message_with_keyword(self):
        """Messages with simple keywords should be classified as simple."""
        message = "What is the capital of France?"
        complexity, tier, escalation = determine_complexity(message)

        assert complexity == "simple"
        assert tier == "cheap"
        assert escalation is False

    def test_medium_message(self):
        """Medium-length messages without special keywords should be medium complexity."""
        message = "Can you help me understand how photosynthesis works in plants?"
        complexity, tier, escalation = determine_complexity(message)

        assert complexity == "medium"
        assert tier == "cheap"
        assert escalation is False

    def test_complex_message_with_keyword(self):
        """Messages with complex keywords should be classified as complex."""
        message = "Analyze the complex implications of quantum computing on cryptography"
        complexity, tier, escalation = determine_complexity(message)

        assert complexity == "complex"
        assert tier == "expensive"
        assert escalation is True

    def test_complex_message_long_length(self):
        """Very long messages should be classified as complex regardless of keywords."""
        message = "x" * 250
        complexity, tier, escalation = determine_complexity(message)

        assert complexity == "complex"
        assert tier == "expensive"
        assert escalation is True

    def test_deterministic_output(self):
        """Same input should always produce same output."""
        message = "Explain the theory of relativity"

        result1 = determine_complexity(message)
        result2 = determine_complexity(message)

        assert result1 == result2


class TestContextManagerService:
    """Tests for context_manager.prepare_context()."""

    def test_full_strategy_empty_history(self):
        """Full strategy with empty history should include only current message."""
        history = []
        message = "Hello"

        context, tokens = prepare_context(history, message, "full")

        assert "Turn 0: Hello" in context
        assert tokens > 0

    def test_full_strategy_with_history(self):
        """Full strategy should include all history messages."""
        history = ["First message", "Second message", "Third message"]
        message = "Fourth message"

        context, tokens = prepare_context(history, message, "full")

        assert "First message" in context
        assert "Second message" in context
        assert "Third message" in context
        assert "Fourth message" in context
        assert tokens > 0

    def test_sliding_window_strategy_short_history(self):
        """Sliding window with short history should include all messages."""
        history = ["Message 1", "Message 2"]
        message = "Message 3"

        context, tokens = prepare_context(history, message, "sliding_window")

        assert "Message 1" in context
        assert "Message 2" in context
        assert "Message 3" in context
        assert tokens > 0

    def test_sliding_window_strategy_long_history(self):
        """Sliding window should only include recent messages when history is long."""
        history = [f"Message {i}" for i in range(10)]
        message = "Current message"

        context, tokens = prepare_context(history, message, "sliding_window")

        assert "Message 0" not in context
        assert "Message 4" not in context

        assert "Message 5" in context
        assert "Message 9" in context
        assert "Current message" in context
        assert tokens > 0

    def test_summarized_strategy_short_history(self):
        """Summarized strategy with short history should behave like full."""
        history = ["Message 1", "Message 2"]
        message = "Message 3"

        context, tokens = prepare_context(history, message, "summarized")

        assert "Message 1" in context
        assert "Message 2" in context
        assert "Message 3" in context
        assert tokens > 0

    def test_summarized_strategy_long_history(self):
        """Summarized strategy should create summary for old messages."""
        history = [f"Message {i}" for i in range(15)]
        message = "Current message"

        context, tokens = prepare_context(history, message, "summarized")

        assert "Summary" in context
        assert "earlier messages" in context
        assert "Message 14" in context
        assert "Current message" in context
        assert tokens > 0

    def test_token_estimation_grows_with_context(self):
        """Token count should increase as context grows."""
        message = "Test message"

        _, tokens_empty = prepare_context([], message, "full")
        _, tokens_small = prepare_context(["A", "B"], message, "full")
        _, tokens_large = prepare_context(["A"] * 10, message, "full")

        assert tokens_empty < tokens_small < tokens_large

    def test_deterministic_output(self):
        """Same inputs should always produce same outputs."""
        history = ["Message 1", "Message 2"]
        message = "Message 3"

        context1, tokens1 = prepare_context(history, message, "full")
        context2, tokens2 = prepare_context(history, message, "full")

        assert context1 == context2
        assert tokens1 == tokens2

    def test_invalid_strategy_raises_value_error(self):
        """Unknown context strategies should fail explicitly."""
        with pytest.raises(ValueError, match="Unknown context strategy"):
            prepare_context(["Message 1"], "Message 2", "invalid")  # type: ignore[arg-type]

    def test_all_strategies_return_valid_output(self):
        """All strategies should return non-empty context and positive token count."""
        history = ["Message 1", "Message 2"]
        message = "Message 3"

        for strategy in ["full", "sliding_window", "summarized"]:
            context, tokens = prepare_context(history, message, strategy)

            assert len(context) > 0
            assert tokens > 0
            assert "Message 3" in context

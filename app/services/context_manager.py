"""Context manager service for conversation-turn context preparation.

This module applies bounded context strategies for multi-turn conversations.
It supports:
- full
- sliding_window
- summarized

All strategies are deterministic and reproducible in the MVP.
"""

from typing import Literal

ContextStrategy = Literal["full", "sliding_window", "summarized"]

SLIDING_WINDOW_SIZE = 5
SUMMARIZATION_THRESHOLD = 10
CHARS_PER_TOKEN = 4


def prepare_context(
    history: list[str],
    message: str,
    strategy: ContextStrategy,
) -> tuple[str, int]:
    """Prepare conversation context according to the requested strategy.

    Args:
        history: Previous conversation messages in chronological order.
        message: Current user message.
        strategy: Context preparation strategy.

    Returns:
        A tuple of:
        - prepared_context: formatted context string
        - estimated_token_count: rough token estimate for the prepared context
    """
    if strategy == "full":
        return _prepare_full_context(history, message)

    if strategy == "sliding_window":
        return _prepare_sliding_window_context(history, message)

    if strategy == "summarized":
        return _prepare_summarized_context(history, message)

    raise ValueError(f"Unknown context strategy: {strategy}")


def _prepare_full_context(history: list[str], message: str) -> tuple[str, int]:
    """Include all prior history plus the current message."""
    messages = history + [message]
    context = _format_messages(messages)
    return context, _estimate_tokens(context)


def _prepare_sliding_window_context(history: list[str], message: str) -> tuple[str, int]:
    """Include only the most recent bounded portion of history plus the current message."""
    recent_history = history[-SLIDING_WINDOW_SIZE:]
    messages = recent_history + [message]
    context = _format_messages(messages)
    return context, _estimate_tokens(context)


def _prepare_summarized_context(history: list[str], message: str) -> tuple[str, int]:
    """Summarize older history deterministically and keep recent turns verbatim.

    In the MVP, summarization is a deterministic placeholder string.
    If a future implementation uses an LLM for summarization, that call
    must go through the gateway layer.
    """
    if len(history) <= SUMMARIZATION_THRESHOLD:
        return _prepare_full_context(history, message)

    old_history = history[:-SLIDING_WINDOW_SIZE]
    recent_history = history[-SLIDING_WINDOW_SIZE:]

    summary = _build_placeholder_summary(old_history)

    context_parts = [summary, _format_messages(recent_history), f"Current: {message}"]
    context = "\n".join(part for part in context_parts if part)
    return context, _estimate_tokens(context)


def _format_messages(messages: list[str]) -> str:
    """Format messages into a deterministic multi-line context block."""
    return "\n".join(f"Turn {index}: {content}" for index, content in enumerate(messages))


def _build_placeholder_summary(old_history: list[str]) -> str:
    """Build a deterministic placeholder summary for older history."""
    return (
        f"[Summary of {len(old_history)} earlier messages: "
        "prior conversation context retained in condensed form]"
    )


def _estimate_tokens(text: str) -> int:
    """Estimate token count using a simple deterministic character heuristic."""
    return max(1, len(text) // CHARS_PER_TOKEN) if text else 0

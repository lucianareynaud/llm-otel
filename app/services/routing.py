"""Routing service for complexity classification and model tier selection.

This module contains the shared routing decision logic used by both
/classify-complexity and /answer-routed routes.
"""

from typing import Literal

Complexity = Literal["simple", "medium", "complex"]
Tier = Literal["cheap", "expensive"]

COMPLEX_KEYWORDS: tuple[str, ...] = (
    "analyze",
    "complex",
    "detailed",
    "comprehensive",
    "explain in depth",
    "compare and contrast",
    "evaluate",
    "critically",
    "implications",
)

SIMPLE_KEYWORDS: tuple[str, ...] = (
    "what is",
    "simple",
    "quick",
    "briefly",
    "yes or no",
)

SIMPLE_LENGTH_THRESHOLD = 50
COMPLEX_LENGTH_THRESHOLD = 200


def determine_complexity(message: str) -> tuple[Complexity, Tier, bool]:
    """Determine message complexity and recommend a model tier.

    The logic is intentionally simple, deterministic, and inspectable.
    It uses keyword matches and message length to assign:
    - a complexity label,
    - a recommended model tier,
    - and whether the message should be escalated to a more capable path.

    Args:
        message: The input message to classify.

    Returns:
        A tuple of:
        - complexity: "simple", "medium", or "complex"
        - recommended_tier: "cheap" or "expensive"
        - needs_escalation: whether the message should use the expensive path
    """
    normalized_message = message.strip().lower()
    message_length = len(normalized_message)

    has_complex_keyword = any(keyword in normalized_message for keyword in COMPLEX_KEYWORDS)
    has_simple_keyword = any(keyword in normalized_message for keyword in SIMPLE_KEYWORDS)

    if has_complex_keyword or message_length > COMPLEX_LENGTH_THRESHOLD:
        return "complex", "expensive", True

    if has_simple_keyword or message_length < SIMPLE_LENGTH_THRESHOLD:
        return "simple", "cheap", False

    return "medium", "cheap", False

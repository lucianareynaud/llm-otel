"""Context assertion helpers for eval harness.

Small explicit functions that check context metadata presence and values.
These are not a framework or plugin system.
"""


def check_context_metadata(response: dict) -> tuple[bool, str]:
    """Check that context metadata fields are present and valid.

    Args:
        response: Response dictionary to check

    Returns:
        Tuple of (pass, reason)
    """
    required_fields = ["turn_index", "context_tokens_used", "context_strategy_applied"]

    for field in required_fields:
        if field not in response:
            return False, f"Field '{field}' not present"

    # Check turn_index is non-negative integer
    turn_index = response["turn_index"]
    if not isinstance(turn_index, int) or turn_index < 0:
        return False, f"turn_index must be non-negative integer, got {turn_index}"

    # Check context_tokens_used is non-negative integer
    context_tokens = response["context_tokens_used"]
    if not isinstance(context_tokens, int) or context_tokens < 0:
        return False, f"context_tokens_used must be non-negative integer, got {context_tokens}"

    return True, "ok"


def check_context_strategy_value(response: dict, expected: str) -> tuple[bool, str]:
    """Check that context_strategy_applied matches expected value.

    Args:
        response: Response dictionary to check
        expected: Expected context strategy ("full", "sliding_window", or "summarized")

    Returns:
        Tuple of (pass, reason)
    """
    if "context_strategy_applied" not in response:
        return False, "Field 'context_strategy_applied' not present"

    actual = response["context_strategy_applied"]
    if actual != expected:
        return False, f"context_strategy_applied is '{actual}', expected '{expected}'"

    return True, "ok"


def check_turn_index(response: dict, expected: int) -> tuple[bool, str]:
    """Check that turn_index matches expected value.

    Args:
        response: Response dictionary to check
        expected: Expected turn index

    Returns:
        Tuple of (pass, reason)
    """
    if "turn_index" not in response:
        return False, "Field 'turn_index' not present"

    actual = response["turn_index"]
    if actual != expected:
        return False, f"turn_index is {actual}, expected {expected}"

    return True, "ok"

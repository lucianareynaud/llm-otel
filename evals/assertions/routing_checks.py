"""Routing assertion helpers for eval harness.

Small explicit functions that check routing metadata presence and values.
These are not a framework or plugin system.
"""


def check_routing_decision(response: dict, expected: str) -> tuple[bool, str]:
    """Check that routing_decision matches expected value.

    Args:
        response: Response dictionary to check
        expected: Expected routing decision ("cheap" or "expensive")

    Returns:
        Tuple of (pass, reason)
    """
    if "routing_decision" not in response:
        return False, "Field 'routing_decision' not present"

    actual = response["routing_decision"]
    if actual != expected:
        return False, f"routing_decision is '{actual}', expected '{expected}'"

    return True, "ok"


def check_selected_model_present(response: dict) -> tuple[bool, str]:
    """Check that selected_model field is present and non-empty.

    Args:
        response: Response dictionary to check

    Returns:
        Tuple of (pass, reason)
    """
    if "selected_model" not in response:
        return False, "Field 'selected_model' not present"

    value = response["selected_model"]
    if not value or (isinstance(value, str) and len(value) == 0):
        return False, "Field 'selected_model' is empty"

    return True, "ok"


def check_routing_metadata(response: dict) -> tuple[bool, str]:
    """Check that routing metadata fields are present and non-empty.

    Args:
        response: Response dictionary to check

    Returns:
        Tuple of (pass, reason)
    """
    required_fields = ["selected_model", "routing_decision"]

    for field in required_fields:
        if field not in response:
            return False, f"Field '{field}' not present"

        value = response[field]
        if not value or (isinstance(value, str) and len(value) == 0):
            return False, f"Field '{field}' is empty"

    return True, "ok"

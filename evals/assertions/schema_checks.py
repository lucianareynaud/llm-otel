"""Schema assertion helpers for eval harness.

Small explicit functions that check response structure and field presence.
These are not a framework or plugin system.
"""

import json


def check_required_fields(response: dict, fields: list[str]) -> tuple[bool, str]:
    """Check that all required fields are present in the response.

    Args:
        response: Response dictionary to check
        fields: List of required field names

    Returns:
        Tuple of (pass, reason)
    """
    missing = [field for field in fields if field not in response]
    if missing:
        return False, f"Missing required fields: {missing}"
    return True, "ok"


def check_field_type(response: dict, field: str, expected_type: type) -> tuple[bool, str]:
    """Check that a field has the expected type.

    Args:
        response: Response dictionary to check
        field: Field name to check
        expected_type: Expected Python type

    Returns:
        Tuple of (pass, reason)
    """
    if field not in response:
        return False, f"Field '{field}' not present"

    value = response[field]
    if not isinstance(value, expected_type):
        got = type(value).__name__
        return False, f"Field '{field}' has type {got}, expected {expected_type.__name__}"

    return True, "ok"


def check_max_length(value: str, max_length: int) -> tuple[bool, str]:
    """Check that a string value is under the maximum length.

    Args:
        value: String value to check
        max_length: Maximum allowed length

    Returns:
        Tuple of (pass, reason)
    """
    if len(value) > max_length:
        return False, f"Value length {len(value)} exceeds max {max_length}"
    return True, "ok"


def check_response_size(response: dict, max_chars: int) -> tuple[bool, str]:
    """Check that JSON-serialized response is under max_chars.

    Args:
        response: Response dictionary to check
        max_chars: Maximum allowed character count

    Returns:
        Tuple of (pass, reason)
    """
    serialized = json.dumps(response)
    if len(serialized) > max_chars:
        return False, f"Response size {len(serialized)} exceeds max {max_chars}"
    return True, "ok"

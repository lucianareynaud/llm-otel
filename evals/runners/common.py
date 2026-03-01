"""Small utility helpers for eval runners.

This is not a framework or abstraction layer.
Just tiny helpers for dataset loading and result writing.
"""

import json
import os
from datetime import UTC, datetime


def load_jsonl_cases(path: str) -> list[dict]:
    """Load test cases from a JSONL file."""
    cases: list[dict] = []
    with open(path, encoding="utf-8") as file_handle:
        for line in file_handle:
            line = line.strip()
            if line:
                cases.append(json.loads(line))
    return cases


def write_eval_results(path: str, payload: dict) -> None:
    """Write eval results to a JSON file."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as file_handle:
        json.dump(payload, file_handle, indent=2)


def utc_timestamp() -> str:
    """Generate UTC timestamp in ISO format."""
    return datetime.now(UTC).isoformat()

#!/usr/bin/env python3
"""Eval runner for /classify-complexity route.

This runner executes bounded regression checks for the classify-complexity route.
It verifies schema compliance, exact deterministic output matching, and bounded behavior.
"""

import sys
from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app
from evals.assertions.schema_checks import check_required_fields, check_response_size
from evals.runners.common import load_jsonl_cases, utc_timestamp, write_eval_results


DATASET_PATH = Path("evals/datasets/classify_cases.jsonl")
OUTPUT_PATH = Path("artifacts/reports/classify_eval_results.json")
REQUIRED_FIELDS = ["complexity", "recommended_tier", "needs_escalation"]


def _check_exact_field(response_data: dict, expected: dict, field: str) -> tuple[bool, str]:
    """Check that a response field exactly matches the expected value."""
    if field not in response_data:
        return False, f"Field '{field}' not present"

    actual_value = response_data[field]
    expected_value = expected[field]

    if actual_value != expected_value:
        return False, f"{field} is {actual_value!r}, expected {expected_value!r}"

    return True, "ok"


def run_classify_eval() -> int:
    """Run eval for /classify-complexity route.

    Returns:
        Exit code: 0 if all pass, 1 if any fail.
    """
    client = TestClient(app)
    cases = load_jsonl_cases(str(DATASET_PATH))

    results: list[dict] = []
    passed = 0
    failed = 0

    for case in cases:
        case_id = case["id"]
        input_data = case["input"]
        expected = case["expected"]

        response = client.post("/classify-complexity", json=input_data)

        if response.status_code != 200:
            results.append(
                {
                    "case_id": case_id,
                    "status": "fail",
                    "reason": f"HTTP {response.status_code}",
                    "assertions": {},
                }
            )
            failed += 1
            continue

        response_data = response.json()
        assertions: dict[str, bool] = {}
        failure_reasons: list[str] = []

        ok, reason = check_required_fields(response_data, REQUIRED_FIELDS)
        assertions["required_fields_present"] = ok
        if not ok:
            failure_reasons.append(reason)

        ok, reason = _check_exact_field(response_data, expected, "complexity")
        assertions["complexity_match"] = ok
        if not ok:
            failure_reasons.append(reason)

        ok, reason = _check_exact_field(response_data, expected, "recommended_tier")
        assertions["recommended_tier_match"] = ok
        if not ok:
            failure_reasons.append(reason)

        ok, reason = _check_exact_field(response_data, expected, "needs_escalation")
        assertions["needs_escalation_match"] = ok
        if not ok:
            failure_reasons.append(reason)

        ok, reason = check_response_size(response_data, 500)
        assertions["bounded_size"] = ok
        if not ok:
            failure_reasons.append(reason)

        if failure_reasons:
            results.append(
                {
                    "case_id": case_id,
                    "status": "fail",
                    "reason": "; ".join(failure_reasons),
                    "assertions": assertions,
                }
            )
            failed += 1
        else:
            results.append(
                {
                    "case_id": case_id,
                    "status": "pass",
                    "assertions": assertions,
                }
            )
            passed += 1

    payload = {
        "route": "/classify-complexity",
        "timestamp": utc_timestamp(),
        "total_cases": len(cases),
        "passed": passed,
        "failed": failed,
        "results": results,
    }
    write_eval_results(str(OUTPUT_PATH), payload)

    print(f"Classify eval: {passed}/{len(cases)} passed")
    if failed > 0:
        print("Failed cases:")
        for result in results:
            if result["status"] == "fail":
                print(f"  - {result['case_id']}: {result.get('reason', 'unknown')}")

    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(run_classify_eval())
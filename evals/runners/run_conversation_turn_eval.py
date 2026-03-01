#!/usr/bin/env python3
"""Eval runner for /conversation-turn route.

This runner executes bounded regression checks for the conversation-turn route.
It verifies schema compliance, context metadata presence, and bounded behavior.

Default eval mode mocks gateway calls to avoid live provider dependency.
"""

import sys
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.main import app
from evals.assertions.context_checks import (
    check_context_metadata,
    check_context_strategy_value,
    check_turn_index,
)
from evals.assertions.schema_checks import check_required_fields, check_response_size
from evals.runners.common import load_jsonl_cases, utc_timestamp, write_eval_results
from gateway.client import GatewayResult


DATASET_PATH = Path("evals/datasets/conversation_turn_cases.jsonl")
OUTPUT_PATH = Path("artifacts/reports/conversation_turn_eval_results.json")
REQUIRED_FIELDS = ["answer", "turn_index", "context_tokens_used", "context_strategy_applied"]


def _mock_call_llm(
    prompt: str,
    model_tier: str,
    route_name: str,
    metadata: dict | None = None,
) -> GatewayResult:
    """Mock implementation of call_llm for deterministic eval execution."""
    return GatewayResult(
        text="Mock conversation response",
        selected_model="gpt-5.2",
        request_id="mock-request-id",
        tokens_in=15,
        tokens_out=25,
        estimated_cost_usd=0.002,
        cache_hit=False,
    )


def run_conversation_turn_eval() -> int:
    """Run eval for /conversation-turn route.

    Returns:
        Exit code: 0 if all pass, 1 if any fail.
    """
    cases = load_jsonl_cases(str(DATASET_PATH))
    results: list[dict] = []
    passed = 0
    failed = 0

    with patch("app.routes.conversation_turn.call_llm", side_effect=_mock_call_llm):
        client = TestClient(app)

        for case in cases:
            case_id = case["id"]
            input_data = case["input"]
            expected = case["expected"]

            response = client.post("/conversation-turn", json=input_data)

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

            answer_value = response_data.get("answer")
            answer_non_empty = isinstance(answer_value, str) and len(answer_value) > 0
            assertions["answer_non_empty"] = answer_non_empty
            if not answer_non_empty:
                failure_reasons.append("Field 'answer' is empty or invalid")

            ok, reason = check_context_metadata(response_data)
            assertions["context_metadata_valid"] = ok
            if not ok:
                failure_reasons.append(reason)

            if "turn_index" in expected:
                ok, reason = check_turn_index(response_data, expected["turn_index"])
                assertions["turn_index_match"] = ok
                if not ok:
                    failure_reasons.append(reason)

            if "context_strategy_applied" in expected:
                ok, reason = check_context_strategy_value(
                    response_data,
                    expected["context_strategy_applied"],
                )
                assertions["context_strategy_match"] = ok
                if not ok:
                    failure_reasons.append(reason)

            ok, reason = check_response_size(response_data, 5000)
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
        "route": "/conversation-turn",
        "timestamp": utc_timestamp(),
        "total_cases": len(cases),
        "passed": passed,
        "failed": failed,
        "results": results,
    }
    write_eval_results(str(OUTPUT_PATH), payload)

    print(f"Conversation-turn eval: {passed}/{len(cases)} passed")
    if failed > 0:
        print("Failed cases:")
        for result in results:
            if result["status"] == "fail":
                print(f"  - {result['case_id']}: {result.get('reason', 'unknown')}")

    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(run_conversation_turn_eval())
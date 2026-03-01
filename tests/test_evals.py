"""Tests for eval harness components.

These tests verify:
- dataset loading works correctly
- assertion helpers return correct pass/fail outcomes
- runner output format is correct
- runner smoke execution works with bounded deterministic inputs
"""

import json
import os
import tempfile
from unittest.mock import patch

from evals.assertions.context_checks import (
    check_context_metadata,
    check_context_strategy_value,
    check_turn_index,
)
from evals.assertions.routing_checks import (
    check_routing_decision,
    check_routing_metadata,
    check_selected_model_present,
)
from evals.assertions.schema_checks import (
    check_field_type,
    check_max_length,
    check_required_fields,
    check_response_size,
)
from evals.runners.common import load_jsonl_cases, utc_timestamp, write_eval_results
from evals.runners.run_answer_routed_eval import run_answer_routed_eval
from evals.runners.run_classify_eval import run_classify_eval
from evals.runners.run_conversation_turn_eval import run_conversation_turn_eval


class TestDatasetLoading:
    """Tests for JSONL dataset loading."""

    def test_load_valid_jsonl(self):
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".jsonl", delete=False, encoding="utf-8"
        ) as file_handle:
            file_handle.write('{"id": "case_001", "input": {"message": "test"}}\n')
            file_handle.write('{"id": "case_002", "input": {"message": "test2"}}\n')
            temp_path = file_handle.name

        try:
            cases = load_jsonl_cases(temp_path)
            assert len(cases) == 2
            assert cases[0]["id"] == "case_001"
            assert cases[1]["id"] == "case_002"
        finally:
            os.unlink(temp_path)

    def test_load_empty_lines_ignored(self):
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".jsonl", delete=False, encoding="utf-8"
        ) as file_handle:
            file_handle.write('{"id": "case_001"}\n')
            file_handle.write("\n")
            file_handle.write('{"id": "case_002"}\n')
            temp_path = file_handle.name

        try:
            cases = load_jsonl_cases(temp_path)
            assert len(cases) == 2
        finally:
            os.unlink(temp_path)


class TestResultWriting:
    """Tests for eval result writing."""

    def test_write_eval_results(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = os.path.join(tmpdir, "subdir", "results.json")
            payload = {
                "route": "/test",
                "total_cases": 5,
                "passed": 5,
                "failed": 0,
                "results": [],
            }

            write_eval_results(output_path, payload)

            assert os.path.exists(output_path)
            with open(output_path, encoding="utf-8") as file_handle:
                loaded = json.load(file_handle)

            assert loaded["route"] == "/test"
            assert loaded["total_cases"] == 5

    def test_utc_timestamp_format(self):
        timestamp = utc_timestamp()
        assert "T" in timestamp
        assert "+" in timestamp or "Z" in timestamp or timestamp.endswith("+00:00")


class TestSchemaChecks:
    """Tests for schema assertion helpers."""

    def test_check_required_fields_all_present(self):
        response = {"field1": "value1", "field2": "value2", "field3": "value3"}
        passed, reason = check_required_fields(response, ["field1", "field2"])
        assert passed is True
        assert reason == "ok"

    def test_check_required_fields_missing(self):
        response = {"field1": "value1"}
        passed, reason = check_required_fields(response, ["field1", "field2", "field3"])
        assert passed is False
        assert "field2" in reason
        assert "field3" in reason

    def test_check_field_type_correct(self):
        response = {"name": "test", "count": 42, "active": True}
        assert check_field_type(response, "name", str) == (True, "ok")
        assert check_field_type(response, "count", int) == (True, "ok")
        assert check_field_type(response, "active", bool) == (True, "ok")

    def test_check_field_type_incorrect(self):
        response = {"count": "42"}
        passed, reason = check_field_type(response, "count", int)
        assert passed is False
        assert "str" in reason
        assert "int" in reason

    def test_check_field_type_missing(self):
        response = {}
        passed, reason = check_field_type(response, "missing", str)
        assert passed is False
        assert "not present" in reason

    def test_check_max_length_under_limit(self):
        passed, reason = check_max_length("short", 100)
        assert passed is True
        assert reason == "ok"

    def test_check_max_length_over_limit(self):
        passed, reason = check_max_length("a" * 101, 100)
        assert passed is False
        assert "101" in reason
        assert "100" in reason

    def test_check_response_size_under_limit(self):
        response = {"field": "value"}
        passed, reason = check_response_size(response, 1000)
        assert passed is True
        assert reason == "ok"

    def test_check_response_size_over_limit(self):
        response = {"field": "x" * 1000}
        passed, reason = check_response_size(response, 100)
        assert passed is False
        assert "exceeds" in reason


class TestRoutingChecks:
    """Tests for routing assertion helpers."""

    def test_check_routing_decision_match(self):
        response = {"routing_decision": "cheap"}
        passed, reason = check_routing_decision(response, "cheap")
        assert passed is True
        assert reason == "ok"

    def test_check_routing_decision_mismatch(self):
        response = {"routing_decision": "expensive"}
        passed, reason = check_routing_decision(response, "cheap")
        assert passed is False
        assert "expensive" in reason
        assert "cheap" in reason

    def test_check_routing_decision_missing(self):
        response = {}
        passed, reason = check_routing_decision(response, "cheap")
        assert passed is False
        assert "not present" in reason

    def test_check_selected_model_present_valid(self):
        response = {"selected_model": "gpt-4o-mini"}
        passed, reason = check_selected_model_present(response)
        assert passed is True
        assert reason == "ok"

    def test_check_selected_model_missing(self):
        response = {}
        passed, reason = check_selected_model_present(response)
        assert passed is False
        assert "not present" in reason

    def test_check_selected_model_empty(self):
        response = {"selected_model": ""}
        passed, reason = check_selected_model_present(response)
        assert passed is False
        assert "empty" in reason

    def test_check_routing_metadata_valid(self):
        response = {"selected_model": "gpt-4o-mini", "routing_decision": "cheap"}
        passed, reason = check_routing_metadata(response)
        assert passed is True
        assert reason == "ok"

    def test_check_routing_metadata_missing_field(self):
        response = {"selected_model": "gpt-4o-mini"}
        passed, reason = check_routing_metadata(response)
        assert passed is False
        assert "routing_decision" in reason


class TestContextChecks:
    """Tests for context assertion helpers."""

    def test_check_context_metadata_valid(self):
        response = {
            "turn_index": 2,
            "context_tokens_used": 100,
            "context_strategy_applied": "full",
        }
        passed, reason = check_context_metadata(response)
        assert passed is True
        assert reason == "ok"

    def test_check_context_metadata_missing_field(self):
        response = {"turn_index": 2, "context_tokens_used": 100}
        passed, reason = check_context_metadata(response)
        assert passed is False
        assert "context_strategy_applied" in reason

    def test_check_context_metadata_negative_turn_index(self):
        response = {
            "turn_index": -1,
            "context_tokens_used": 100,
            "context_strategy_applied": "full",
        }
        passed, reason = check_context_metadata(response)
        assert passed is False
        assert "non-negative" in reason

    def test_check_context_metadata_negative_tokens(self):
        response = {
            "turn_index": 2,
            "context_tokens_used": -10,
            "context_strategy_applied": "full",
        }
        passed, reason = check_context_metadata(response)
        assert passed is False
        assert "non-negative" in reason

    def test_check_context_strategy_value_match(self):
        response = {"context_strategy_applied": "sliding_window"}
        passed, reason = check_context_strategy_value(response, "sliding_window")
        assert passed is True
        assert reason == "ok"

    def test_check_context_strategy_value_mismatch(self):
        response = {"context_strategy_applied": "full"}
        passed, reason = check_context_strategy_value(response, "sliding_window")
        assert passed is False
        assert "full" in reason
        assert "sliding_window" in reason

    def test_check_turn_index_match(self):
        response = {"turn_index": 3}
        passed, reason = check_turn_index(response, 3)
        assert passed is True
        assert reason == "ok"

    def test_check_turn_index_mismatch(self):
        response = {"turn_index": 5}
        passed, reason = check_turn_index(response, 3)
        assert passed is False
        assert "5" in reason
        assert "3" in reason


class TestRunnerSmoke:
    """Small smoke tests for runner execution."""

    def test_run_classify_eval_smoke(self):
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".jsonl", delete=False, encoding="utf-8"
        ) as file_handle:
            file_handle.write(
                '{"id": "test_001", "input": {"message": "What is 2+2?"}, '
                '"expected": {"complexity": "simple", "recommended_tier": "cheap",'
                ' "needs_escalation": false}}\n'
            )
            temp_dataset = file_handle.name

        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = os.path.join(tmpdir, "classify_results.json")

            with (
                patch("evals.runners.run_classify_eval.DATASET_PATH", temp_dataset),
                patch("evals.runners.run_classify_eval.OUTPUT_PATH", output_path),
            ):
                exit_code = run_classify_eval()

            assert exit_code == 0
            assert os.path.exists(output_path)

            with open(output_path, encoding="utf-8") as file_handle:
                payload = json.load(file_handle)

            assert payload["route"] == "/classify-complexity"
            assert payload["total_cases"] == 1
            assert payload["passed"] == 1
            assert payload["failed"] == 0

        os.unlink(temp_dataset)

    def test_run_answer_routed_eval_smoke(self):
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".jsonl", delete=False, encoding="utf-8"
        ) as file_handle:
            file_handle.write(
                '{"id": "test_001", "input": {"message": "What is 2+2?"}, '
                '"expected": {"routing_decision": "cheap", "min_answer_length": 1}}\n'
            )
            temp_dataset = file_handle.name

        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = os.path.join(tmpdir, "answer_routed_results.json")

            with (
                patch("evals.runners.run_answer_routed_eval.DATASET_PATH", temp_dataset),
                patch("evals.runners.run_answer_routed_eval.OUTPUT_PATH", output_path),
            ):
                exit_code = run_answer_routed_eval()

            assert exit_code == 0
            assert os.path.exists(output_path)

            with open(output_path, encoding="utf-8") as file_handle:
                payload = json.load(file_handle)

            assert payload["route"] == "/answer-routed"
            assert payload["total_cases"] == 1
            assert payload["passed"] == 1
            assert payload["failed"] == 0

        os.unlink(temp_dataset)

    def test_run_conversation_turn_eval_smoke(self):
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".jsonl", delete=False, encoding="utf-8"
        ) as file_handle:
            file_handle.write(
                '{"id": "test_001", "input": {"conversation_id": "conv_001",'
                ' "message": "Hello", "history": [], "context_strategy": "full"},'
                ' "expected": {"context_strategy_applied": "full",'
                ' "min_answer_length": 1, "turn_index": 0}}\n'
            )
            temp_dataset = file_handle.name

        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = os.path.join(tmpdir, "conversation_turn_results.json")

            module = "evals.runners.run_conversation_turn_eval"
            with (
                patch(f"{module}.DATASET_PATH", temp_dataset),
                patch(f"{module}.OUTPUT_PATH", output_path),
            ):
                exit_code = run_conversation_turn_eval()

            assert exit_code == 0
            assert os.path.exists(output_path)

            with open(output_path, encoding="utf-8") as file_handle:
                payload = json.load(file_handle)

            assert payload["route"] == "/conversation-turn"
            assert payload["total_cases"] == 1
            assert payload["passed"] == 1
            assert payload["failed"] == 0

        os.unlink(temp_dataset)

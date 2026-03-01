"""Tests for the reporting module.

These tests verify deterministic telemetry loading, normalization, aggregation,
before/after comparison, eval loading, and markdown rendering.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from reporting.make_report import (
    AggregateMetrics,
    NormalizedTelemetryRow,
    aggregate_metrics,
    build_route_aggregates,
    compare_aggregates,
    group_rows_by_route,
    load_eval_result,
    load_jsonl_telemetry,
    normalize_telemetry_row,
    percentile,
    render_markdown_report,
)


class TestNormalizeTelemetryRow:
    """Tests for telemetry row normalization."""

    def test_normalize_valid_row(self):
        raw = {
            "route": "/answer-routed",
            "latency_ms": 123.4,
            "estimated_cost_usd": 0.0012,
            "status": "success",
            "schema_valid": True,
            "error_type": None,
        }

        row = normalize_telemetry_row(raw)

        assert row == NormalizedTelemetryRow(
            route="/answer-routed",
            latency_ms=123.4,
            estimated_cost_usd=0.0012,
            status="success",
            schema_valid=True,
            error_type=None,
        )

    def test_normalize_valid_row_with_string_coercions(self):
        raw = {
            "route": "/conversation-turn",
            "latency_ms": "456.7",
            "estimated_cost_usd": "0.0034",
            "status": "error",
            "schema_valid": "false",
            "error_type": "timeout",
        }

        row = normalize_telemetry_row(raw)

        assert row == NormalizedTelemetryRow(
            route="/conversation-turn",
            latency_ms=456.7,
            estimated_cost_usd=0.0034,
            status="error",
            schema_valid=False,
            error_type="timeout",
        )

    @pytest.mark.parametrize(
        "raw",
        [
            {
                "latency_ms": 123.4,
                "estimated_cost_usd": 0.001,
                "status": "success",
                "schema_valid": True,
            },  # missing route
            {
                "route": "",
                "latency_ms": 123.4,
                "estimated_cost_usd": 0.001,
                "status": "success",
                "schema_valid": True,
            },  # empty route
            {
                "route": "/x",
                "latency_ms": -1,
                "estimated_cost_usd": 0.001,
                "status": "success",
                "schema_valid": True,
            },  # negative latency
            {
                "route": "/x",
                "latency_ms": "abc",
                "estimated_cost_usd": 0.001,
                "status": "success",
                "schema_valid": True,
            },  # invalid latency
            {
                "route": "/x",
                "latency_ms": 123.4,
                "estimated_cost_usd": -0.1,
                "status": "success",
                "schema_valid": True,
            },  # negative cost
            {
                "route": "/x",
                "latency_ms": 123.4,
                "estimated_cost_usd": 0.001,
                "status": "weird",
                "schema_valid": True,
            },  # invalid status
            {
                "route": "/x",
                "latency_ms": 123.4,
                "estimated_cost_usd": 0.001,
                "status": "success",
                "schema_valid": "maybe",
            },  # invalid schema_valid
        ],
    )
    def test_normalize_invalid_rows(self, raw):
        assert normalize_telemetry_row(raw) is None


class TestLoadJsonlTelemetry:
    """Tests for JSONL telemetry loading."""

    def test_load_valid_jsonl(self, tmp_path: Path):
        file_path = tmp_path / "telemetry.jsonl"
        file_path.write_text(
            "\n".join(
                [
                    json.dumps(
                        {
                            "route": "/answer-routed",
                            "latency_ms": 100.0,
                            "estimated_cost_usd": 0.001,
                            "status": "success",
                            "schema_valid": True,
                            "error_type": None,
                        }
                    ),
                    json.dumps(
                        {
                            "route": "/conversation-turn",
                            "latency_ms": 200.0,
                            "estimated_cost_usd": 0.002,
                            "status": "error",
                            "schema_valid": False,
                            "error_type": "timeout",
                        }
                    ),
                ]
            ),
            encoding="utf-8",
        )

        rows, malformed_count = load_jsonl_telemetry(str(file_path))

        assert malformed_count == 0
        assert len(rows) == 2
        assert rows[0].route == "/answer-routed"
        assert rows[1].route == "/conversation-turn"

    def test_load_jsonl_ignores_empty_lines(self, tmp_path: Path):
        file_path = tmp_path / "telemetry.jsonl"
        file_path.write_text(
            "\n".join(
                [
                    "",
                    json.dumps(
                        {
                            "route": "/answer-routed",
                            "latency_ms": 100.0,
                            "estimated_cost_usd": 0.001,
                            "status": "success",
                            "schema_valid": True,
                            "error_type": None,
                        }
                    ),
                    "",
                ]
            ),
            encoding="utf-8",
        )

        rows, malformed_count = load_jsonl_telemetry(str(file_path))

        assert malformed_count == 0
        assert len(rows) == 1

    def test_load_jsonl_counts_invalid_json_as_malformed(self, tmp_path: Path):
        file_path = tmp_path / "telemetry.jsonl"
        file_path.write_text(
            "\n".join(
                [
                    '{"route": "/x", "latency_ms": 10.0, "estimated_cost_usd": 0.1,'
                    ' "status": "success", "schema_valid": true}',
                    '{"route": "/bad", "latency_ms": ',
                    '{"route": "/y", "latency_ms": 20.0, "estimated_cost_usd": 0.2,'
                    ' "status": "error", "schema_valid": false}',
                ]
            ),
            encoding="utf-8",
        )

        rows, malformed_count = load_jsonl_telemetry(str(file_path))

        assert len(rows) == 2
        assert malformed_count == 1

    def test_load_jsonl_counts_missing_required_fields_as_malformed(self, tmp_path: Path):
        file_path = tmp_path / "telemetry.jsonl"
        file_path.write_text(
            "\n".join(
                [
                    json.dumps(
                        {
                            "route": "/ok",
                            "latency_ms": 10.0,
                            "estimated_cost_usd": 0.001,
                            "status": "success",
                            "schema_valid": True,
                        }
                    ),
                    json.dumps(
                        {
                            "latency_ms": 20.0,
                            "estimated_cost_usd": 0.002,
                            "status": "success",
                            "schema_valid": True,
                        }
                    ),
                ]
            ),
            encoding="utf-8",
        )

        rows, malformed_count = load_jsonl_telemetry(str(file_path))

        assert len(rows) == 1
        assert malformed_count == 1

    def test_load_jsonl_counts_invalid_field_types_as_malformed(self, tmp_path: Path):
        file_path = tmp_path / "telemetry.jsonl"
        file_path.write_text(
            "\n".join(
                [
                    json.dumps(
                        {
                            "route": "/ok",
                            "latency_ms": 10.0,
                            "estimated_cost_usd": 0.001,
                            "status": "success",
                            "schema_valid": True,
                        }
                    ),
                    json.dumps(
                        {
                            "route": "/bad",
                            "latency_ms": "not-a-number",
                            "estimated_cost_usd": 0.002,
                            "status": "success",
                            "schema_valid": True,
                        }
                    ),
                ]
            ),
            encoding="utf-8",
        )

        rows, malformed_count = load_jsonl_telemetry(str(file_path))

        assert len(rows) == 1
        assert malformed_count == 1

    def test_load_jsonl_file_not_found(self):
        with pytest.raises(FileNotFoundError):
            load_jsonl_telemetry("does_not_exist.jsonl")


class TestPercentile:
    """Tests for deterministic percentile calculation."""

    def test_percentile_empty(self):
        assert percentile([], 50.0) == 0.0

    def test_percentile_single_value(self):
        assert percentile([42.0], 50.0) == 42.0
        assert percentile([42.0], 95.0) == 42.0

    def test_percentile_multiple_values(self):
        values = [10.0, 20.0, 30.0, 40.0, 50.0]

        assert percentile(values, 50.0) == pytest.approx(30.0)
        assert percentile(values, 95.0) == pytest.approx(48.0)

    def test_percentile_unsorted_values(self):
        values = [50.0, 10.0, 40.0, 20.0, 30.0]

        assert percentile(values, 50.0) == pytest.approx(30.0)
        assert percentile(values, 95.0) == pytest.approx(48.0)


class TestAggregateMetrics:
    """Tests for aggregate metric calculation."""

    def test_aggregate_metrics_empty(self):
        metrics = aggregate_metrics([])

        assert metrics == AggregateMetrics(
            request_count=0,
            latency_p50_ms=0.0,
            latency_p95_ms=0.0,
            estimated_total_cost_usd=0.0,
            estimated_average_cost_usd=0.0,
            error_rate=0.0,
            schema_valid_rate=0.0,
            error_count=0,
            unknown_error_count=0,
        )

    def test_aggregate_metrics_non_empty(self):
        rows = [
            NormalizedTelemetryRow("/a", 100.0, 0.001, "success", True, None),
            NormalizedTelemetryRow("/a", 200.0, 0.002, "error", False, "unknown"),
            NormalizedTelemetryRow("/a", 300.0, 0.003, "success", True, None),
        ]

        metrics = aggregate_metrics(rows)

        assert metrics.request_count == 3
        assert metrics.latency_p50_ms == pytest.approx(200.0)
        assert metrics.latency_p95_ms == pytest.approx(290.0)
        assert metrics.estimated_total_cost_usd == pytest.approx(0.006)
        assert metrics.estimated_average_cost_usd == pytest.approx(0.002)
        assert metrics.error_rate == pytest.approx(1 / 3)
        assert metrics.schema_valid_rate == pytest.approx(2 / 3)
        assert metrics.error_count == 1
        assert metrics.unknown_error_count == 1


class TestGroupingAndRouteAggregates:
    """Tests for route grouping and route-level aggregate building."""

    def test_group_rows_by_route(self):
        rows = [
            NormalizedTelemetryRow("/route1", 100.0, 0.001, "success", True, None),
            NormalizedTelemetryRow("/route2", 200.0, 0.002, "success", True, None),
            NormalizedTelemetryRow("/route1", 150.0, 0.0015, "error", False, "unknown"),
        ]

        grouped = group_rows_by_route(rows)

        assert set(grouped.keys()) == {"/route1", "/route2"}
        assert len(grouped["/route1"]) == 2
        assert len(grouped["/route2"]) == 1

    def test_build_route_aggregates(self):
        rows = [
            NormalizedTelemetryRow("/route1", 100.0, 0.001, "success", True, None),
            NormalizedTelemetryRow("/route2", 200.0, 0.002, "success", True, None),
            NormalizedTelemetryRow("/route1", 150.0, 0.0015, "success", True, None),
        ]

        per_route, overall = build_route_aggregates(rows)

        assert len(per_route) == 2
        assert per_route["/route1"].request_count == 2
        assert per_route["/route2"].request_count == 1
        assert overall.request_count == 3
        assert overall.estimated_total_cost_usd == pytest.approx(0.0045)
        assert overall.estimated_average_cost_usd == pytest.approx(0.0015)


class TestCompareAggregates:
    """Tests for before/after aggregate comparison."""

    def test_compare_aggregates(self):
        before = AggregateMetrics(
            request_count=10,
            latency_p50_ms=100.0,
            latency_p95_ms=200.0,
            estimated_total_cost_usd=0.010,
            estimated_average_cost_usd=0.001,
            error_rate=0.2,
            schema_valid_rate=0.9,
            error_count=2,
            unknown_error_count=1,
        )
        after = AggregateMetrics(
            request_count=12,
            latency_p50_ms=90.0,
            latency_p95_ms=180.0,
            estimated_total_cost_usd=0.014,
            estimated_average_cost_usd=0.0011666667,
            error_rate=0.1,
            schema_valid_rate=1.0,
            error_count=1,
            unknown_error_count=0,
        )

        delta = compare_aggregates(before, after)

        assert delta["request_count_delta"] == 2
        assert delta["latency_p50_ms_delta"] == pytest.approx(-10.0)
        assert delta["latency_p95_ms_delta"] == pytest.approx(-20.0)
        assert delta["estimated_total_cost_usd_delta"] == pytest.approx(0.004)
        assert delta["estimated_average_cost_usd_delta"] == pytest.approx(0.0001666667)
        assert delta["error_rate_delta"] == pytest.approx(-0.1)


class TestLoadEvalResult:
    """Tests for eval JSON loading."""

    def test_load_existing_eval_result(self, tmp_path: Path):
        file_path = tmp_path / "eval.json"
        payload = {
            "route": "/classify-complexity",
            "total_cases": 5,
            "passed": 5,
            "failed": 0,
            "results": [],
        }
        file_path.write_text(json.dumps(payload), encoding="utf-8")

        loaded = load_eval_result(str(file_path))

        assert loaded == payload

    def test_load_missing_eval_result_returns_none(self):
        assert load_eval_result("does_not_exist.json") is None

    def test_load_none_eval_path_returns_none(self):
        assert load_eval_result(None) is None

    def test_load_non_dict_eval_result_returns_none(self, tmp_path: Path):
        file_path = tmp_path / "eval.json"
        file_path.write_text(json.dumps(["not", "a", "dict"]), encoding="utf-8")

        loaded = load_eval_result(str(file_path))

        assert loaded is None


class TestRenderMarkdownReport:
    """Tests for markdown report rendering."""

    def test_render_single_run_report_contains_required_sections(self):
        after_rows = [
            NormalizedTelemetryRow("/answer-routed", 120.0, 0.0012, "success", True, None),
            NormalizedTelemetryRow("/conversation-turn", 220.0, 0.0022, "error", False, "unknown"),
        ]
        after_by_route, after_overall = build_route_aggregates(after_rows)

        report = render_markdown_report(
            before_log_path=None,
            after_log_path="artifacts/logs/telemetry.jsonl",
            before_rows=[],
            after_rows=after_rows,
            malformed_before_count=0,
            malformed_after_count=1,
            before_by_route=None,
            after_by_route=after_by_route,
            before_overall=None,
            after_overall=after_overall,
            eval_payloads={
                "Classify Eval": {
                    "total_cases": 5,
                    "passed": 5,
                    "failed": 0,
                    "results": [],
                },
                "Answer Routed Eval": None,
                "Conversation Turn Eval": None,
            },
        )

        assert "# LLM Cost Control Report" in report
        assert "## Run Context" in report
        assert "## Executive Summary" in report
        assert "## Telemetry Coverage Summary" in report
        assert "## Per-Route Aggregate Table" in report
        assert "## Eval Summary" in report
        assert "## Pareto Analysis" in report
        assert "## Recommendations" in report
        assert "Answer Routed Eval" in report
        assert "Eval summary unavailable." in report
        assert "malformed telemetry row" in report.lower() or "malformed rows" in report.lower()

    def test_render_before_after_report_contains_comparison_section(self):
        before_rows = [
            NormalizedTelemetryRow("/answer-routed", 200.0, 0.0030, "success", True, None),
        ]
        after_rows = [
            NormalizedTelemetryRow("/answer-routed", 100.0, 0.0020, "success", True, None),
            NormalizedTelemetryRow("/conversation-turn", 300.0, 0.0040, "error", False, "unknown"),
        ]

        before_by_route, before_overall = build_route_aggregates(before_rows)
        after_by_route, after_overall = build_route_aggregates(after_rows)

        report = render_markdown_report(
            before_log_path="artifacts/logs/before_telemetry.jsonl",
            after_log_path="artifacts/logs/telemetry.jsonl",
            before_rows=before_rows,
            after_rows=after_rows,
            malformed_before_count=0,
            malformed_after_count=0,
            before_by_route=before_by_route,
            after_by_route=after_by_route,
            before_overall=before_overall,
            after_overall=after_overall,
            eval_payloads={
                "Classify Eval": None,
                "Answer Routed Eval": None,
                "Conversation Turn Eval": None,
            },
        )

        assert "## Before/After Comparison" in report
        assert "/answer-routed" in report
        assert "/conversation-turn" in report
        assert "Overall latency p50 delta" in report
        assert "Overall total cost delta" in report
        assert "Overall error rate delta" in report

    def test_render_report_mentions_incomplete_regression_coverage(self):
        after_rows = [
            NormalizedTelemetryRow("/conversation-turn", 100.0, 0.001, "error", False, "unknown"),
        ]
        after_by_route, after_overall = build_route_aggregates(after_rows)

        report = render_markdown_report(
            before_log_path=None,
            after_log_path="artifacts/logs/telemetry.jsonl",
            before_rows=[],
            after_rows=after_rows,
            malformed_before_count=0,
            malformed_after_count=0,
            before_by_route=None,
            after_by_route=after_by_route,
            before_overall=None,
            after_overall=after_overall,
            eval_payloads={
                "Classify Eval": None,
                "Answer Routed Eval": None,
                "Conversation Turn Eval": None,
            },
        )

        assert "Regression coverage is incomplete" in report

    def test_render_report_mentions_unknown_error_taxonomy_problem(self):
        after_rows = [
            NormalizedTelemetryRow("/conversation-turn", 100.0, 0.001, "error", False, "unknown"),
            NormalizedTelemetryRow("/conversation-turn", 120.0, 0.001, "error", False, "unknown"),
            NormalizedTelemetryRow("/conversation-turn", 140.0, 0.001, "success", True, None),
        ]
        after_by_route, after_overall = build_route_aggregates(after_rows)

        report = render_markdown_report(
            before_log_path=None,
            after_log_path="artifacts/logs/telemetry.jsonl",
            before_rows=[],
            after_rows=after_rows,
            malformed_before_count=0,
            malformed_after_count=0,
            before_by_route=None,
            after_by_route=after_by_route,
            before_overall=None,
            after_overall=after_overall,
            eval_payloads={
                "Classify Eval": {
                    "total_cases": 5,
                    "passed": 5,
                    "failed": 0,
                    "results": [],
                },
                "Answer Routed Eval": {
                    "total_cases": 5,
                    "passed": 5,
                    "failed": 0,
                    "results": [],
                },
                "Conversation Turn Eval": {
                    "total_cases": 5,
                    "passed": 5,
                    "failed": 0,
                    "results": [],
                },
            },
        )

        assert "error taxonomy" in report.lower()
        assert "unknown" in report.lower()

    def test_union_of_routes_behavior_in_before_after_rendering(self):
        before_rows = [
            NormalizedTelemetryRow("/only-before", 100.0, 0.001, "success", True, None),
        ]
        after_rows = [
            NormalizedTelemetryRow("/only-after", 200.0, 0.002, "success", True, None),
        ]

        before_by_route, before_overall = build_route_aggregates(before_rows)
        after_by_route, after_overall = build_route_aggregates(after_rows)

        report = render_markdown_report(
            before_log_path="before.jsonl",
            after_log_path="after.jsonl",
            before_rows=before_rows,
            after_rows=after_rows,
            malformed_before_count=0,
            malformed_after_count=0,
            before_by_route=before_by_route,
            after_by_route=after_by_route,
            before_overall=before_overall,
            after_overall=after_overall,
            eval_payloads={
                "Classify Eval": None,
                "Answer Routed Eval": None,
                "Conversation Turn Eval": None,
            },
        )

        assert "/only-before" in report
        assert "/only-after" in report

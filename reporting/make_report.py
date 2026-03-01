#!/usr/bin/env python3
"""Deterministic markdown reporting for telemetry and eval artifacts.

This module is downstream-only. It reads local artifact files, normalizes
telemetry rows into one canonical internal shape, computes aggregates, and
writes a markdown report.

It does not:
- call providers
- run routes
- run evals
- depend on Langfuse
- depend on notebooks
"""

from __future__ import annotations

import argparse
import json
import math
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class NormalizedTelemetryRow:
    """Canonical telemetry row shape used by reporting logic."""

    route: str
    latency_ms: float
    estimated_cost_usd: float
    status: str
    schema_valid: bool
    error_type: str | None


@dataclass(frozen=True)
class AggregateMetrics:
    """Deterministic aggregate metrics for a telemetry slice."""

    request_count: int
    latency_p50_ms: float
    latency_p95_ms: float
    estimated_total_cost_usd: float
    estimated_average_cost_usd: float
    error_rate: float
    schema_valid_rate: float
    error_count: int
    unknown_error_count: int


REQUIRED_NORMALIZED_FIELDS = {
    "route",
    "latency_ms",
    "estimated_cost_usd",
    "status",
    "schema_valid",
}


def utc_timestamp() -> str:
    """Return the current UTC timestamp in ISO-8601 format."""
    return datetime.now(UTC).isoformat()


def parse_args() -> argparse.Namespace:
    """Parse CLI arguments for report generation."""
    parser = argparse.ArgumentParser(
        description="Generate deterministic markdown reports from telemetry and eval artifacts."
    )
    parser.add_argument(
        "--before-log",
        type=str,
        default=None,
        help="Path to telemetry JSONL for the 'before' snapshot.",
    )
    parser.add_argument(
        "--after-log",
        type=str,
        required=True,
        help="Path to telemetry JSONL for the current or 'after' snapshot.",
    )
    parser.add_argument(
        "--classify-eval",
        type=str,
        default=None,
        help="Path to classify eval JSON results.",
    )
    parser.add_argument(
        "--answer-eval",
        type=str,
        default=None,
        help="Path to answer-routed eval JSON results.",
    )
    parser.add_argument(
        "--conversation-eval",
        type=str,
        default=None,
        help="Path to conversation-turn eval JSON results.",
    )
    parser.add_argument(
        "--output",
        type=str,
        required=True,
        help="Output path for the markdown report.",
    )
    return parser.parse_args()


def _coerce_float(value: Any) -> float | None:
    """Coerce a value to float if possible, otherwise return None."""
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value.strip())
        except ValueError:
            return None
    return None


def _coerce_bool(value: Any) -> bool | None:
    """Coerce a value to bool if possible, otherwise return None."""
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered == "true":
            return True
        if lowered == "false":
            return False
    return None


def normalize_telemetry_row(raw_row: dict[str, Any]) -> NormalizedTelemetryRow | None:
    """Normalize one raw telemetry row into the reporting row shape.

    A row is considered malformed, and therefore excluded from aggregation,
    when any of the required reporting fields are missing or invalid:

    - route
    - latency_ms
    - estimated_cost_usd
    - status
    - schema_valid

    This function is the only normalization boundary. All downstream
    aggregation and markdown rendering must operate on normalized rows only.
    """
    missing = [field for field in REQUIRED_NORMALIZED_FIELDS if field not in raw_row]
    if missing:
        return None

    route = raw_row.get("route")
    if not isinstance(route, str) or not route.strip():
        return None

    latency_ms = _coerce_float(raw_row.get("latency_ms"))
    estimated_cost_usd = _coerce_float(raw_row.get("estimated_cost_usd"))
    schema_valid = _coerce_bool(raw_row.get("schema_valid"))
    status = raw_row.get("status")

    if latency_ms is None or latency_ms < 0:
        return None
    if estimated_cost_usd is None or estimated_cost_usd < 0:
        return None
    if schema_valid is None:
        return None
    if status not in {"success", "error"}:
        return None

    error_type = raw_row.get("error_type")
    if error_type is not None and not isinstance(error_type, str):
        error_type = str(error_type)

    return NormalizedTelemetryRow(
        route=route.strip(),
        latency_ms=latency_ms,
        estimated_cost_usd=estimated_cost_usd,
        status=status,
        schema_valid=schema_valid,
        error_type=error_type,
    )


def load_jsonl_telemetry(path: str) -> tuple[list[NormalizedTelemetryRow], int]:
    """Load and normalize telemetry rows from a JSONL file.

    Returns:
        Tuple of:
        - list of normalized telemetry rows
        - malformed row count

    A row counts as malformed if JSON parsing fails or normalization fails.
    """
    file_path = Path(path)
    if not file_path.exists():
        raise FileNotFoundError(f"Telemetry file not found: {path}")

    normalized_rows: list[NormalizedTelemetryRow] = []
    malformed_row_count = 0

    with file_path.open("r", encoding="utf-8") as file_handle:
        for raw_line in file_handle:
            line = raw_line.strip()
            if not line:
                continue

            try:
                parsed = json.loads(line)
            except json.JSONDecodeError:
                malformed_row_count += 1
                continue

            if not isinstance(parsed, dict):
                malformed_row_count += 1
                continue

            normalized = normalize_telemetry_row(parsed)
            if normalized is None:
                malformed_row_count += 1
                continue

            normalized_rows.append(normalized)

    return normalized_rows, malformed_row_count


def load_eval_result(path: str | None) -> dict[str, Any] | None:
    """Load one eval result JSON file.

    Missing files are treated as unavailable coverage, not as hard failures.
    """
    if not path:
        return None

    file_path = Path(path)
    if not file_path.exists():
        return None

    with file_path.open("r", encoding="utf-8") as file_handle:
        payload = json.load(file_handle)

    if not isinstance(payload, dict):
        return None

    return payload


def percentile(values: list[float], p: float) -> float:
    """Compute a deterministic percentile using linear interpolation.

    Rule:
    - sort ascending
    - compute the fractional index as `p / 100 * (n - 1)`
    - linearly interpolate between the lower and upper neighbors

    This is deterministic, dependency-free, and stable for small samples.
    """
    if not values:
        return 0.0

    if len(values) == 1:
        return float(values[0])

    sorted_values = sorted(values)
    index = (p / 100.0) * (len(sorted_values) - 1)
    lower_index = math.floor(index)
    upper_index = math.ceil(index)

    lower_value = sorted_values[lower_index]
    upper_value = sorted_values[upper_index]

    if lower_index == upper_index:
        return float(lower_value)

    fraction = index - lower_index
    return float(lower_value + (upper_value - lower_value) * fraction)


def aggregate_metrics(rows: list[NormalizedTelemetryRow]) -> AggregateMetrics:
    """Aggregate route-level or overall metrics from normalized rows."""
    request_count = len(rows)
    if request_count == 0:
        return AggregateMetrics(
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

    latencies = [row.latency_ms for row in rows]
    total_cost = sum(row.estimated_cost_usd for row in rows)
    error_count = sum(1 for row in rows if row.status == "error")
    schema_valid_count = sum(1 for row in rows if row.schema_valid)
    unknown_error_count = sum(
        1 for row in rows if row.status == "error" and row.error_type == "unknown"
    )

    return AggregateMetrics(
        request_count=request_count,
        latency_p50_ms=percentile(latencies, 50.0),
        latency_p95_ms=percentile(latencies, 95.0),
        estimated_total_cost_usd=total_cost,
        estimated_average_cost_usd=(total_cost / request_count) if request_count else 0.0,
        error_rate=(error_count / request_count) if request_count else 0.0,
        schema_valid_rate=(schema_valid_count / request_count) if request_count else 0.0,
        error_count=error_count,
        unknown_error_count=unknown_error_count,
    )


def group_rows_by_route(
    rows: list[NormalizedTelemetryRow],
) -> dict[str, list[NormalizedTelemetryRow]]:
    """Group normalized telemetry rows by route."""
    grouped: dict[str, list[NormalizedTelemetryRow]] = {}
    for row in rows:
        grouped.setdefault(row.route, []).append(row)
    return grouped


def build_route_aggregates(
    rows: list[NormalizedTelemetryRow],
) -> tuple[dict[str, AggregateMetrics], AggregateMetrics]:
    """Build per-route and overall aggregates from normalized rows."""
    grouped = group_rows_by_route(rows)
    per_route = {route: aggregate_metrics(route_rows) for route, route_rows in grouped.items()}
    overall = aggregate_metrics(rows)
    return per_route, overall


def compare_aggregates(
    before_metrics: AggregateMetrics,
    after_metrics: AggregateMetrics,
) -> dict[str, float]:
    """Compute deterministic deltas between before and after aggregate metrics."""
    return {
        "request_count_delta": after_metrics.request_count - before_metrics.request_count,
        "latency_p50_ms_delta": after_metrics.latency_p50_ms - before_metrics.latency_p50_ms,
        "latency_p95_ms_delta": after_metrics.latency_p95_ms - before_metrics.latency_p95_ms,
        "estimated_total_cost_usd_delta": (
            after_metrics.estimated_total_cost_usd - before_metrics.estimated_total_cost_usd
        ),
        "estimated_average_cost_usd_delta": (
            after_metrics.estimated_average_cost_usd - before_metrics.estimated_average_cost_usd
        ),
        "error_rate_delta": after_metrics.error_rate - before_metrics.error_rate,
    }


def _fmt_float(value: float, decimals: int = 4) -> str:
    """Format a float deterministically for markdown output."""
    return f"{value:.{decimals}f}"


def _route_table_lines(route_metrics: dict[str, AggregateMetrics]) -> list[str]:
    """Render a markdown table for per-route aggregates."""
    lines = [
        "| Route | Request Count | Latency P50 (ms) | Latency P95 (ms)"
        " | Total Cost (USD) | Avg Cost (USD) | Error Rate | Schema-Valid Rate |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]

    for route in sorted(route_metrics.keys()):
        metrics = route_metrics[route]
        lines.append(
            "| "
            f"{route} | "
            f"{metrics.request_count} | "
            f"{_fmt_float(metrics.latency_p50_ms, 2)} | "
            f"{_fmt_float(metrics.latency_p95_ms, 2)} | "
            f"{_fmt_float(metrics.estimated_total_cost_usd, 6)} | "
            f"{_fmt_float(metrics.estimated_average_cost_usd, 6)} | "
            f"{_fmt_float(metrics.error_rate, 4)} | "
            f"{_fmt_float(metrics.schema_valid_rate, 4)} |"
        )

    return lines


def _delta_table_lines(
    before_by_route: dict[str, AggregateMetrics],
    after_by_route: dict[str, AggregateMetrics],
) -> list[str]:
    """Render a markdown delta table for before/after route comparison."""
    all_routes = sorted(set(before_by_route.keys()) | set(after_by_route.keys()))

    lines = [
        "| Route | Request Δ | P50 Δ (ms) | P95 Δ (ms)"
        " | Total Cost Δ (USD) | Avg Cost Δ (USD) | Error Rate Δ |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]

    for route in all_routes:
        before_metrics = before_by_route.get(route, aggregate_metrics([]))
        after_metrics = after_by_route.get(route, aggregate_metrics([]))
        delta = compare_aggregates(before_metrics, after_metrics)

        lines.append(
            "| "
            f"{route} | "
            f"{delta['request_count_delta']} | "
            f"{_fmt_float(delta['latency_p50_ms_delta'], 2)} | "
            f"{_fmt_float(delta['latency_p95_ms_delta'], 2)} | "
            f"{_fmt_float(delta['estimated_total_cost_usd_delta'], 6)} | "
            f"{_fmt_float(delta['estimated_average_cost_usd_delta'], 6)} | "
            f"{_fmt_float(delta['error_rate_delta'], 4)} |"
        )

    return lines


def _eval_summary_lines(
    eval_payloads: dict[str, dict[str, Any] | None],
) -> tuple[list[str], list[str]]:
    """Render eval summary lines and collect missing coverage labels."""
    lines: list[str] = []
    missing_coverage: list[str] = []

    for label, payload in eval_payloads.items():
        lines.append(f"### {label}")
        if payload is None:
            lines.append("Eval summary unavailable.")
            lines.append("")
            missing_coverage.append(label)
            continue

        total_cases = payload.get("total_cases", 0)
        passed = payload.get("passed", 0)
        failed = payload.get("failed", 0)
        results = payload.get("results", [])

        lines.append(f"- Total cases: {total_cases}")
        lines.append(f"- Passed: {passed}")
        lines.append(f"- Failed: {failed}")

        failing_ids = [
            result.get("case_id", "unknown")
            for result in results
            if isinstance(result, dict) and result.get("status") == "fail"
        ]
        if failing_ids:
            lines.append(f"- Failing cases: {', '.join(failing_ids)}")
        else:
            lines.append("- Failing cases: none")

        lines.append("")

    return lines, missing_coverage


def _pareto_lines(route_metrics: dict[str, AggregateMetrics]) -> list[str]:
    """Render Pareto-style ranked sections for cost and error burden."""
    lines: list[str] = []

    by_cost = sorted(
        route_metrics.items(),
        key=lambda item: item[1].estimated_total_cost_usd,
        reverse=True,
    )
    by_error = sorted(
        route_metrics.items(),
        key=lambda item: item[1].error_count,
        reverse=True,
    )

    lines.append("### Highest Cost Routes")
    for route, metrics in by_cost:
        lines.append(
            f"- `{route}` — total cost {_fmt_float(metrics.estimated_total_cost_usd, 6)} USD"
        )
    lines.append("")

    lines.append("### Highest Error Burden Routes")
    for route, metrics in by_error:
        lines.append(
            f"- `{route}` — error count {metrics.error_count},"
            f" error rate {_fmt_float(metrics.error_rate, 4)}"
        )
    lines.append("")

    return lines


def _build_recommendations(
    after_rows: list[NormalizedTelemetryRow],
    after_route_metrics: dict[str, AggregateMetrics],
    malformed_before_count: int,
    malformed_after_count: int,
    missing_eval_coverage: list[str],
    before_by_route: dict[str, AggregateMetrics] | None,
) -> list[str]:
    """Build rule-based recommendations grounded in current artifacts."""
    lines: list[str] = []

    if after_route_metrics:
        highest_cost_route = max(
            after_route_metrics.items(),
            key=lambda item: item[1].estimated_total_cost_usd,
        )[0]
        lines.append(
            f"- Prioritize `{highest_cost_route}` first,"
            " because it currently dominates observed cost."
        )

        highest_error_route = max(
            after_route_metrics.items(),
            key=lambda item: item[1].error_count,
        )[0]
        if after_route_metrics[highest_error_route].error_count > 0:
            lines.append(
                f"- Investigate `{highest_error_route}` first for failure reduction,"
                " because it currently has the highest observed error burden."
            )

    total_malformed = malformed_before_count + malformed_after_count
    if total_malformed > 0:
        lines.append(
            f"- Fix telemetry structure upstream. The report skipped"
            f" {total_malformed} malformed telemetry row(s),"
            " which weakens measurement quality."
        )

    error_rows = [row for row in after_rows if row.status == "error"]
    unknown_error_rows = [row for row in error_rows if row.error_type == "unknown"]
    if error_rows and (len(unknown_error_rows) / len(error_rows)) > 0.5:
        lines.append(
            "- Tighten gateway error taxonomy. `unknown` is currently the dominant"
            " failure type, which makes operational diagnosis weaker than it should be."
        )

    if missing_eval_coverage:
        lines.append(
            "- Regression coverage is incomplete. Missing eval summaries for: "
            + ", ".join(missing_eval_coverage)
            + "."
        )

    if before_by_route is not None and after_route_metrics:
        all_routes = sorted(set(before_by_route.keys()) | set(after_route_metrics.keys()))
        largest_cost_route: str | None = None
        largest_cost_delta = 0.0

        for route in all_routes:
            before_metrics = before_by_route.get(route, aggregate_metrics([]))
            after_metrics = after_route_metrics.get(route, aggregate_metrics([]))
            delta = compare_aggregates(before_metrics, after_metrics)
            absolute_delta = abs(delta["estimated_total_cost_usd_delta"])
            if absolute_delta > largest_cost_delta:
                largest_cost_delta = absolute_delta
                largest_cost_route = route

        if largest_cost_route is not None:
            lines.append(
                f"- Review `{largest_cost_route}` carefully in before/after analysis,"
                " because it shows the largest absolute cost movement."
            )

    if not lines:
        lines.append(
            "- No strong action signal was detected from current artifacts."
            " Collect more telemetry before making optimization decisions."
        )

    return lines


def render_markdown_report(
    *,
    before_log_path: str | None,
    after_log_path: str,
    before_rows: list[NormalizedTelemetryRow],
    after_rows: list[NormalizedTelemetryRow],
    malformed_before_count: int,
    malformed_after_count: int,
    before_by_route: dict[str, AggregateMetrics] | None,
    after_by_route: dict[str, AggregateMetrics],
    before_overall: AggregateMetrics | None,
    after_overall: AggregateMetrics,
    eval_payloads: dict[str, dict[str, Any] | None],
) -> str:
    """Render the final markdown report."""
    lines: list[str] = []

    lines.append("# LLM Cost Control Report")
    lines.append("")
    lines.append("## Run Context")
    lines.append(f"- Generated at: {utc_timestamp()}")
    lines.append(f"- After log: `{after_log_path}`")
    if before_log_path:
        lines.append(f"- Before log: `{before_log_path}`")
        lines.append("- Mode: before/after comparison")
    else:
        lines.append("- Mode: single-run summary")
    lines.append("")

    lines.append("## Executive Summary")
    if after_by_route:
        highest_cost_route = max(
            after_by_route.items(),
            key=lambda item: item[1].estimated_total_cost_usd,
        )[0]
        highest_error_route = max(
            after_by_route.items(),
            key=lambda item: item[1].error_count,
        )[0]
        lines.append(f"- Highest current cost route: `{highest_cost_route}`.")
        lines.append(f"- Highest current error-burden route: `{highest_error_route}`.")
    else:
        lines.append("- No valid telemetry rows were available for current-route analysis.")

    if before_by_route is not None and before_overall is not None:
        overall_delta = compare_aggregates(before_overall, after_overall)
        lines.append(
            f"- Overall latency p50 delta:"
            f" {_fmt_float(overall_delta['latency_p50_ms_delta'], 2)} ms."
        )
        lines.append(
            f"- Overall total cost delta:"
            f" {_fmt_float(overall_delta['estimated_total_cost_usd_delta'], 6)} USD."
        )
        lines.append(
            f"- Overall error rate delta: {_fmt_float(overall_delta['error_rate_delta'], 4)}."
        )
    else:
        lines.append("- No before snapshot provided; comparison deltas were not computed.")
    lines.append("")

    lines.append("## Telemetry Coverage Summary")
    lines.append(f"- Current valid rows: {len(after_rows)}")
    lines.append(f"- Current malformed rows skipped: {malformed_after_count}")
    lines.append(f"- Current routes observed: {len(after_by_route)}")
    lines.append(f"- Current successes: {sum(1 for row in after_rows if row.status == 'success')}")
    lines.append(f"- Current errors: {sum(1 for row in after_rows if row.status == 'error')}")
    if before_by_route is not None:
        lines.append(f"- Before valid rows: {len(before_rows)}")
        lines.append(f"- Before malformed rows skipped: {malformed_before_count}")
    lines.append("")

    lines.append("## Per-Route Aggregate Table")
    lines.extend(_route_table_lines(after_by_route))
    lines.append("")

    if before_by_route is not None:
        lines.append("## Before/After Comparison")
        lines.extend(_delta_table_lines(before_by_route, after_by_route))
        lines.append("")

    lines.append("## Eval Summary")
    eval_lines, missing_eval_coverage = _eval_summary_lines(eval_payloads)
    lines.extend(eval_lines)

    lines.append("## Pareto Analysis")
    lines.extend(_pareto_lines(after_by_route))

    lines.append("## Recommendations")
    recommendation_lines = _build_recommendations(
        after_rows=after_rows,
        after_route_metrics=after_by_route,
        malformed_before_count=malformed_before_count,
        malformed_after_count=malformed_after_count,
        missing_eval_coverage=missing_eval_coverage,
        before_by_route=before_by_route,
    )
    lines.extend(recommendation_lines)
    lines.append("")

    return "\n".join(lines)


def write_text_file(path: str, content: str) -> None:
    """Write a UTF-8 text file, creating parent directories if needed."""
    file_path = Path(path)
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_text(content, encoding="utf-8")


def main() -> int:
    """Generate the markdown report from explicit artifact paths."""
    args = parse_args()

    before_rows: list[NormalizedTelemetryRow] = []
    malformed_before_count = 0
    before_by_route: dict[str, AggregateMetrics] | None = None
    before_overall: AggregateMetrics | None = None

    if args.before_log:
        before_rows, malformed_before_count = load_jsonl_telemetry(args.before_log)
        before_by_route, before_overall = build_route_aggregates(before_rows)

    after_rows, malformed_after_count = load_jsonl_telemetry(args.after_log)
    after_by_route, after_overall = build_route_aggregates(after_rows)

    eval_payloads = {
        "Classify Eval": load_eval_result(args.classify_eval),
        "Answer Routed Eval": load_eval_result(args.answer_eval),
        "Conversation Turn Eval": load_eval_result(args.conversation_eval),
    }

    report_markdown = render_markdown_report(
        before_log_path=args.before_log,
        after_log_path=args.after_log,
        before_rows=before_rows,
        after_rows=after_rows,
        malformed_before_count=malformed_before_count,
        malformed_after_count=malformed_after_count,
        before_by_route=before_by_route,
        after_by_route=after_by_route,
        before_overall=before_overall,
        after_overall=after_overall,
        eval_payloads=eval_payloads,
    )

    write_text_file(args.output, report_markdown)
    print(f"Report written to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

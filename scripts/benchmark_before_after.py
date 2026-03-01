"""Before/after benchmark — capture two telemetry snapshots around a change.

NOT YET IMPLEMENTED — no spec currently assigned.

When implemented, this script will:
  - Copy the current artifacts/logs/telemetry.jsonl to before_telemetry.jsonl.
  - Run a load generation pass to populate a fresh telemetry.jsonl.
  - Invoke reporting/make_report.py with --before-log and --after-log to produce
    a before/after comparison report at artifacts/reports/report_before_after.md.

Usage (once implemented):
    python3 -m scripts.benchmark_before_after
"""

raise NotImplementedError("scripts.benchmark_before_after is not yet implemented")

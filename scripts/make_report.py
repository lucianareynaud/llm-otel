"""Report generation shortcut script.

NOT YET IMPLEMENTED — no spec currently assigned.

When implemented, this script will be a thin wrapper around
reporting/make_report.py that picks sensible default artifact paths so the
common case (single-run report from the current telemetry file) requires no
flags.

Usage (once implemented):
    python3 -m scripts.make_report
    # equivalent to:
    python3 -m reporting.make_report \
        --after-log artifacts/logs/telemetry.jsonl \
        --output artifacts/reports/report.md

Until then, call reporting.make_report directly:
    python3 -m reporting.make_report --after-log artifacts/logs/telemetry.jsonl \
        --output artifacts/reports/report.md
"""

raise NotImplementedError(
    "scripts.make_report is not yet implemented. "
    "Use: python3 -m reporting.make_report --after-log artifacts/logs/telemetry.jsonl "
    "--output artifacts/reports/report.md"
)

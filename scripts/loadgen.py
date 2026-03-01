"""Load generator — drive request volume against the running app to populate telemetry.

NOT YET IMPLEMENTED — no spec currently assigned.

When implemented, this script will:
  - Accept --url, --requests, --concurrency, and --output-log flags.
  - Send a configurable volume of requests to all three routes
    (/classify-complexity, /answer-routed, /conversation-turn).
  - Write a "before" JSONL snapshot to artifacts/logs/before_telemetry.jsonl
    before the run and leave the "after" state in artifacts/logs/telemetry.jsonl.
  - Report per-route throughput and error rate to stdout on completion.

Usage (once implemented):
    python3 -m scripts.loadgen --requests 50 --concurrency 5
"""

raise NotImplementedError("scripts.loadgen is not yet implemented")

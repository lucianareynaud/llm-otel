# Spec: 004 Reporting

## Goal
Generate a reproducible markdown report that compares before and after runs of the reference app.

The report exists to support engineering decisions.
It is not a vanity dashboard and it is not a BI artifact.

Its purpose is to make route-level cost, routing behavior, context usage, latency, and bounded improvements easy to inspect after a controlled benchmark or eval run.

## Reporting questions
The report must answer the following questions:

1. Which route costs the most?
2. Which route fails the most?
3. Which route is cheapest and most stable?
4. Which route benefited most from routing-based optimization?
5. Which context strategy reduced token usage the most?
6. Which change had the largest effect on cost, latency, or schema-valid rate?
7. What should be changed next?

## Required metrics
The report must include, per route and overall:

- request count
- latency p50
- latency p95
- estimated total cost
- estimated average cost
- total tokens_in
- total tokens_out
- error rate
- schema-valid rate

Additionally:
- selected model distribution for `/answer-routed`
- routing decision distribution for `/answer-routed`
- average `context_tokens_used` for `/conversation-turn`
- context strategy distribution for `/conversation-turn`
- cache hit rate when caching is enabled

## Input requirements
The reporting layer must accept:
- a before log path
- an after log path

The report must be generated from file-based artifacts only.
No notebook or manual spreadsheet step may be required.

## Output requirements
The reporting layer must produce:
- one markdown report
- one aggregate comparison table
- one Pareto-style section by route
- one routing behavior summary section
- one context usage summary section
- one recommendation section listing next engineering actions

The output must be readable in plain markdown without requiring a UI.

## Comparison rules
Before/after comparison must be reproducible.
The report must assume the same controlled workload was run in both cases.

If workload comparability is missing, the report must make that limitation explicit.

## Report structure
The markdown report must include these sections:

1. Summary
2. Route-by-route comparison
3. Aggregate metrics table
4. Pareto analysis by route
5. Routing behavior summary
6. Context usage summary
7. Change impact analysis
8. Recommended next steps
9. Limitations and assumptions

## CLI requirements
- Report generation must work from a CLI command.
- Inputs must be explicit file paths.
- Output path must be explicit or clearly defaulted.
- The command must be documented in the README.

## Acceptance criteria
This spec is complete only if all of the following are true:

1. Report generation works from CLI.
2. Before/after comparison is reproducible.
3. Report is readable without notebooks or dashboards.
4. Route-level trade-offs are obvious from the report.
5. Routing and context behavior are visible in the report.
6. The report can be regenerated from stored artifacts.
7. README explains the exact command to generate the report.

## Required files
At minimum, this spec must result in:
- `scripts/make_report.py`
- `scripts/benchmark_before_after.py`
- `artifacts/reports/`
- `tests/test_reporting.py` or reporting coverage added to existing tests
- README documentation for report generation

## Explicitly out of scope
- web dashboards
- real-time analytics
- BI integration
- notebook-only reporting
- fancy charting libraries
- interactive visualizations
- manual spreadsheet workflows

## Final constraint
If a reporting approach adds visual complexity but does not improve reproducibility, route-level clarity, or decision usefulness, reject it.

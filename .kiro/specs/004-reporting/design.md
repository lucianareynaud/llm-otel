# Design: 004 Reporting

## Purpose
This design describes a deterministic reporting layer that reads existing artifact files and generates one markdown report for operational analysis.

The reporting layer exists to answer practical engineering questions from already-collected data. It does not create telemetry, run evals, or call providers. It only reads artifact inputs and produces a human-readable markdown report.

The reporting layer focuses on:
- route-level cost visibility
- route-level latency visibility
- route-level failure visibility
- before/after comparison of engineering changes
- summary of eval outcomes
- concrete next-step recommendations grounded in current artifacts

It does not attempt dashboarding, tracing exploration, or external observability integration.

## Design Principles

### 1. Downstream-only design
Reporting is a downstream consumer of artifacts.

It must read only from existing files such as:
- `artifacts/logs/telemetry.jsonl`
- `artifacts/reports/classify_eval_results.json`
- `artifacts/reports/answer_routed_eval_results.json`
- `artifacts/reports/conversation_turn_eval_results.json`

It must not:
- call the gateway
- call OpenAI
- run routes
- regenerate evals
- depend on Langfuse
- depend on notebooks

### 2. Deterministic report generation
Given the same input files, the reporting script must produce the same aggregate values and the same markdown structure.

The report may include a timestamp, but metric calculations and ranking logic must remain deterministic.

### 3. File-based inspectability
All inputs and outputs remain file-based and readable without proprietary tooling.

The report must be plain markdown.
Intermediate aggregates may be written as JSON if needed, but the primary output is one markdown file.

### 4. Operational usefulness over visual polish
The report must answer concrete operational questions, not merely dump raw metrics.

At minimum, it must answer:
1. Which route costs the most?
2. Which route fails the most?
3. Which change affected cost or latency the most?
4. What should be changed next?

### 5. Small-scope implementation
The reporting layer must remain narrow:
- one report script
- one markdown output
- small helper functions only if necessary
- no dashboard UI
- no BI integration
- no web server
- no notebook workflow

## Input Design

### 1. Telemetry input
Primary telemetry source:
- `artifacts/logs/telemetry.jsonl`

Each line is one JSON event emitted by the gateway.

Required fields expected from telemetry:
- `timestamp`
- `request_id`
- `route`
- `provider`
- `model`
- `latency_ms`
- `status`
- `tokens_in`
- `tokens_out`
- `estimated_cost_usd`
- `cache_hit`
- `schema_valid`
- `error_type`

Additional metadata fields may be present and should be preserved if useful for summaries, but they are not required for core aggregates.

### 2. Eval result inputs
Optional but expected eval inputs:
- `artifacts/reports/classify_eval_results.json`
- `artifacts/reports/answer_routed_eval_results.json`
- `artifacts/reports/conversation_turn_eval_results.json`

Each eval file contributes:
- total cases
- passed count
- failed count
- per-case failures and reasons

If an eval file is missing, report generation must still work, but the report should explicitly state that the eval summary for that route was unavailable.

### 3. Before/after comparison inputs
The report script must support two telemetry inputs:
- `before_log_path`
- `after_log_path`

These may refer to:
- the same file pattern in different directories
- two snapshots of telemetry saved before and after a change

If only one log path is provided, the report must generate a single-run summary instead of a comparison report.

## Output Design

### Primary output
One markdown file:
- `artifacts/reports/report.md`

This report must be readable without opening notebooks or dashboards.

### Optional aggregate output
If useful, the script may also write:
- `artifacts/aggregates/report_summary.json`

This is optional and must remain secondary to the markdown report.

## Report Structure

The markdown report must contain the following sections in this order.

### 1. Title and run context
Include:
- report title
- generation timestamp
- input file paths used
- whether the report is single-run or before/after comparison

### 2. Executive summary
A short section with direct conclusions, for example:
- highest-cost route
- highest-error route
- whether latency improved or worsened
- whether eval pass rates changed
- one or two recommended next actions

This section must be concise and factual.

### 3. Telemetry coverage summary
Summarize:
- total request count
- number of routes observed
- number of success vs error events
- whether before and after inputs were both provided

### 4. Per-route aggregate table
For each route, include:
- request count
- latency p50
- latency p95
- estimated total cost
- estimated average cost
- error rate
- schema-valid rate

This table must appear for:
- single-run mode, or
- both before and after, depending on the invocation mode

### 5. Before/after comparison section
If both before and after logs are provided, compare per route:
- request count delta
- latency p50 delta
- latency p95 delta
- total cost delta
- average cost delta
- error rate delta

This section must explicitly highlight:
- the route with the largest cost change
- the route with the largest latency change
- whether failures improved or worsened

### 6. Eval summary section
For each route, summarize:
- eval cases total
- passed
- failed
- failing case IDs, if any

If eval files are missing, state that clearly instead of failing silently.

### 7. Pareto-style section
Rank routes by:
- estimated total cost
- error count

This section must make it obvious where engineering effort should go first.

### 8. Recommendation section
Provide a short recommendation section grounded only in the observed artifacts.

Examples:
- focus on `/conversation-turn` if it dominates cost
- improve error taxonomy if many failures are `unknown`
- collect more before/after telemetry if comparison inputs are too sparse

Recommendations must be rule-based, not speculative prose.

## Metrics and Aggregation Design

### Core metrics
Per route and overall, compute:
- `request_count`
- `latency_p50_ms`
- `latency_p95_ms`
- `estimated_total_cost_usd`
- `estimated_average_cost_usd`
- `error_rate`
- `schema_valid_rate`

### Definitions

**Request count**
- total number of telemetry events for the route

**Latency p50**
- 50th percentile of `latency_ms`

**Latency p95**
- 95th percentile of `latency_ms`

**Estimated total cost**
- sum of `estimated_cost_usd`

**Estimated average cost**
- total estimated cost divided by request count
- if request count is zero, use `0.0`

**Error rate**
- count of events where `status == "error"` divided by request count

**Schema-valid rate**
- count of events where `schema_valid == true` divided by request count

### Percentile rule
Use a deterministic percentile calculation method documented in code.
Do not depend on heavy numerical libraries if the standard library is sufficient.

### Missing-value handling
If fields are missing in a telemetry row:
- do not crash the whole report
- skip invalid row contributions where necessary
- count and report malformed rows in a small warning section

## Component Design

### 1. Report script
Recommended file:
- `reporting/make_report.py`

Responsibilities:
- parse CLI arguments
- load telemetry file(s)
- load eval result file(s)
- compute aggregates
- compute before/after deltas when applicable
- render markdown
- write final report file

### 2. Small helper module
Optional helper file:
- `reporting/metrics.py`

Allowed responsibilities:
- percentile calculation
- route grouping
- cost/error aggregation helpers

This helper must remain small and concrete.
Do not create a reporting framework.

### 3. Tests
Test file:
- `tests/test_reporting.py`

Responsibilities:
- test telemetry parsing
- test route aggregation
- test percentile calculation
- test before/after comparison logic
- test markdown report generation shape
- test missing eval file behavior
- test malformed telemetry row handling

## CLI Design

### Required CLI mode
The report script must support explicit input paths.

Examples:

Single-run summary:
```bash
python3 -m reporting.make_report \
  --after-log artifacts/logs/telemetry.jsonl \
  --output artifacts/reports/report.md
```

Before/after comparison:
```bash
python3 -m reporting.make_report \
  --before-log artifacts/logs/before_telemetry.jsonl \
  --after-log artifacts/logs/after_telemetry.jsonl \
  --output artifacts/reports/report.md
```

Optional eval paths:
```bash
python3 -m reporting.make_report \
  --after-log artifacts/logs/telemetry.jsonl \
  --classify-eval artifacts/reports/classify_eval_results.json \
  --answer-eval artifacts/reports/answer_routed_eval_results.json \
  --conversation-eval artifacts/reports/conversation_turn_eval_results.json \
  --output artifacts/reports/report.md
```

### CLI constraints
- all paths must be explicit
- no hidden defaults except reasonable output path fallback if documented
- no interactive prompts
- no notebook dependency

## File Structure

```text
reporting/
├── __init__.py
├── make_report.py
└── metrics.py          # optional, only if needed

artifacts/
├── logs/
│   └── telemetry.jsonl
├── reports/
│   ├── classify_eval_results.json
│   ├── answer_routed_eval_results.json
│   ├── conversation_turn_eval_results.json
│   └── report.md
└── aggregates/
    └── report_summary.json   # optional
```

## Testing Strategy

### Unit-level coverage
`tests/test_reporting.py` must verify:
- JSONL telemetry loading
- aggregation per route
- p50 and p95 calculations
- error rate calculation
- schema-valid rate calculation
- before/after delta calculation
- markdown section presence
- eval summary integration

### Fixture design
Use tiny local fixture files for:
- telemetry before
- telemetry after
- eval results

Fixtures must be deterministic and small.

### Excluded testing concerns
Do not test:
- dashboard rendering
- notebooks
- external telemetry systems
- live provider calls

## Acceptance Criteria Mapping

| Criterion | Design element |
|-----------|----------------|
| Report generation works from CLI | `reporting/make_report.py` with explicit path args |
| Before/after comparison is reproducible | deterministic aggregation and delta rules |
| Report is readable without notebooks | markdown-only output |
| Answers operational questions | fixed report sections and recommendation rules |
| Per-route and overall metrics exist | aggregate metric design |
| Pareto-style view exists | ranked cost and error sections |
| Eval results are incorporated | eval summary section |
| No Langfuse or dashboard dependency | downstream-only design |

## Explicit Non-Goals

This design explicitly excludes:
- Langfuse integration
- dashboard UI
- real-time analytics
- notebook-based analysis
- BI tooling
- provider calls
- re-running evals
- route execution from reporting
- generalized analytics platform design

## Final Design Rule
If a proposed reporting feature improves visual sophistication but does not improve:
- determinism,
- inspectability,
- operational clarity,
- before/after comparability, or
- report usefulness,

it does not belong in the MVP.

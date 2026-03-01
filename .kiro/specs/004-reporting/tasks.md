# Tasks: 004 Reporting

## Implementation order
Tasks must be executed in the order listed to preserve deterministic behavior, inspectable artifacts, and bounded scope.

## Task list

### 1. Create reporting package skeleton
Create the minimal reporting package structure.

- [x] 1.1 Create `reporting/__init__.py`
  - Keep file empty or minimal

- [x] 1.2 Create `reporting/make_report.py`
  - This will be the CLI entry point for report generation

- [x] 1.3 Optionally create `reporting/metrics.py`
  - Only if needed for small aggregation helpers
  - Do not create a framework or analytics layer

**Acceptance**: Reporting package exists and contains the minimal files needed for implementation.

---

### 2. Implement telemetry loading
Create deterministic loading for telemetry JSONL inputs.

- [x] 2.1 In `reporting/make_report.py`, implement telemetry loading
  - Load JSONL from explicit file path
  - Parse one JSON object per line
  - Ignore empty lines
  - Handle malformed rows without crashing the whole report
  - Track malformed row count for later reporting
  - Keep implementation simple and explicit

**Acceptance**: Telemetry loader returns parsed event rows and malformed-row count from a JSONL file.

---

### 3. Implement eval result loading
Create deterministic loading for eval result JSON files.

- [x] 3.1 In `reporting/make_report.py`, implement eval result loading
  - Load JSON from explicit file path
  - Support missing eval files gracefully
  - Return `None` or equivalent when file is absent
  - Do not crash report generation if eval files are unavailable

**Acceptance**: Eval loader can read existing eval JSON files and handle missing files gracefully.

---

### 4. Implement route-level aggregation
Create deterministic route-level metrics from telemetry rows.

- [x] 4.1 In `reporting/make_report.py` or `reporting/metrics.py`, implement grouping by route
  - Group telemetry rows by `route`

- [x] 4.2 Implement aggregate calculations per route
  - `request_count`
  - `latency_p50_ms`
  - `latency_p95_ms`
  - `estimated_total_cost_usd`
  - `estimated_average_cost_usd`
  - `error_rate`
  - `schema_valid_rate`

- [x] 4.3 Implement overall metrics
  - Same metrics at overall level across all routes

**Acceptance**: Report code can compute route-level and overall aggregates deterministically from telemetry rows.

---

### 5. Implement percentile calculation
Implement deterministic latency percentile helpers.

- [x] 5.1 Add percentile helper
  - Support p50 and p95
  - Keep implementation small and explicit
  - Do not add heavy numerical dependencies
  - Document percentile method in code comments or docstring

**Acceptance**: p50 and p95 are computed deterministically and consistently for test inputs.

---

### 6. Implement before/after comparison
Add deterministic comparison logic for two telemetry snapshots.

- [x] 6.1 Implement before/after comparison in `reporting/make_report.py`
  - Accept:
    - `before_log_path`
    - `after_log_path`
  - Support single-run mode when only after-log is provided
  - For before/after mode, compute per-route deltas for:
    - request count
    - latency p50
    - latency p95
    - estimated total cost
    - estimated average cost
    - error rate

- [x] 6.2 Add ranked summaries
  - Identify route with largest cost change
  - Identify route with largest latency change
  - Identify route with largest error burden in current snapshot

**Acceptance**: Report code can generate either single-run summaries or before/after comparisons from explicit paths.

---

### 7. Implement markdown rendering
Generate one inspectable markdown report.

- [x] 7.1 In `reporting/make_report.py`, implement markdown rendering
  - Include sections in this order:
    1. Title and run context
    2. Executive summary
    3. Telemetry coverage summary
    4. Per-route aggregate table
    5. Before/after comparison section (only if both logs provided)
    6. Eval summary section
    7. Pareto-style section
    8. Recommendation section

- [x] 7.2 Make recommendations rule-based
  - Recommendations must be grounded in observed artifacts
  - Do not generate speculative prose
  - Examples:
    - highest-cost route should be investigated first
    - many `unknown` errors indicate error taxonomy should improve
    - missing eval files should be called out clearly

**Acceptance**: Markdown report is readable, deterministic, and answers the operational questions from the spec.

---

### 8. Implement report writing
Write the final report artifact to disk.

- [x] 8.1 Write markdown report to output path
  - Default target should be explicit through CLI argument
  - Expected typical path:
    - `artifacts/reports/report.md`
  - Ensure parent directories are created if missing

- [x] 8.2 Optionally write aggregate JSON summary
  - Only if useful and trivial to support
  - Expected path:
    - `artifacts/aggregates/report_summary.json`
  - Keep this optional and secondary

**Acceptance**: Report generation produces a markdown file at the requested output path.

---

### 9. Implement CLI entry point
Create an explicit CLI for report generation.

- [x] 9.1 In `reporting/make_report.py`, implement CLI argument parsing
  - Support:
    - `--before-log`
    - `--after-log`
    - `--classify-eval`
    - `--answer-eval`
    - `--conversation-eval`
    - `--output`
  - Require explicit paths
  - No interactive prompts
  - No hidden notebook workflow

- [x] 9.2 Support two modes
  - Single-run mode:
    - only `--after-log`
  - Before/after mode:
    - both `--before-log` and `--after-log`

**Acceptance**: Report can be generated from CLI using explicit file paths.

---

### 10. Create reporting tests
Create tests for the reporting layer.

- [x] 10.1 Update or create `tests/test_reporting.py`
  - Test telemetry JSONL loading
  - Test malformed-row handling
  - Test eval result loading
  - Test route aggregation
  - Test p50 and p95 calculations
  - Test error rate calculation
  - Test schema-valid rate calculation
  - Test before/after delta logic
  - Test markdown report contains required sections
  - Test missing eval file behavior
  - Use only tiny deterministic fixture files or temporary files

**Acceptance**: Reporting tests pass locally and verify bounded reporting behavior.

---

### 11. Update README with reporting usage
Document how to run the reporting layer.

- [x] 11.1 Update `README.md`
  - Add section: `Reporting`
  - Document example commands for:
    - single-run mode
    - before/after mode
  - Use `python3 -m reporting.make_report`
  - Mention expected output path:
    - `artifacts/reports/report.md`
  - Keep documentation exact and minimal

**Acceptance**: README includes exact report-generation commands and output location.

---

### 12. Verify acceptance criteria
Verify the 004 spec acceptance criteria against the implementation.

- [x] 12.1 Verify CLI report generation works
  - Run with explicit input paths
  - Confirm markdown file is written

- [x] 12.2 Verify single-run mode
  - Run with only `--after-log`
  - Confirm report contains route summary and eval summary

- [x] 12.3 Verify before/after mode
  - Run with `--before-log` and `--after-log`
  - Confirm report contains delta section

- [x] 12.4 Verify operational readability
  - Confirm report answers:
    - which route costs the most
    - which route fails the most
    - which change affected cost or latency the most
    - what should be changed next

- [x] 12.5 Verify no external observability dependency
  - Confirm no Langfuse dependency
  - Confirm no dashboard UI
  - Confirm no notebook requirement

- [x] 12.6 Verify inspectability
  - Confirm markdown is readable directly
  - Confirm artifact paths are local and explicit

**Acceptance**: All 004 acceptance criteria are explicitly verified and documented.

---

## Task completion criteria
A task is complete only when:
- the code exists
- the code runs
- tests pass or are updated explicitly
- markdown report is written successfully
- report content is inspectable locally
- no external observability dependency was introduced
- no speculative analytics framework was added

## Notes
- Keep reporting downstream-only
- Do not add Langfuse in the MVP
- Do not add dashboards, notebooks, or BI tooling
- Prefer explicit file-based logic over abstraction
- The markdown report is the primary product of 004

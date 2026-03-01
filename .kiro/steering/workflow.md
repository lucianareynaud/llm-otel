# Workflow Steering

## Core workflow rule
Work one spec at a time. Never implement, design, or generate tasks for a future spec while
the current spec is in progress. The existence of specs 006–013 in the repository does not
authorize work on them until their prerequisite gate is green.

## Spec lifecycle
Every spec must pass through these stages in order:
```
1. prerequisite gate   → run test suite from prior spec; must be fully green
2. implementation      → execute tasks in the spec's tasks.md, in order
3. tests               → write or update tests before marking tasks complete
4. verification        → run full test suite + ruff + mypy; must all pass
5. commit              → commit with a descriptive message
```

Skip no stage. A task is not done until the verification stage passes.

## The prerequisite gate (critical)
Before starting any task in a spec, run:
```bash
OTEL_SDK_DISABLED=true pytest tests/ -v
```
The gate is defined at the top of every `tasks.md`. If any test fails, fix the failure before
touching any file in the current spec.

**The gate exists to prevent compounding failures.** If spec N has a broken test and you
start spec N+1, you will not know whether new failures come from N or N+1.

## Sequential spec order

The production-readiness specs must be completed in this exact order:

| Spec | Name | Gate (passing tests before start) |
|------|------|------------------------------------|
| 005  | Real model identifiers and pricing | 135 |
| 006  | Health endpoints and CI/CD | 135 |
| 007  | Authentication and rate limiting | 138 |
| 008  | Async-safe gateway retry | 147 |
| 009  | Accurate token counting | 147 |
| 010  | Semantic cache | 151 |
| 011  | Circuit breaker | 159 |
| 012  | Conversation persistence | 167 |
| 013  | Embedding-based routing | 176 |

If you are unsure which spec is current, run `pytest tests/ -v` and count passing tests.
Match the count to the table above to determine where you are in the sequence.

## Task execution rules

1. **Read the tasks.md for the current spec before writing any code.**
2. **Execute tasks in the order listed.** Tasks within a spec are sequenced deliberately —
   later tasks depend on earlier ones.
3. **Run the acceptance check at the end of each task before moving to the next.**
   Each task in `tasks.md` ends with an `**Acceptance**:` line — satisfy it before proceeding.
4. **Do not combine multiple spec tasks into a single implementation sweep.**
   Each task must be individually verifiable.

## Files to read at the start of any spec

Always read these three files before writing any code for a spec:
- `.kiro/specs/NNN-name/spec.md` — scope, acceptance criteria, what is frozen
- `.kiro/specs/NNN-name/design.md` — technical blueprint
- `.kiro/specs/NNN-name/tasks.md` — ordered task list with acceptance checks

Also read the relevant existing source files before editing them (never edit blind).

## What is frozen throughout specs 005–013

These must not change regardless of what a task asks you to do:
- The three route paths and their Pydantic schemas
- `gateway/telemetry.py` JSONL field names and types (adding optional fields is allowed)
- `reporting/make_report.py` and the artifact format it reads
- The `evals/` harness structure, datasets, and runner interfaces
- `gateway/otel_setup.py` setup/shutdown pattern
- The `RoutePolicy` frozen dataclass structure

## Commit message rules

Commit messages must identify:
1. Which spec the commit belongs to
2. Which files were changed
3. What acceptance criteria were satisfied

Example:
```
spec-007: add APIKeyMiddleware and RateLimitMiddleware

- app/middleware/auth.py: X-API-Key validation, /healthz /readyz exempt
- app/middleware/rate_limit.py: per-key deque sliding window, RATE_LIMIT_RPM env var
- app/main.py: register both middlewares (auth outermost), APP_API_KEY startup validation
- tests/test_auth.py: 5 tests covering valid key, missing, wrong, health bypass
- tests/test_rate_limit.py: 4 tests covering limits and per-key isolation
- tests/test_routes.py: added X-API-Key header to all existing fixtures

All 192 tests pass (hardening baseline). ruff, ruff format, and mypy clean.
```

## CI requirements

Every commit that modifies source files must pass locally before pushing:
```bash
ruff check .
ruff format --check .
mypy app/ gateway/ evals/ reporting/ --ignore-missing-imports
OTEL_SDK_DISABLED=true pytest tests/ -v
```

The CI workflow (`.github/workflows/ci.yml`) enforces these same checks. A red CI run
means the prerequisite gate for the next spec is not met.

## When a task introduces a regression

If a task causes a previously passing test to fail:
1. **Stop immediately.** Do not proceed to the next task.
2. Identify whether the failure is in a test that tests the new code or in a pre-existing test.
3. If a pre-existing test breaks, revert the relevant change and redesign the approach so the
   existing test continues to pass.
4. Tests are the truth. Code changes to satisfy a spec must not break prior tests.

The only exception: a spec task explicitly says "update this test to use the new values"
(e.g., updating `gpt-5-mini` → `gpt-4o-mini` in assertions). In that case, updating the test
is part of the task — the intent is that the new value is correct, not that the test is wrong.

## Change control

Before making any change not explicitly listed in the current spec's tasks.md:
- Stop and ask: does this change have a current acceptance criterion in the current spec?
- If yes, proceed.
- If no, record it as a future improvement and do not implement it now.

Do not make "while I'm here" changes. Scope discipline is more valuable than opportunistic
cleanup when working across a 9-spec sequence where each spec's gate depends on the prior spec.

## Definition of done for a task
A task is complete only when:
1. All sub-task checkboxes in `tasks.md` are satisfied
2. The task's `**Acceptance**` check passes
3. `OTEL_SDK_DISABLED=true pytest tests/ -v` passes (all tests, not just new ones)
4. `ruff check .` exits zero
5. `ruff format --check .` exits zero
6. `mypy app/ gateway/ evals/ reporting/ --ignore-missing-imports` exits zero

## Definition of done for a spec
A spec is complete only when:
1. All tasks are done (per the task definition above)
2. Test count has reached the expected value in the spec's completion criteria
3. No reference to forbidden patterns (e.g., fictional model names, synchronous sleep in
   async context) remains in modified files
4. A commit has been created with a descriptive message

## Definition of done for the full production-readiness sequence
All of specs 007–013 are complete and:
1. `OTEL_SDK_DISABLED=true pytest tests/ -v` reports ≥ 236 tests, all passing
2. `ruff check .` exits zero
3. `ruff format --check .` exits zero
4. `mypy app/ gateway/ evals/ reporting/ --ignore-missing-imports` exits zero
5. With `OPENAI_API_KEY` and `APP_API_KEY` set, the app starts and serves real requests
6. `GET /healthz` returns 200 without authentication
7. CI workflow passes on a clean push

## Final rule
Move only when the current spec is demonstrably complete.
Do not trade completion for motion.
Do not trade scope discipline for perceived speed.

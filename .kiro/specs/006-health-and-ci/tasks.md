# Tasks: 006 Health Endpoints and CI/CD Pipeline

## Prerequisite gate
Run before starting any task:

```bash
OTEL_SDK_DISABLED=true pytest tests/ -v
grep -r "gpt-5" .
```

- All tests must be green.
- `grep` must return zero matches.

If either fails, complete spec 005 first.

---

## Task 1 — Create health router

- [x] 1.1 Create `app/routes/health.py`
  - Module-level `_ready: bool = False`
  - `set_ready(value: bool) -> None` — sets the module-level flag
  - `router = APIRouter()`
  - `GET /healthz` → always returns `{"status": "ok"}` with HTTP 200
  - `GET /readyz` → returns `{"status": "ready"}` / HTTP 200 when `_ready` is True;
    `{"status": "not_ready"}` / HTTP 503 when False
  - No gateway import, no OTel import, no database access

- [x] 1.2 Verify the file compiles: `python -c "from app.routes.health import router"`

**Acceptance**: Module imports without errors. Both endpoints are defined.

---

## Task 2 — Register health router and update lifespan

- [x] 2.1 Open `app/main.py`
- [x] 2.2 Import: `from app.routes import health` and `from app.routes.health import set_ready`
- [x] 2.3 Register the health router — no tags:
  ```python
  app.include_router(health.router)
  ```
- [x] 2.4 In the lifespan handler, add `set_ready(True)` immediately after `setup_otel()` completes
- [x] 2.5 In the lifespan shutdown section, add `set_ready(False)` as the first line before `shutdown_otel()`
- [x] 2.6 Update `FastAPIInstrumentor.instrument_app()` call to exclude health paths:
  ```python
  FastAPIInstrumentor.instrument_app(application, excluded_urls="healthz,readyz")
  ```

**Acceptance**: App starts without errors. `GET /healthz` returns 200 without the `X-API-Key`
header (auth spec not yet added — this is a forward reference, but the endpoint must not require
auth now either).

---

## Task 3 — Write health endpoint tests

- [x] 3.1 Add tests to `tests/test_routes.py` (or create `tests/test_health.py`):
  - `test_healthz_always_200`: GET `/healthz` → HTTP 200, body `{"status": "ok"}`
  - `test_readyz_when_ready`: set `_ready = True` via monkeypatch, GET `/readyz` → HTTP 200,
    body `{"status": "ready"}`
  - `test_readyz_when_not_ready`: set `_ready = False` via monkeypatch, GET `/readyz` → HTTP 503,
    body `{"status": "not_ready"}`
- [x] 3.2 Import `set_ready` in the test file and use monkeypatch to control the flag — do not
  start a real lifespan
- [x] 3.3 Run: `OTEL_SDK_DISABLED=true pytest tests/ -v` — must pass with 138+ tests

**Acceptance**: Three new tests pass. Total test count ≥ 138.

---

## Task 4 — Create pyproject.toml with ruff and mypy config

- [x] 4.1 Create `pyproject.toml` at the repo root (if it does not already exist)
- [x] 4.2 Add ruff configuration:
  ```toml
  [tool.ruff]
  line-length = 100
  select = ["E", "F", "I", "UP"]
  exclude = [".venv", ".git", "__pycache__", "artifacts"]
  ```
- [x] 4.3 Add mypy configuration:
  ```toml
  [tool.mypy]
  python_version = "3.11"
  ignore_missing_imports = true
  warn_return_any = true
  warn_unused_ignores = true
  ```
- [x] 4.4 Run locally to baseline:
  - `ruff check .` — note any existing errors (do not fix pre-existing errors from other files
    in this spec; only fix errors introduced by files created in this spec)
  - `mypy app/routes/health.py gateway/` — must pass for the new file

**Acceptance**: `ruff check app/routes/health.py` and `mypy app/routes/health.py` pass with zero errors.

---

## Task 5 — Implement ci.yml

- [x] 5.1 Open `.github/workflows/ci.yml` (currently empty)
- [x] 5.2 Write the workflow:
  ```yaml
  name: CI

  on:
    pull_request:
    push:
      branches: [main]

  jobs:
    test:
      runs-on: ubuntu-latest
      steps:
        - uses: actions/checkout@v4
        - uses: actions/setup-python@v5
          with:
            python-version: "3.11"
        - run: pip install -r requirements.txt
        - run: ruff check . --output-format=github
        - run: mypy app/ gateway/ --ignore-missing-imports
        - run: OTEL_SDK_DISABLED=true pytest tests/ -v --tb=short --junitxml=results.xml
          env:
            OTEL_SDK_DISABLED: "true"
        - uses: actions/upload-artifact@v4
          if: always()
          with:
            name: test-results
            path: results.xml
  ```
- [x] 5.3 Confirm: no `OPENAI_API_KEY` secret is referenced anywhere in this workflow

**Acceptance**: `ci.yml` is non-empty, syntactically valid YAML, and contains no secrets requirements.

---

## Task 6 — Implement regression.yml

- [x] 6.1 Open `.github/workflows/regression.yml` (currently empty)
- [x] 6.2 Write the workflow:
  ```yaml
  name: Regression

  on:
    push:
      branches: [main]

  jobs:
    regression:
      runs-on: ubuntu-latest
      steps:
        - uses: actions/checkout@v4
        - uses: actions/setup-python@v5
          with:
            python-version: "3.11"
        - run: pip install -r requirements.txt
        - run: python -m evals.runners.run_classify_eval
          env:
            OTEL_SDK_DISABLED: "true"
        - run: python -m evals.runners.run_answer_routed_eval
          env:
            OTEL_SDK_DISABLED: "true"
        - run: python -m evals.runners.run_conversation_turn_eval
          env:
            OTEL_SDK_DISABLED: "true"
        - run: |
            python - <<'EOF'
            import json, glob, sys
            failures = 0
            for path in glob.glob("artifacts/reports/*_eval_results.json"):
                data = json.load(open(path))
                failures += data.get("failed", 0)
            if failures > 0:
                print(f"Regression: {failures} eval failure(s) detected")
                sys.exit(1)
            print("All evals passed")
            EOF
        - uses: actions/upload-artifact@v4
          if: always()
          with:
            name: eval-results
            path: artifacts/reports/
  ```
- [x] 6.3 Confirm: no `OPENAI_API_KEY` secret referenced. Eval runners mock the gateway.

**Acceptance**: `regression.yml` is non-empty, syntactically valid YAML, triggers only on push
to main, and exits 1 when any eval runner reports `failed > 0`.

---

## Task 7 — Final verification

- [x] 7.1 `OTEL_SDK_DISABLED=true pytest tests/ -v` — all 138+ tests pass
- [x] 7.2 `ruff check app/routes/health.py` — zero errors
- [x] 7.3 `mypy app/routes/health.py` — zero errors
- [x] 7.4 `python -c "import yaml; yaml.safe_load(open('.github/workflows/ci.yml'))"` — valid YAML
- [x] 7.5 `python -c "import yaml; yaml.safe_load(open('.github/workflows/regression.yml'))"` — valid YAML
- [x] 7.6 Manual: start the app and confirm both endpoints respond correctly without auth

**Acceptance**: All tests pass. YAML workflows are syntactically valid. Health endpoints
return correct status codes. No secrets required in CI.

---

## Completion criteria
This spec is complete when:
- `GET /healthz` returns HTTP 200 unconditionally
- `GET /readyz` returns 503 before lifespan completes and 200 after
- Both CI workflow files are non-empty and syntactically valid YAML
- `OTEL_SDK_DISABLED=true pytest tests/ -v` reports ≥ 192 tests, all passing
- No modifications were made to any file outside the list in spec.md

# Design: 006 Health Endpoints and CI/CD Pipeline

---

## Part A — Health endpoints

### Readiness flag

A module-level boolean `_ready: bool = False` lives in `app/routes/health.py`.
It is set by a public function `set_ready(value: bool) -> None` called from the lifespan handler
in `app/main.py`. This is the only global state introduced by this spec.

```python
# app/routes/health.py
_ready: bool = False

def set_ready(value: bool) -> None:
    global _ready
    _ready = value
```

### /healthz — liveness probe

```python
@router.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}
```

Always returns HTTP 200. FastAPI will never call this during shutdown, so it is inherently
safe to keep it unconditional. If the process is alive enough to handle the request, the
liveness probe should pass.

### /readyz — readiness probe

```python
@router.get("/readyz")
def readyz() -> JSONResponse:
    if _ready:
        return JSONResponse({"status": "ready"}, status_code=200)
    return JSONResponse({"status": "not_ready"}, status_code=503)
```

### Lifespan integration in app/main.py

```python
@asynccontextmanager
async def lifespan(application: FastAPI):
    setup_otel()
    FastAPIInstrumentor.instrument_app(application)
    set_ready(True)          # readyz → 200 from this point
    yield
    set_ready(False)         # readyz → 503 during graceful shutdown
    shutdown_otel()
    FastAPIInstrumentor.uninstrument_app(application)
```

### Router registration

The health router is registered without tags — these are not business routes and must not
appear in the business API surface of the OpenAPI docs.

```python
app.include_router(health.router)   # no tags=
```

### OTel exclusion

Health endpoints must be excluded from FastAPI instrumentation spans to avoid polluting
distributed traces with probe noise. Pass `excluded_urls` to the instrumentor:

```python
FastAPIInstrumentor.instrument_app(
    application,
    excluded_urls="healthz,readyz",
)
```

---

## Part B — CI/CD pipeline

### ci.yml — quality gate on every PR and push to main

Pipeline steps (in order, each blocks the next on failure):

1. **ruff check** — Python linter. Zero tolerance. `--output-format=github` produces inline
   annotations on the PR diff.
2. **mypy** — Type checker. Run on `app/` and `gateway/` only (not `evals/` — legacy code).
   `--ignore-missing-imports` prevents failures on untyped third-party stubs.
3. **pytest** — Full test suite with `OTEL_SDK_DISABLED=true`. JUnit XML output is uploaded
   as a CI artifact so test results are visible on the GitHub Actions summary page.

Python version: `3.11`. Dependencies installed with `pip install -r requirements.txt`.

### regression.yml — eval regression on push to main

Runs only on `push` to `main`, after `ci.yml` passes. Executes the three eval runners sequentially:

```bash
OTEL_SDK_DISABLED=true python -m evals.runners.run_classify_eval
OTEL_SDK_DISABLED=true python -m evals.runners.run_answer_routed_eval
OTEL_SDK_DISABLED=true python -m evals.runners.run_conversation_turn_eval
```

After all three complete, a small inline Python script reads each
`artifacts/reports/*_eval_results.json` and exits 1 if `failed > 0`. This makes the workflow
red on any eval regression.

All three eval runners mock the OpenAI boundary — no `OPENAI_API_KEY` secret required.

### pyproject.toml — linter and type checker configuration

Ruff:
```toml
[tool.ruff]
line-length = 100
select = ["E", "F", "I", "UP"]
exclude = [".venv", ".git", "__pycache__", "artifacts"]
```

Mypy:
```toml
[tool.mypy]
python_version = "3.11"
ignore_missing_imports = true
warn_return_any = true
warn_unused_ignores = true
```

`strict = false` — the project has pre-existing untyped areas; `--strict` would produce false
noise. The gate tightens incrementally as later specs add typed new modules.

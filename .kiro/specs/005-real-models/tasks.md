# Tasks: 005 Real Model Identifiers and Pricing

## Prerequisite gate
Run before starting any task:

```bash
OTEL_SDK_DISABLED=true pytest tests/ -v
```

All tests must be green. If any fail, fix them first — do not proceed with this spec while
the prior baseline is broken.

---

## Task 1 — Update cost_model.py

- [x] 1.1 Open `gateway/cost_model.py`
- [x] 1.2 Replace `"gpt-5-mini"` key with `"gpt-4o-mini"`
- [x] 1.3 Replace `"gpt-5.2"` key with `"gpt-4o"`
- [x] 1.4 Set pricing:
  - `gpt-4o-mini`: `input_per_1m: 0.15`, `output_per_1m: 0.60`
  - `gpt-4o`: `input_per_1m: 2.50`, `output_per_1m: 10.00`
- [x] 1.5 Add a comment above `MODEL_PRICING`:
  ```python
  # Source: https://platform.openai.com/docs/models — retrieved YYYY-MM-DD
  ```
  Replace `YYYY-MM-DD` with today's date.
- [x] 1.6 Update any docstring or inline comment that references the old names

**Acceptance**: `grep "gpt-5" gateway/cost_model.py` returns zero matches.

---

## Task 2 — Update policies.py

- [x] 2.1 Open `gateway/policies.py`
- [x] 2.2 In the `/answer-routed` policy, replace `"gpt-5-mini"` → `"gpt-4o-mini"` and `"gpt-5.2"` → `"gpt-4o"`
- [x] 2.3 In the `/conversation-turn` policy, apply the same replacements
- [x] 2.4 Verify no other occurrences of `gpt-5` exist in the file

**Acceptance**: `grep "gpt-5" gateway/policies.py` returns zero matches.

---

## Task 3 — Update test assertions

- [x] 3.1 Open `tests/test_gateway.py`
  - Replace every `"gpt-5-mini"` string with `"gpt-4o-mini"`
  - Replace every `"gpt-5.2"` string with `"gpt-4o"`
- [x] 3.2 Open `tests/test_routes.py`
  - Replace every `selected_model="gpt-5-mini"` with `selected_model="gpt-4o-mini"`
  - Replace every `selected_model="gpt-5.2"` with `selected_model="gpt-4o"`

**Acceptance**: `grep -r "gpt-5" tests/` returns zero matches.

---

## Task 4 — Verify

- [x] 4.1 Run full repository scan: `grep -r "gpt-5" .` — must return zero matches
- [x] 4.2 Run test suite:
  ```bash
  OTEL_SDK_DISABLED=true pytest tests/ -v
  ```
  All tests pass. Zero failures.
- [ ] 4.3 Manual smoke test (requires `OPENAI_API_KEY`):
  ```bash
  uvicorn app.main:app --reload &
  curl -s -X POST http://localhost:8000/classify-complexity \
    -H "Content-Type: application/json" \
    -d '{"message": "What is 2+2?"}'
  ```
  Returns HTTP 200. This confirms the app starts with real model names.

**Acceptance**: Zero `gpt-5` references anywhere. All tests pass. App starts cleanly.

---

## Completion criteria
This spec is complete when:
- `grep -r "gpt-5" .` returns zero matches in all source files
- `OTEL_SDK_DISABLED=true pytest tests/ -v` passes with no failures
- The pricing dict has a source comment with a retrieval date
- No other files were modified beyond the four listed in the spec

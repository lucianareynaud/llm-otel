# Tasks: 009 Accurate Token Counting with tiktoken

## Prerequisite gate
Run before starting any task:

```bash
OTEL_SDK_DISABLED=true pytest tests/ -v  # ≥ 147 tests, all passing
grep "async def call_llm" gateway/client.py  # must match
```

Both must pass before proceeding.

---

## Task 1 — Add tiktoken to requirements.txt

- [ ] 1.1 Run `pip install tiktoken` and note the installed version
- [ ] 1.2 Add `tiktoken==<version>` to `requirements.txt`
- [ ] 1.3 Verify: `python -c "import tiktoken; print(tiktoken.__version__)"` — prints a version

**Acceptance**: `tiktoken` imports without error.

---

## Task 2 — Create app/services/token_counter.py

- [ ] 2.1 Create `app/services/token_counter.py`
- [ ] 2.2 Implement `ContextTooLargeError(ValueError)`:
  - Constructor: `__init__(self, actual_tokens: int, max_tokens: int)`
  - Sets `self.actual_tokens` and `self.max_tokens`
  - Calls `super().__init__(f"Context too large: {actual_tokens} tokens exceeds limit of {max_tokens}")`
- [ ] 2.3 Implement `_get_encoding(model: str) -> tiktoken.Encoding` decorated with `@functools.lru_cache(maxsize=16)`:
  - `try: return tiktoken.encoding_for_model(model)`
  - `except KeyError: return tiktoken.get_encoding("cl100k_base")`
- [ ] 2.4 Implement `count_tokens(text: str, model: str = "gpt-4o") -> int`:
  - Returns `len(_get_encoding(model).encode(text))`
  - Include a docstring explaining BPE encoding and the cl100k_base fallback
- [ ] 2.5 `ruff check app/services/token_counter.py` — zero errors
- [ ] 2.6 `mypy app/services/token_counter.py --ignore-missing-imports` — zero errors

**Acceptance**: `from app.services.token_counter import count_tokens, ContextTooLargeError` works.

---

## Task 3 — Create tests/test_token_counter.py

- [ ] 3.1 Create `tests/test_token_counter.py`
- [ ] 3.2 Write:
  - `test_known_string_exact_count`:
    - Run `count_tokens("Hello world", "gpt-4o")` manually first; note the exact integer
    - Hard-code that integer as the expected value with a comment: `# "Hello world" → N tokens`
    - Assert the function returns that integer
  - `test_empty_string_returns_zero`:
    - `assert count_tokens("", "gpt-4o") == 0`
  - `test_unknown_model_falls_back`:
    - `count_tokens("test", "nonexistent-model-xyz-999")` must not raise; must return an integer > 0
  - `test_encoder_cached`:
    - Call `count_tokens("a", "gpt-4o")` twice
    - Call `_get_encoding.cache_info()` — `hits` must be ≥ 1 after the second call
- [ ] 3.3 Run: `OTEL_SDK_DISABLED=true pytest tests/test_token_counter.py -v` — all 4 tests pass

**Acceptance**: All 4 tests pass. Exact token count is hard-coded, not computed at test time.

---

## Task 4 — Update app/services/context_manager.py

- [ ] 4.1 Open `app/services/context_manager.py`
- [ ] 4.2 Remove `CHARS_PER_TOKEN = 4` constant
- [ ] 4.3 Remove the `_estimate_tokens()` function entirely — delete all lines
- [ ] 4.4 Add import: `from app.services.token_counter import count_tokens, ContextTooLargeError`
- [ ] 4.5 Add `import os` if not already present
- [ ] 4.6 Replace every call to `_estimate_tokens(text)` with `count_tokens(text, model)`
  - Add `model: str = "gpt-4o"` parameter to `prepare_context()` and to any private helper
    that calls `count_tokens`
- [ ] 4.7 At the end of `prepare_context()`, after building the final context string, add the guard:
  ```python
  max_ctx = int(os.environ.get("MAX_CONTEXT_TOKENS", "8192"))
  total_tokens = count_tokens(context, model)
  if total_tokens > max_ctx:
      raise ContextTooLargeError(actual_tokens=total_tokens, max_tokens=max_ctx)
  return context, total_tokens
  ```
- [ ] 4.8 Confirm: `grep "CHARS_PER_TOKEN" app/services/context_manager.py` — zero matches
- [ ] 4.9 Confirm: `grep "_estimate_tokens" app/services/context_manager.py` — zero matches
- [ ] 4.10 `ruff check app/services/context_manager.py` — zero errors

**Acceptance**: `CHARS_PER_TOKEN` and `_estimate_tokens` are gone. `count_tokens` is used.

---

## Task 5 — Update app/routes/conversation_turn.py

- [ ] 5.1 Open `app/routes/conversation_turn.py`
- [ ] 5.2 Add import: `from app.services.token_counter import ContextTooLargeError`
- [ ] 5.3 Wrap the `prepare_context()` call in try/except:
  ```python
  try:
      prepared_context, context_tokens_used = prepare_context(
          history=history,
          message=request.message,
          strategy=request.context_strategy,
          model="gpt-4o",
      )
  except ContextTooLargeError as exc:
      raise HTTPException(
          status_code=400,
          detail=f"Context too large: {exc.actual_tokens} tokens exceeds limit of {exc.max_tokens}",
      )
  ```
- [ ] 5.4 `ruff check app/routes/conversation_turn.py` — zero errors

**Acceptance**: `ContextTooLargeError` is caught and returns HTTP 400 with structured message.

---

## Task 6 — Update tests/test_services.py

- [ ] 6.1 Open `tests/test_services.py`
- [ ] 6.2 For each test that asserts on `context_tokens_used`:
  - Run the relevant `prepare_context()` call with real inputs to get the exact tiktoken value
  - Update the assertion to that exact integer
  - Add a comment showing the input and the tiktoken model used
- [ ] 6.3 Add a test for `ContextTooLargeError`:
  - Use `monkeypatch.setenv("MAX_CONTEXT_TOKENS", "10")`
  - Call `prepare_context()` with a long enough input to exceed 10 tokens
  - Assert `ContextTooLargeError` is raised
  - Assert `exc.actual_tokens > 10` and `exc.max_tokens == 10`
- [ ] 6.4 Run: `OTEL_SDK_DISABLED=true pytest tests/test_services.py -v` — all tests pass

**Acceptance**: No assertion uses `// 4` math. Exact tiktoken values are hard-coded.

---

## Task 7 — Full verification

- [ ] 7.1 `grep "CHARS_PER_TOKEN" .` — zero matches across the entire repo
- [ ] 7.2 `grep "_estimate_tokens" .` — zero matches
- [ ] 7.3 `grep "tiktoken" app/services/context_manager.py` — zero matches (it's only in `token_counter.py`)
- [ ] 7.4 `OTEL_SDK_DISABLED=true pytest tests/ -v` — all tests pass, ≥ 151 tests
- [ ] 7.5 `ruff check app/services/` — zero errors
- [ ] 7.6 `mypy app/services/ --ignore-missing-imports` — zero errors

**Acceptance**: All structural checks pass. Full test suite green.

---

## Completion criteria
This spec is complete when:
- `CHARS_PER_TOKEN` and `_estimate_tokens` are absent from the codebase
- `count_tokens` uses tiktoken BPE encoding
- `ContextTooLargeError` is raised and caught with HTTP 400
- All token count assertions in tests use exact tiktoken values
- `OTEL_SDK_DISABLED=true pytest tests/ -v` reports ≥ 151 tests, all passing

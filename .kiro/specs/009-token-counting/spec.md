# Spec: 009 Accurate Token Counting with tiktoken

## Goal
Replace the character-division heuristic (`len(text) // 4`) in context management with BPE
token counting via `tiktoken`. This prevents `BadRequestError` from the provider when context
exceeds the model's window, and makes the `context_tokens_used` field in telemetry accurate.

## Prerequisite gate
Spec 008 must be complete before starting:

```bash
OTEL_SDK_DISABLED=true pytest tests/ -v  # ≥ 147 tests, all passing
grep "async def call_llm" gateway/client.py  # must match
```

Both must pass before any task in this spec begins.

## What this spec adds
- `app/services/token_counter.py` — `count_tokens()` function and `ContextTooLargeError`
- `tests/test_token_counter.py` — unit tests for token counting

## What this spec changes
- `app/services/context_manager.py` — replace `_estimate_tokens` with `count_tokens`, add `ContextTooLargeError` guard
- `app/routes/conversation_turn.py` — catch `ContextTooLargeError`, return HTTP 400
- `tests/test_services.py` — update token count assertions to exact tiktoken values
- `requirements.txt` — add `tiktoken`

## What this spec does NOT change
The gateway, routes other than `conversation_turn`, schemas, middleware, auth, OTel setup,
and telemetry JSONL format are frozen.

## Problem
`app/services/context_manager.py` estimates tokens as `len(text) // 4`. This is accurate
for short ASCII text but under-counts by 2–3× for code blocks, JSON payloads, and non-Latin
scripts. When `prepare_context()` assembles a context window that exceeds the model's limit,
the provider returns a `BadRequestError` with no graceful recovery. The error bubbles up as
an unhandled 500.

## Acceptance criteria
1. `CHARS_PER_TOKEN` constant is removed from `context_manager.py`.
2. `_estimate_tokens()` function is removed from `context_manager.py`.
3. `count_tokens("Hello world", "gpt-4o")` returns the exact value produced by tiktoken.
4. `count_tokens("", "gpt-4o")` returns 0.
5. `count_tokens(text, "unknown-model-xyz")` falls back to `cl100k_base` without raising.
6. `prepare_context()` raises `ContextTooLargeError` when the assembled context exceeds `MAX_CONTEXT_TOKENS`.
7. `/conversation-turn` returns HTTP 400 with a descriptive message when `ContextTooLargeError` is raised.
8. All token count assertions in `tests/test_services.py` use exact tiktoken values.
9. `OTEL_SDK_DISABLED=true pytest tests/ -v` — all tests pass.

## Testing requirements
- `tests/test_token_counter.py`: exact count for a known string, empty string, unknown model fallback,
  lru_cache reuse assertion.
- `tests/test_services.py`: update assertions to exact tiktoken values; add a test that
  `ContextTooLargeError` is raised when context exceeds the limit (use `monkeypatch` to set
  `MAX_CONTEXT_TOKENS=10`).

## Hard rules
- `tiktoken` must be imported only in `app/services/token_counter.py` — it must not appear in
  any other module.
- The encoder is cached per model using `functools.lru_cache` — not re-created on every call.
- `ContextTooLargeError` must be defined in `token_counter.py` and imported where needed.
- `MAX_CONTEXT_TOKENS` is read from the `MAX_CONTEXT_TOKENS` env var (default `8192`).
- The `model` parameter in `prepare_context()` defaults to `"gpt-4o"` — backward compatible.

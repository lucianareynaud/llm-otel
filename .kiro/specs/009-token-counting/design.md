# Design: 009 Accurate Token Counting with tiktoken

---

## app/services/token_counter.py (new file)

```python
import functools
import os
import tiktoken


class ContextTooLargeError(ValueError):
    def __init__(self, actual_tokens: int, max_tokens: int) -> None:
        self.actual_tokens = actual_tokens
        self.max_tokens = max_tokens
        super().__init__(
            f"Context too large: {actual_tokens} tokens exceeds limit of {max_tokens}"
        )


@functools.lru_cache(maxsize=16)
def _get_encoding(model: str) -> tiktoken.Encoding:
    try:
        return tiktoken.encoding_for_model(model)
    except KeyError:
        # cl100k_base is the vocabulary used by gpt-4o and gpt-4o-mini
        return tiktoken.get_encoding("cl100k_base")


def count_tokens(text: str, model: str = "gpt-4o") -> int:
    """Return the exact BPE token count for `text` using the vocabulary of `model`.

    Falls back to cl100k_base encoding for unknown model identifiers.
    The encoder is cached per model via lru_cache to avoid repeated disk reads.
    """
    return len(_get_encoding(model).encode(text))
```

`ContextTooLargeError` is a `ValueError` subclass so it is treated as a bad-input error, not
an internal server error. It carries `actual_tokens` and `max_tokens` as structured attributes
for use in the HTTP 400 response body.

---

## app/services/context_manager.py changes

### Removals
- `CHARS_PER_TOKEN = 4` constant — deleted
- `_estimate_tokens(text: str) -> int` function — deleted

### New import
```python
from app.services.token_counter import count_tokens, ContextTooLargeError
```

### prepare_context signature
Add `model: str = "gpt-4o"` parameter. Thread it through to every private helper that
computes token counts.

### MAX_CONTEXT_TOKENS guard
At the end of `prepare_context()`, after assembling the final context string:

```python
max_ctx = int(os.environ.get("MAX_CONTEXT_TOKENS", "8192"))
total_tokens = count_tokens(context, model)
if total_tokens > max_ctx:
    raise ContextTooLargeError(actual_tokens=total_tokens, max_tokens=max_ctx)
return context, total_tokens
```

---

## app/routes/conversation_turn.py changes

Wrap the `prepare_context()` call:

```python
from app.services.token_counter import ContextTooLargeError

try:
    prepared_context, context_tokens_used = prepare_context(
        history=history,
        message=request.message,
        strategy=request.context_strategy,
        model="gpt-4o",  # conservative default; exact model resolved by gateway
    )
except ContextTooLargeError as exc:
    raise HTTPException(
        status_code=400,
        detail=f"Context too large: {exc.actual_tokens} tokens exceeds limit of {exc.max_tokens}",
    )
```

---

## Test update strategy for tests/test_services.py

Any existing assertion like `assert context_tokens_used == 15` must be replaced with the
actual tiktoken value. The correct approach:

1. Run the function with the same inputs using the real tiktoken encoder.
2. Print the output.
3. Hard-code that value as the expected value.

Do not compute the expected value at test runtime (that would be testing tiktoken against
itself). Hard-code the exact integer once, with a comment showing the input.

Example:
```python
# "Hello world" → tiktoken gpt-4o → 2 tokens
assert context_tokens_used == 2
```

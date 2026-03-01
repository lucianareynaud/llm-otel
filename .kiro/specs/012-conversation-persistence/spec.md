# Spec: 012 Server-Side Conversation Persistence

## Goal
Store conversation history server-side so that clients only need to send a `conversation_id`
on subsequent turns, not the full history. This is required for any multi-turn assistant
deployment where the client is a web browser or mobile app that does not reliably track history.

## Prerequisite gate
Spec 011 must be complete before starting:

```bash
OTEL_SDK_DISABLED=true pytest tests/ -v  # ≥ 167 tests, all passing
```

All tests must be green before any task in this spec begins.

## What this spec adds
- `app/services/conversation_store.py` — `ConversationStore` protocol, `InMemoryConversationStore`, `RedisConversationStore`, `get_conversation_store()`
- `tests/test_conversation_store.py` — store unit tests

## What this spec changes
- `app/routes/conversation_turn.py` — inject store, resolve history from server-side, persist turns
- `tests/test_routes.py` — override `get_conversation_store` dependency in existing tests
- `requirements.txt` — add `redis`, `fakeredis`

## What this spec does NOT change
The request/response schema for `/conversation-turn` does not change. Sending `history` is
still valid (used for bootstrap). Gateway, auth, cache, circuit breaker, and all other specs
are frozen.

## Problem
`/conversation-turn` requires the client to send the entire conversation history on every
request. `conversation_id` is accepted in the request body but never stored or looked up.
There is no server-side state. In production, clients (browsers, mobile apps) cannot
reliably maintain and retransmit growing conversation histories.

## Acceptance criteria
1. A second POST to `/conversation-turn` with the same `conversation_id` and `history=[]`
   returns a response that incorporates prior context from server-side storage.
2. `context_tokens_used` on the second call is larger than on the first call (proves context
   was loaded from the store).
3. When `history` is sent by the client and no server-side conversation exists, the store is
   bootstrapped from the client-provided history.
4. When both server-side history and client history exist, server-side wins.
5. `InMemoryConversationStore` is used by default when `REDIS_URL` is not set.
6. `RedisConversationStore` is used when `REDIS_URL` is set (tested with `fakeredis`).
7. Conversations expire after `CONVERSATION_TTL_SECONDS` of inactivity (lazy expiry).
8. `OTEL_SDK_DISABLED=true pytest tests/ -v` — all tests pass.

## Testing requirements
- `tests/test_conversation_store.py`: get unknown ID returns `[]`; append then get returns
  messages in order; delete removes; TTL expiry; two IDs are isolated; Redis interface with
  `fakeredis`.
- `tests/test_routes.py`: override `get_conversation_store` with `InMemoryConversationStore`;
  test that second call with same ID and empty history includes prior context.
- Tests must never require a real Redis connection.

## Hard rules
- The `ConversationStore` abstraction is a `typing.Protocol` — no abstract base classes.
- `redis` is imported conditionally — only when `REDIS_URL` is set. The package must not
  cause an `ImportError` in environments without it installed.
- `get_conversation_store()` uses `functools.lru_cache` to return the same instance per process.
- The route handler uses `Depends(get_conversation_store)` — no global store reference in routes.
- The schema for `/conversation-turn` (`history: list[str]`) is not changed. Clients may
  continue to send history for bootstrap.

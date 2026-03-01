# Tasks: 012 Server-Side Conversation Persistence

## Prerequisite gate
Run before starting any task:

```bash
OTEL_SDK_DISABLED=true pytest tests/ -v  # ≥ 221 tests, all passing
```

If any test fails, fix it before proceeding.

---

## Task 1 — Add redis and fakeredis to requirements.txt

- [ ] 1.1 Run `pip install redis fakeredis` and note the installed versions
- [ ] 1.2 Add to `requirements.txt`:
  - `redis==<version>` — soft runtime dependency (only used when `REDIS_URL` is set)
  - `fakeredis==<version>` — test-only dependency
- [ ] 1.3 Verify: `python -c "import fakeredis"` — no ImportError

**Acceptance**: Both packages install without conflicts.

---

## Task 2 — Create app/services/conversation_store.py

- [ ] 2.1 Create `app/services/conversation_store.py`
- [ ] 2.2 Implement `ConversationStore` as a `typing.Protocol` with three methods:
  - `get(conversation_id: str) -> list[str]`
  - `append(conversation_id: str, message: str) -> None`
  - `delete(conversation_id: str) -> None`
- [ ] 2.3 Implement `InMemoryConversationStore`:
  - `__init__`: initialise `_store: dict[str, tuple[list[str], float]]`; read `CONVERSATION_TTL_SECONDS` env var (default 3600)
  - `get()`: check TTL on read (lazy expiry); refresh last-access on hit; return `[]` on miss or expiry
  - `append()`: call `get()` to load existing messages and clean up expired; append new message; write back with fresh timestamp
  - `delete()`: `_store.pop(conversation_id, None)`
- [ ] 2.4 Implement `RedisConversationStore`:
  - `__init__(redis_url: str)`: import `redis` inside the method body; create client; set TTL
  - `get()`: `LRANGE conv:{id} 0 -1`
  - `append()`: `RPUSH conv:{id} message` then `EXPIRE conv:{id} ttl`
  - `delete()`: `DEL conv:{id}`
- [ ] 2.5 Implement `get_conversation_store() -> ConversationStore`:
  - Decorated with `@functools.lru_cache(maxsize=1)`
  - If `REDIS_URL` is set and `redis` is importable: return `RedisConversationStore(REDIS_URL)`
  - Otherwise: return `InMemoryConversationStore()`
- [ ] 2.6 `ruff check app/services/conversation_store.py` — zero errors
- [ ] 2.7 `mypy app/services/conversation_store.py --ignore-missing-imports` — zero errors

**Acceptance**: Module imports without `redis` installed. `get_conversation_store()` returns `InMemoryConversationStore` when `REDIS_URL` is not set.

---

## Task 3 — Create tests/test_conversation_store.py

- [ ] 3.1 Create `tests/test_conversation_store.py`
- [ ] 3.2 Write InMemoryConversationStore tests:
  - `test_get_unknown_returns_empty`: `store.get("nonexistent")` → `[]`
  - `test_append_then_get_preserves_order`: append three messages; `get()` returns them in order
  - `test_delete_removes_conversation`: append; delete; `get()` → `[]`
  - `test_ttl_expiry`: create store with `CONVERSATION_TTL_SECONDS=0` (or monkeypatch `_ttl=0`);
    append a message; immediately call `get()` — should return `[]` (TTL expired)
  - `test_two_conversations_isolated`: append to ID `"a"` and ID `"b"`; verify each returns only its own messages
- [ ] 3.3 Write RedisConversationStore tests using `fakeredis`:
  - `test_redis_get_unknown_returns_empty`: use `fakeredis.FakeRedis(decode_responses=True)`;
    inject into `RedisConversationStore`; `get("x")` → `[]`
  - `test_redis_append_then_get`: append two messages; `get()` returns them
  - `test_redis_delete`: append; delete; `get()` → `[]`
  - Note: to inject `fakeredis`, monkeypatch `redis.Redis.from_url` to return a `FakeRedis` instance
- [ ] 3.4 Run: `OTEL_SDK_DISABLED=true pytest tests/test_conversation_store.py -v` — all 8 tests pass

**Acceptance**: All 8 store tests pass. No real Redis connection needed.

---

## Task 4 — Update app/routes/conversation_turn.py

- [ ] 4.1 Open `app/routes/conversation_turn.py`
- [ ] 4.2 Add imports:
  ```python
  from fastapi import Depends
  from app.services.conversation_store import ConversationStore, get_conversation_store
  ```
- [ ] 4.3 Add `store: ConversationStore = Depends(get_conversation_store)` to the route handler signature
- [ ] 4.4 Replace the current `history = request.history` resolution with:
  ```python
  server_history = store.get(request.conversation_id)
  if server_history:
      history = server_history
  elif request.history:
      history = request.history
      for msg in request.history:
          store.append(request.conversation_id, msg)
  else:
      history = []
  ```
- [ ] 4.5 After the LLM response, persist both turns:
  ```python
  store.append(request.conversation_id, request.message)
  store.append(request.conversation_id, result.text)
  ```
- [ ] 4.6 `ruff check app/routes/conversation_turn.py` — zero errors

**Acceptance**: History is resolved from server-side store. Both turns are persisted after response.

---

## Task 5 — Update tests/test_routes.py for conversation_turn

- [ ] 5.1 Open `tests/test_routes.py`
- [ ] 5.2 Add a pytest fixture that overrides `get_conversation_store` with a fresh `InMemoryConversationStore`:
  ```python
  from app.services.conversation_store import InMemoryConversationStore, get_conversation_store

  @pytest.fixture(autouse=True)
  def reset_conversation_store():
      store = InMemoryConversationStore()
      app.dependency_overrides[get_conversation_store] = lambda: store
      yield
      app.dependency_overrides.clear()
  ```
- [ ] 5.3 Add a new test `test_second_turn_uses_server_history`:
  - POST to `/conversation-turn` with `conversation_id="test-conv"`, `message="Hello"`, `history=[]`
  - POST again with same `conversation_id`, `message="What did I just say?"`, `history=[]`
  - Assert that `context_tokens_used` on the second call is greater than on the first call
  - This proves the store returned prior context
- [ ] 5.4 Run: `OTEL_SDK_DISABLED=true pytest tests/test_routes.py -v` — all tests pass

**Acceptance**: Existing tests pass unchanged. New test proves server-side history is loaded.

---

## Task 6 — Full verification

- [ ] 6.1 `OTEL_SDK_DISABLED=true pytest tests/ -v` — all tests pass, ≥ 230 tests
- [ ] 6.2 `ruff check app/services/conversation_store.py app/routes/conversation_turn.py` — zero errors
- [ ] 6.3 Confirm: `redis` import only happens inside `RedisConversationStore.__init__` — not at module level
- [ ] 6.4 Confirm: `python -c "from app.services.conversation_store import get_conversation_store"` succeeds
  even when `redis` is not installed (because `redis` is imported lazily)

**Acceptance**: Full test suite green. Redis import is conditional. Dependency injection wires correctly.

---

## Completion criteria
This spec is complete when:
- A second call to `/conversation-turn` with the same `conversation_id` and empty `history` returns context from server-side storage
- `InMemoryConversationStore` is the default backend when `REDIS_URL` is not set
- `redis` is not imported at module level
- `OTEL_SDK_DISABLED=true pytest tests/ -v` reports ≥ 230 tests, all passing
- The `/conversation-turn` schema is unchanged

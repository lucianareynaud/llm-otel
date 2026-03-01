# Design: 012 Server-Side Conversation Persistence

---

## app/services/conversation_store.py

### Protocol

```python
from typing import Protocol

class ConversationStore(Protocol):
    def get(self, conversation_id: str) -> list[str]: ...
    def append(self, conversation_id: str, message: str) -> None: ...
    def delete(self, conversation_id: str) -> None: ...
```

`Protocol` (not ABC) means any class with these three methods satisfies the type without
explicit inheritance. This keeps the interface lightweight and test-friendly.

### InMemoryConversationStore

```python
import os
import time

class InMemoryConversationStore:
    def __init__(self) -> None:
        # (messages, last_access_time)
        self._store: dict[str, tuple[list[str], float]] = {}
        self._ttl = int(os.environ.get("CONVERSATION_TTL_SECONDS", "3600"))

    def get(self, conversation_id: str) -> list[str]:
        entry = self._store.get(conversation_id)
        if entry is None:
            return []
        messages, last_access = entry
        if time.monotonic() - last_access > self._ttl:
            del self._store[conversation_id]
            return []
        # Refresh last-access time on read
        self._store[conversation_id] = (messages, time.monotonic())
        return list(messages)

    def append(self, conversation_id: str, message: str) -> None:
        existing = self.get(conversation_id)  # cleans up expired entries
        existing.append(message)
        self._store[conversation_id] = (existing, time.monotonic())

    def delete(self, conversation_id: str) -> None:
        self._store.pop(conversation_id, None)
```

TTL is checked lazily on `get()` — no background cleanup task needed for the MVP.

### RedisConversationStore

```python
class RedisConversationStore:
    def __init__(self, redis_url: str) -> None:
        import redis  # conditional import
        self._client = redis.Redis.from_url(redis_url, decode_responses=True)
        self._ttl = int(os.environ.get("CONVERSATION_TTL_SECONDS", "3600"))
        self._key_prefix = "conv:"

    def _key(self, conversation_id: str) -> str:
        return f"{self._key_prefix}{conversation_id}"

    def get(self, conversation_id: str) -> list[str]:
        return self._client.lrange(self._key(conversation_id), 0, -1)  # type: ignore[return-value]

    def append(self, conversation_id: str, message: str) -> None:
        k = self._key(conversation_id)
        self._client.rpush(k, message)
        self._client.expire(k, self._ttl)

    def delete(self, conversation_id: str) -> None:
        self._client.delete(self._key(conversation_id))
```

`redis` is imported inside `__init__` — the class can be defined without `redis` installed;
it only fails when instantiated with a real Redis URL.

### get_conversation_store factory

```python
import functools

@functools.lru_cache(maxsize=1)
def get_conversation_store() -> ConversationStore:
    redis_url = os.environ.get("REDIS_URL")
    if redis_url:
        try:
            return RedisConversationStore(redis_url)
        except ImportError:
            pass  # redis not installed; fall back to in-memory
    return InMemoryConversationStore()
```

`lru_cache(maxsize=1)` returns the same store instance on every `Depends()` call within a
process. This is correct for in-process state sharing without a global variable.

---

## app/routes/conversation_turn.py changes

### Dependency injection

```python
from app.services.conversation_store import ConversationStore, get_conversation_store

async def conversation_turn(
    request: ConversationTurnRequest,
    store: ConversationStore = Depends(get_conversation_store),
) -> ConversationTurnResponse:
```

### History resolution (priority order)

```python
server_history = store.get(request.conversation_id)

if server_history:
    history = server_history          # server-side wins
elif request.history:
    history = request.history         # bootstrap from client
    for msg in request.history:
        store.append(request.conversation_id, msg)
else:
    history = []                      # fresh conversation
```

### Post-response persistence

```python
store.append(request.conversation_id, request.message)   # user turn
store.append(request.conversation_id, result.text)        # assistant turn
```

---

## Test dependency override pattern

```python
from app.services.conversation_store import InMemoryConversationStore

def override_store():
    return InMemoryConversationStore()

app.dependency_overrides[get_conversation_store] = override_store

# Teardown:
app.dependency_overrides.clear()
```

Use a pytest `autouse` fixture with `yield` to ensure teardown always runs.

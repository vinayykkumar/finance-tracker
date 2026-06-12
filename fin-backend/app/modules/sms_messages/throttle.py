"""Per-user in-process rate limit for POST /sms-messages/sync.

Mirrors ``app.auth.login_throttle``: simple in-memory sliding window, not
multi-replica safe — swap for a shared store (Redis) before running more
than one API process. A batch already caps at
``schemas.MAX_BATCH_SIZE`` messages, so this mainly bounds *call frequency*
(e.g. a buggy client retry-looping the sync endpoint).
"""

from __future__ import annotations

import time
from collections import defaultdict, deque
from threading import Lock
from uuid import UUID

_WINDOW_SEC = 60
_MAX_SYNCS_PER_WINDOW = 6

_lock = Lock()
_calls: dict[UUID, deque[float]] = defaultdict(deque)


def _prune(user_id: UUID, now: float) -> None:
    q = _calls[user_id]
    while q and now - q[0] > _WINDOW_SEC:
        q.popleft()


def is_sync_throttled(user_id: UUID) -> bool:
    now = time.monotonic()
    with _lock:
        _prune(user_id, now)
        return len(_calls[user_id]) >= _MAX_SYNCS_PER_WINDOW


def record_sync_call(user_id: UUID) -> None:
    now = time.monotonic()
    with _lock:
        _prune(user_id, now)
        _calls[user_id].append(now)

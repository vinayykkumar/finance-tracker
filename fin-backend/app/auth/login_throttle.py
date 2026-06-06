"""Simple in-process login rate limiting (per normalized email). Not multi-replica safe — use Redis in production clusters."""

from __future__ import annotations

import time
from collections import defaultdict, deque
from threading import Lock

_WINDOW_SEC = 15 * 60
_MAX_ATTEMPTS = 12

_lock = Lock()
_failures: dict[str, deque[float]] = defaultdict(deque)


def _prune(email_key: str, now: float) -> None:
    q = _failures[email_key]
    while q and now - q[0] > _WINDOW_SEC:
        q.popleft()


def record_login_failure(email: str) -> None:
    email_key = email.strip().lower()
    now = time.monotonic()
    with _lock:
        _prune(email_key, now)
        _failures[email_key].append(now)


def clear_login_failures(email: str) -> None:
    email_key = email.strip().lower()
    with _lock:
        _failures.pop(email_key, None)


def is_login_throttled(email: str) -> bool:
    email_key = email.strip().lower()
    now = time.monotonic()
    with _lock:
        _prune(email_key, now)
        return len(_failures[email_key]) >= _MAX_ATTEMPTS

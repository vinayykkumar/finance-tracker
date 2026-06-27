"""Tests for in-process login rate limiting."""

import pytest
from app.auth import login_throttle


@pytest.fixture(autouse=True)
def reset_throttle_state() -> None:
    """Ensure each test starts with a clean failure ledger."""
    login_throttle._failures.clear()
    yield
    login_throttle._failures.clear()


def test_fresh_email_is_not_throttled() -> None:
    assert login_throttle.is_login_throttled("alice@example.com") is False


def test_throttles_after_max_attempts() -> None:
    email = "bob@example.com"
    for _ in range(login_throttle._MAX_ATTEMPTS):
        login_throttle.record_login_failure(email)
    assert login_throttle.is_login_throttled(email) is True


def test_below_max_attempts_not_throttled() -> None:
    email = "carol@example.com"
    for _ in range(login_throttle._MAX_ATTEMPTS - 1):
        login_throttle.record_login_failure(email)
    assert login_throttle.is_login_throttled(email) is False


def test_email_is_normalized() -> None:
    for _ in range(login_throttle._MAX_ATTEMPTS):
        login_throttle.record_login_failure("  Dave@Example.COM  ")
    # Lookup with different casing/whitespace hits the same bucket.
    assert login_throttle.is_login_throttled("dave@example.com") is True


def test_clear_resets_throttle() -> None:
    email = "erin@example.com"
    for _ in range(login_throttle._MAX_ATTEMPTS):
        login_throttle.record_login_failure(email)
    assert login_throttle.is_login_throttled(email) is True

    login_throttle.clear_login_failures(email)
    assert login_throttle.is_login_throttled(email) is False


def test_failures_are_pruned_outside_window(monkeypatch: pytest.MonkeyPatch) -> None:
    email = "frank@example.com"
    base = 1000.0
    # Record all failures "now".
    monkeypatch.setattr(login_throttle.time, "monotonic", lambda: base)
    for _ in range(login_throttle._MAX_ATTEMPTS):
        login_throttle.record_login_failure(email)
    assert login_throttle.is_login_throttled(email) is True

    # Advance the clock past the window; old failures should be pruned.
    monkeypatch.setattr(
        login_throttle.time, "monotonic", lambda: base + login_throttle._WINDOW_SEC + 1
    )
    assert login_throttle.is_login_throttled(email) is False

"""Service-layer unit tests — pure helpers, no I/O.

The helpers ``validate_item``, ``compute_fingerprint``, and ``compute_body_hash``
are synchronous pure functions and can be tested without spinning up a database or
async runtime.

SmsIngestService.ingest_batch is exercised with a mocked repository via the API
tests in test_api.py.
"""

import uuid
from datetime import UTC, datetime, timedelta

import pytest

from app.modules.sms_ingest.schemas import SmsItemIn
from app.modules.sms_ingest.service import (
    MAX_AGE_DAYS,
    MAX_BODY_LEN,
    MAX_FUTURE_SECONDS,
    compute_body_hash,
    compute_fingerprint,
    validate_item,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _item(
    body: str = "INR 100 debited from SBI account.",
    sender: str = "SBIINB",
    received_at: datetime | None = None,
    device_message_id: str = "msg_001",
) -> SmsItemIn:
    return SmsItemIn(
        device_message_id=device_message_id,
        sender=sender,
        body=body,
        received_at=received_at or datetime.now(UTC),
    )


NOW = datetime.now(UTC)


# ---------------------------------------------------------------------------
# validate_item
# ---------------------------------------------------------------------------

def test_validate_accepts_valid_item() -> None:
    assert validate_item(_item(), NOW) is None


def test_validate_rejects_body_too_large() -> None:
    """Service guard is tested directly with a dataclass-style object that bypasses
    Pydantic's own max_length check — both defences protect in real usage."""
    oversized_item = SmsItemIn.model_construct(
        device_message_id="id",
        sender="SBIINB",
        body="x" * (MAX_BODY_LEN + 1),
        received_at=NOW,
    )
    assert validate_item(oversized_item, NOW) == "body_too_large"


def test_validate_rejects_body_at_exact_limit_is_fine() -> None:
    at_limit = "x" * MAX_BODY_LEN
    item = SmsItemIn(device_message_id="id", sender="S", body=at_limit, received_at=NOW)
    assert validate_item(item, NOW) is None


def test_validate_rejects_sender_too_long() -> None:
    long_sender_item = SmsItemIn.model_construct(
        device_message_id="id",
        sender="A" * 65,
        body="hello",
        received_at=NOW,
    )
    assert validate_item(long_sender_item, NOW) == "sender_too_long"


def test_validate_rejects_old_message() -> None:
    old_ts = NOW - timedelta(days=MAX_AGE_DAYS + 1)
    assert validate_item(_item(received_at=old_ts), NOW) == "received_at_too_old"


def test_validate_accepts_exactly_at_age_limit() -> None:
    edge_ts = NOW - timedelta(days=MAX_AGE_DAYS)
    assert validate_item(_item(received_at=edge_ts), NOW) is None


def test_validate_rejects_future_beyond_skew() -> None:
    future_ts = NOW + timedelta(seconds=MAX_FUTURE_SECONDS + 60)
    assert validate_item(_item(received_at=future_ts), NOW) == "received_at_future"


def test_validate_accepts_future_within_clock_skew() -> None:
    near_future = NOW + timedelta(seconds=MAX_FUTURE_SECONDS - 10)
    assert validate_item(_item(received_at=near_future), NOW) is None


def test_validate_naive_datetime_treated_as_utc() -> None:
    """A naive received_at should not crash — treated as UTC."""
    naive_ts = datetime.utcnow() - timedelta(hours=1)
    item = _item(received_at=naive_ts)
    assert validate_item(item, NOW) is None


# ---------------------------------------------------------------------------
# compute_fingerprint
# ---------------------------------------------------------------------------

USER_A = uuid.uuid4()
USER_B = uuid.uuid4()


def test_fingerprint_is_deterministic() -> None:
    fp1 = compute_fingerprint(USER_A, "SBIINB", "msg_001", "bodyhash")
    fp2 = compute_fingerprint(USER_A, "SBIINB", "msg_001", "bodyhash")
    assert fp1 == fp2


def test_fingerprint_differs_across_users() -> None:
    fp_a = compute_fingerprint(USER_A, "SBIINB", "msg_001", "hash")
    fp_b = compute_fingerprint(USER_B, "SBIINB", "msg_001", "hash")
    assert fp_a != fp_b


def test_fingerprint_differs_across_message_ids() -> None:
    fp1 = compute_fingerprint(USER_A, "SBIINB", "msg_001", "hash")
    fp2 = compute_fingerprint(USER_A, "SBIINB", "msg_002", "hash")
    assert fp1 != fp2


def test_fingerprint_empty_device_id_uses_body_hash() -> None:
    """When device_message_id is empty, body hash is folded in so messages with
    different bodies still produce different fingerprints."""
    fp_body1 = compute_fingerprint(USER_A, "SBIINB", "", "hash_body_1")
    fp_body2 = compute_fingerprint(USER_A, "SBIINB", "", "hash_body_2")
    assert fp_body1 != fp_body2


def test_fingerprint_is_64_hex_chars() -> None:
    fp = compute_fingerprint(USER_A, "SBIINB", "msg_001", "bodyhash")
    assert len(fp) == 64
    assert all(c in "0123456789abcdef" for c in fp)


# ---------------------------------------------------------------------------
# compute_body_hash
# ---------------------------------------------------------------------------

def test_body_hash_is_deterministic() -> None:
    h1 = compute_body_hash("hello")
    h2 = compute_body_hash("hello")
    assert h1 == h2


def test_body_hash_differs_for_different_bodies() -> None:
    h1 = compute_body_hash("body A")
    h2 = compute_body_hash("body B")
    assert h1 != h2


def test_body_hash_is_sha256_length() -> None:
    h = compute_body_hash("test")
    assert len(h) == 64

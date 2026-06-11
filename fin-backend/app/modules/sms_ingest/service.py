"""SMS ingest use-cases.

Boundaries
----------
* This service does NOT write ledger_transactions — that is a follow-on task.
* The ``ledger_tx_id`` column on ``sms_ingest_items`` is left NULL here.
* No LLM / ML categorisation — only deterministic template matching.
"""

import hashlib
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.sms_ingest.parser import normalize_sender, try_parse
from app.modules.sms_ingest.repository import SmsIngestRepository
from app.modules.sms_ingest.schemas import BatchIn, BatchResult, RejectedItem, SmsItemIn

# ---------------------------------------------------------------------------
# Validation constants
# ---------------------------------------------------------------------------

MAX_BODY_LEN = 2_000          # chars — any real SMS fits here
MAX_SENDER_LEN = 64           # chars — Android sender field
MAX_BATCH_SIZE = 100          # items per request
MAX_AGE_DAYS = 30             # reject messages older than this
MAX_FUTURE_SECONDS = 300      # 5-minute clock-skew tolerance


# ---------------------------------------------------------------------------
# Pure helpers (no I/O — separately testable)
# ---------------------------------------------------------------------------


def compute_body_hash(body: str) -> str:
    """SHA-256 hex of the raw body.  The body itself is never stored."""
    return hashlib.sha256(body.encode()).hexdigest()


def compute_fingerprint(user_id: UUID, sender_key: str, device_message_id: str, body_hash: str) -> str:
    """Stable dedupe fingerprint.

    Incorporates ``device_message_id`` when present; falls back to ``body_hash``
    so that messages without a device ID are still deduplicated correctly.
    """
    stable_id = device_message_id.strip() if device_message_id.strip() else body_hash
    payload = f"{user_id}|{sender_key}|{stable_id}"
    return hashlib.sha256(payload.encode()).hexdigest()


def validate_item(item: SmsItemIn, now: datetime) -> str | None:
    """Return a rejection-reason string, or ``None`` if the item is acceptable.

    All reasons are stable machine-readable tokens the mobile client can act on.
    """
    if len(item.body) > MAX_BODY_LEN:
        return "body_too_large"
    if len(item.sender) > MAX_SENDER_LEN:
        return "sender_too_long"

    # Normalise to UTC for comparison
    received = item.received_at
    if received.tzinfo is None:
        received = received.replace(tzinfo=UTC)

    age = now - received
    if age > timedelta(days=MAX_AGE_DAYS):
        return "received_at_too_old"
    if (received - now).total_seconds() > MAX_FUTURE_SECONDS:
        return "received_at_future"

    return None


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------


class SmsIngestService:
    def __init__(self, session: AsyncSession) -> None:
        self._repo = SmsIngestRepository(session)
        self._session = session

    async def ingest_batch(self, user_id: UUID, body: BatchIn) -> BatchResult:
        """Process a batch: validate → dedupe → parse → persist.

        Edge-case contract
        ------------------
        * **Duplicate upload** (same fingerprint): ``ON CONFLICT DO NOTHING`` — row
          count stays 1, duplicate counter increments.  Safe under retries.
        * **Clock skew** (device clock ahead by < 5 min): accepted.
          Device > 5 min ahead or > 30 days old: rejected as ``received_at_future``
          / ``received_at_too_old``.
        * **Oversized body**: rejected as ``body_too_large`` — not stored at all.
        * **Unparsed template**: stored with ``parse_status='unparsed'``,
          ``parsed_payload=None``.  Not rejected — ops use this to prioritise
          new template work.
        * **Sender looks like bank but body fails validation**: still stored as
          ``unparsed`` (body validated before parse attempt).
        """
        now = datetime.now(UTC)
        accepted = 0
        duplicates = 0
        rejected: list[RejectedItem] = []

        async with self._session.begin():
            for item in body.items:
                reason = validate_item(item, now)
                if reason:
                    rejected.append(
                        RejectedItem(device_message_id=item.device_message_id, reason=reason)
                    )
                    continue

                sender_key = normalize_sender(item.sender)
                body_hash = compute_body_hash(item.body)
                fingerprint = compute_fingerprint(
                    user_id, sender_key, item.device_message_id, body_hash
                )
                payload, status = try_parse(sender_key, item.body)

                inserted = await self._repo.upsert_by_fingerprint(
                    user_id=user_id,
                    sender_key=sender_key,
                    raw_body_hash=body_hash,
                    device_message_id=item.device_message_id,
                    received_at=item.received_at,
                    parsed_payload=payload.to_dict() if payload else None,
                    parse_status=status,
                    template_key=payload.template_key if payload else None,
                    dedupe_fingerprint=fingerprint,
                )
                if inserted:
                    accepted += 1
                else:
                    duplicates += 1

        return BatchResult(accepted=accepted, duplicates=duplicates, rejected=rejected)

"""SMS ingest use-cases — idempotent insert-by-fingerprint, v1 parsing.

Out of scope here (by design — see docs/sms-ingest.md): writing
``ledger_transactions``, account mapping, and any LLM/ML categorization.
This service only records what arrived and whether it matched a known
template.
"""

import hashlib
import re
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.sms_message import SmsMessage
from app.modules.sms_messages.parsers import parse_sms
from app.modules.sms_messages.repository import SmsMessageRepository
from app.modules.sms_messages.schemas import (
    SmsMessageIngest,
    SmsMessageRead,
    SmsSyncResponse,
    SmsSyncResultItem,
)

# Storage cap for `body`. Concatenated SMS realistically top out around
# 10 segments * ~153 chars ≈ 1530 chars; round up with headroom. Anything
# normalized-longer is truncated for storage and the row is marked
# parse_status="rejected" / reject_reason="body_too_long" — it is still
# persisted (so the client doesn't retry it forever) but never parsed.
MAX_BODY_STORAGE_LEN = 1600

_SENDER_KEY_STRIP_RE = re.compile(r"[^A-Z0-9]")
_WHITESPACE_RE = re.compile(r"\s+")


def normalize_body(body: str) -> str:
    """Collapse whitespace so parser regexes see a single-line body."""
    return _WHITESPACE_RE.sub(" ", body).strip()


def normalize_sender_key(sender: str) -> str:
    """Uppercase, alnum-only key used for dedupe + future per-sender rules.

    DLT headers like "AD-HDFCBK" -> "ADHDFCBK"; phone numbers like
    "+91 98765 43210" -> "919876543210". An empty result means the sender
    had no usable identifying characters at all.
    """
    return _SENDER_KEY_STRIP_RE.sub("", sender.upper())


def _hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def compute_fingerprint(
    user_id: UUID, sender_key: str, device_msg_id: str | None, body_hash: str
) -> str:
    """Dedupe key: same user + sender + device message id + body content
    always produces the same fingerprint, so re-syncing the same SMS
    (e.g. after the device replays its SMS provider cursor) is a no-op.
    ``device_msg_id`` is included so two distinct messages with identical
    text (recurring promos) don't collide when the device can tell them
    apart; when it can't (``None``), dedupe falls back to sender+body.
    """
    raw = f"{user_id}:{sender_key}:{device_msg_id or ''}:{body_hash}"
    return _hash(raw)


def _ensure_aware(dt: datetime) -> datetime:
    """Treat naive timestamps as UTC. Clock skew between device and server
    is expected and tolerated: ``received_at`` is informational (and not
    part of the dedupe fingerprint), while ``created_at`` records the
    server's own clock.
    """
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt


class SmsMessageService:
    def __init__(self, session: AsyncSession) -> None:
        self._repo = SmsMessageRepository(session)
        self._session = session

    def _to_read(self, row: SmsMessage) -> SmsMessageRead:
        return SmsMessageRead.model_validate(row)

    async def list_messages(
        self,
        user_id: UUID,
        *,
        limit: int = 50,
        offset: int = 0,
        parse_status: str | None = None,
    ) -> list[SmsMessageRead]:
        rows = await self._repo.list_for_user(
            user_id, limit=limit, offset=offset, parse_status=parse_status
        )
        return [self._to_read(r) for r in rows]

    async def get(self, user_id: UUID, msg_id: UUID) -> SmsMessageRead | None:
        row = await self._repo.get_for_user(user_id, msg_id)
        return self._to_read(row) if row else None

    async def sync_messages(
        self, user_id: UUID, items: list[SmsMessageIngest]
    ) -> SmsSyncResponse:
        results: list[SmsSyncResultItem] = []
        async with self._session.begin():
            for item in items:
                results.append(await self._ingest_one(user_id, item))

        return SmsSyncResponse(
            results=results,
            received=len(results),
            created=sum(1 for r in results if not r.duplicate),
            duplicates=sum(1 for r in results if r.duplicate),
            parsed=sum(1 for r in results if r.parse_status == "parsed"),
            unparsed=sum(1 for r in results if r.parse_status == "unparsed"),
            rejected=sum(1 for r in results if r.parse_status == "rejected"),
        )

    async def _ingest_one(self, user_id: UUID, item: SmsMessageIngest) -> SmsSyncResultItem:
        normalized_body = normalize_body(item.body)
        body_length = len(normalized_body)
        body_hash = _hash(normalized_body)
        sender_key = normalize_sender_key(item.sender) or "INVALID"
        received_at = _ensure_aware(item.received_at)

        fingerprint = compute_fingerprint(user_id, sender_key, item.device_msg_id, body_hash)

        existing = await self._repo.get_by_fingerprint(user_id, fingerprint)
        if existing is not None:
            return SmsSyncResultItem(
                id=existing.id,
                device_msg_id=existing.device_msg_id,
                fingerprint=fingerprint,
                duplicate=True,
                parse_status=existing.parse_status,  # type: ignore[arg-type]
                parser_template=existing.parser_template,
                reject_reason=existing.reject_reason,
            )

        truncated = body_length > MAX_BODY_STORAGE_LEN
        stored_body = normalized_body[:MAX_BODY_STORAGE_LEN] if truncated else normalized_body

        if sender_key == "INVALID":
            parse_status, parser_template, parsed_payload, reject_reason = (
                "rejected",
                None,
                None,
                "invalid_sender",
            )
        elif truncated:
            parse_status, parser_template, parsed_payload, reject_reason = (
                "rejected",
                None,
                None,
                "body_too_long",
            )
        else:
            parsed = parse_sms(normalized_body)
            if parsed is not None:
                parse_status, parser_template, parsed_payload, reject_reason = (
                    "parsed",
                    parsed.template,
                    parsed.to_payload(),
                    None,
                )
            else:
                parse_status, parser_template, parsed_payload, reject_reason = (
                    "unparsed",
                    None,
                    None,
                    None,
                )

        row = SmsMessage(
            user_id=user_id,
            source="sms",
            sender=item.sender,
            sender_key=sender_key,
            device_msg_id=item.device_msg_id,
            received_at=received_at,
            body=stored_body,
            body_length=body_length,
            body_hash=body_hash,
            fingerprint=fingerprint,
            parse_status=parse_status,
            parser_template=parser_template,
            parsed_payload=parsed_payload,
            reject_reason=reject_reason,
        )

        try:
            async with self._session.begin_nested():
                self._session.add(row)
                await self._session.flush()
        except IntegrityError:
            # Concurrent sync inserted the same fingerprint first — replay it.
            existing = await self._repo.get_by_fingerprint(user_id, fingerprint)
            assert existing is not None
            return SmsSyncResultItem(
                id=existing.id,
                device_msg_id=existing.device_msg_id,
                fingerprint=fingerprint,
                duplicate=True,
                parse_status=existing.parse_status,  # type: ignore[arg-type]
                parser_template=existing.parser_template,
                reject_reason=existing.reject_reason,
            )

        return SmsSyncResultItem(
            id=row.id,
            device_msg_id=row.device_msg_id,
            fingerprint=fingerprint,
            duplicate=False,
            parse_status=row.parse_status,  # type: ignore[arg-type]
            parser_template=row.parser_template,
            reject_reason=row.reject_reason,
        )

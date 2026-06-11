"""SQLAlchemy model for the SMS ingest append table.

Raw message bodies are NOT stored; only their SHA-256 fingerprint.
Parsed structured data lives in ``parsed_payload`` (JSONB).
"""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class SmsIngestItem(Base):
    """Append-style ingest row — one per unique (user_id, dedupe_fingerprint) pair.

    Deduplication is enforced by the unique index ``uq_sms_ingest_user_fingerprint``.
    The ``ledger_tx_id`` column is a nullable forward-reference placeholder so the
    categorisation feature can link back to this row without a schema migration.
    """

    __tablename__ = "sms_ingest_items"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # Always 'sms' in v1; reserved for future ingest channels (e-mail, push, etc.)
    source: Mapped[str] = mapped_column(String(32), nullable=False, default="sms")
    # Normalized sender key: upper-case, alphanumeric only, e.g. "SBIINB", "HDFCBK"
    sender_key: Mapped[str] = mapped_column(String(128), nullable=False)
    # SHA-256 hex of the raw message body — body itself is never stored
    raw_body_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    # Opaque identifier from the device's SMS content provider
    device_message_id: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    # Timestamp reported by the device (may differ from ingested_at due to clock skew)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    # Server-assigned ingest timestamp
    ingested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    # Structured extraction result; None when parse_status == 'unparsed'
    parsed_payload: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    # 'parsed' | 'unparsed'  — 'rejected' items are never persisted
    parse_status: Mapped[str] = mapped_column(String(16), nullable=False, default="unparsed")
    # Which template matched, e.g. 'sbi_debit_v1'; None when unparsed
    template_key: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # SHA-256 hex: SHA256(user_id | sender_key | device_message_id [| body_hash])
    # Unique per user — guarantees at-most-once ingest for the same physical message.
    dedupe_fingerprint: Mapped[str] = mapped_column(
        Text, nullable=False
    )
    # Nullable FK placeholder for future ledger linkage — NOT written in v1
    ledger_tx_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("ledger_transactions.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    user = relationship("User", foreign_keys=[user_id])

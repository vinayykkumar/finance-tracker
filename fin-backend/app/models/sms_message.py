import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class SmsMessage(Base):
    """User-authorized SMS ingest row (consent-based, never scraped).

    Append-mostly raw capture of a bank/UPI SMS plus the result of running it
    through the v1 parser templates (see ``app.modules.sms_messages.parsers``).
    Deliberately decoupled from ``ledger_transactions``: this table is the
    ingest boundary only. ``ledger_transaction_id`` is an unused placeholder
    for a follow-on feature that promotes a parsed row into a ledger posting.

    Dedupe: ``(user_id, fingerprint)`` is unique so re-syncing the same SMS
    (e.g. after the device re-reads its SMS provider) is a no-op.

    Cross-dialect note: ``JSON().with_variant(JSONB(), "postgresql")`` and
    ``postgresql.UUID`` both compile cleanly on SQLite, which lets the test
    suite run against an in-memory SQLite DB while production (Postgres)
    still gets native ``uuid``/``jsonb`` columns.
    """

    __tablename__ = "sms_messages"
    __table_args__ = (
        UniqueConstraint("user_id", "fingerprint", name="uq_sms_messages_user_fingerprint"),
        Index("ix_sms_messages_user_received_at", "user_id", "received_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # "sms" today; kept open for future sources (e.g. "email") without a migration.
    source: Mapped[str] = mapped_column(String(16), nullable=False, server_default="sms")

    sender: Mapped[str] = mapped_column(String(64), nullable=False)
    sender_key: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    device_msg_id: Mapped[str | None] = mapped_column(String(128), nullable=True)

    # Client-reported timestamp (subject to device clock skew). created_at below
    # is the server's view of "when we received this sync".
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    body: Mapped[str] = mapped_column(Text, nullable=False)
    body_length: Mapped[int] = mapped_column(Integer, nullable=False)
    body_hash: Mapped[str] = mapped_column(String(64), nullable=False)

    # sha256 of user_id + sender_key + device_msg_id + body_hash. Unique per user.
    fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)

    parse_status: Mapped[str] = mapped_column(String(16), nullable=False, server_default="unparsed")
    parser_template: Mapped[str | None] = mapped_column(String(64), nullable=True)
    parsed_payload: Mapped[dict[str, Any] | None] = mapped_column(
        JSON().with_variant(JSONB(), "postgresql"), nullable=True
    )
    reject_reason: Mapped[str | None] = mapped_column(String(64), nullable=True)

    # Unused placeholder for a follow-on feature (promote a parsed row to a
    # ledger posting). Nothing in this slice writes or reads this column.
    ledger_transaction_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("ledger_transactions.id", ondelete="SET NULL"),
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )

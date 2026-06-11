"""sms_ingest_items — append table for user-authorized bank SMS ingest.

Design notes
------------
* Raw message bodies are NEVER stored.  ``raw_body_hash`` is a SHA-256 hex
  digest of the body; this is sufficient for deduplication.
* ``dedupe_fingerprint`` is the primary dedup key: one row per (user, message).
* ``ledger_tx_id`` is a nullable FK placeholder reserved for the categorisation
  follow-on.  It is NOT written by the ingest service itself.
* ``parse_status`` CHECK constraint keeps the column honest without a separate
  enum type.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0003_sms_ingest"
down_revision: Union[str, None] = "0002_hardening"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "sms_ingest_items",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        # Always 'sms' in v1; reserved for future channels
        sa.Column("source", sa.String(32), nullable=False, server_default="sms"),
        # Normalized sender: uppercase alphanumeric, e.g. 'SBIINB', 'HDFCBK'
        sa.Column("sender_key", sa.String(128), nullable=False),
        # SHA-256 hex of raw message body — raw body never stored
        sa.Column("raw_body_hash", sa.String(64), nullable=False),
        # Opaque device identifier from Android SMS content provider
        sa.Column("device_message_id", sa.String(255), nullable=False, server_default=""),
        # Timestamp as reported by device (may differ from ingested_at due to clock skew)
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        # Server-assigned ingest timestamp
        sa.Column(
            "ingested_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        # Structured extraction — NULL when parse_status='unparsed'
        sa.Column("parsed_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        # 'parsed' | 'unparsed' — rejected items are never persisted
        sa.Column(
            "parse_status",
            sa.String(16),
            nullable=False,
            server_default="unparsed",
        ),
        sa.CheckConstraint("parse_status IN ('parsed', 'unparsed')", name="ck_sms_parse_status"),
        # Which template matched, e.g. 'sbi_debit_v1'; NULL when unparsed
        sa.Column("template_key", sa.String(64), nullable=True),
        # SHA-256 hex fingerprint — unique per user; guarantees at-most-once ingest
        sa.Column("dedupe_fingerprint", sa.Text(), nullable=False),
        # Nullable FK placeholder for future ledger linkage — NOT written in v1
        sa.Column("ledger_tx_id", postgresql.UUID(as_uuid=True), nullable=True),
        # Constraints
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["ledger_tx_id"], ["ledger_transactions.id"], ondelete="SET NULL"
        ),
        sa.UniqueConstraint(
            "user_id", "dedupe_fingerprint", name="uq_sms_ingest_user_fingerprint"
        ),
    )
    op.create_index("ix_sms_ingest_items_user_id", "sms_ingest_items", ["user_id"])
    op.create_index("ix_sms_ingest_items_received_at", "sms_ingest_items", ["received_at"])
    op.create_index("ix_sms_ingest_items_ledger_tx_id", "sms_ingest_items", ["ledger_tx_id"])


def downgrade() -> None:
    op.drop_index("ix_sms_ingest_items_ledger_tx_id", table_name="sms_ingest_items")
    op.drop_index("ix_sms_ingest_items_received_at", table_name="sms_ingest_items")
    op.drop_index("ix_sms_ingest_items_user_id", table_name="sms_ingest_items")
    op.drop_table("sms_ingest_items")

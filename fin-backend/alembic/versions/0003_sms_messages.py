"""SMS ingest table (consent-based, dedupe via fingerprint)."""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0003_sms_messages"
down_revision: Union[str, None] = "0002_hardening"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "sms_messages",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source", sa.String(16), nullable=False, server_default="sms"),
        sa.Column("sender", sa.String(64), nullable=False),
        sa.Column("sender_key", sa.String(64), nullable=False),
        sa.Column("device_msg_id", sa.String(128), nullable=True),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("body_length", sa.Integer(), nullable=False),
        sa.Column("body_hash", sa.String(64), nullable=False),
        sa.Column("fingerprint", sa.String(64), nullable=False),
        sa.Column("parse_status", sa.String(16), nullable=False, server_default="unparsed"),
        sa.Column("parser_template", sa.String(64), nullable=True),
        sa.Column("parsed_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("reject_reason", sa.String(64), nullable=True),
        sa.Column("ledger_transaction_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["ledger_transaction_id"], ["ledger_transactions.id"], ondelete="SET NULL"
        ),
        sa.UniqueConstraint("user_id", "fingerprint", name="uq_sms_messages_user_fingerprint"),
    )
    op.create_index("ix_sms_messages_user_id", "sms_messages", ["user_id"])
    op.create_index("ix_sms_messages_sender_key", "sms_messages", ["sender_key"])
    op.create_index("ix_sms_messages_user_received_at", "sms_messages", ["user_id", "received_at"])
    op.create_index("ix_sms_messages_deleted_at", "sms_messages", ["deleted_at"])


def downgrade() -> None:
    op.drop_index("ix_sms_messages_deleted_at", table_name="sms_messages")
    op.drop_index("ix_sms_messages_user_received_at", table_name="sms_messages")
    op.drop_index("ix_sms_messages_sender_key", table_name="sms_messages")
    op.drop_index("ix_sms_messages_user_id", table_name="sms_messages")
    op.drop_table("sms_messages")

"""Pydantic schemas for the SMS ingest API (v1)."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class SmsItemIn(BaseModel):
    """A single SMS message submitted by the mobile client."""

    # Opaque identifier from Android's SMS content provider (``_id`` column).
    # Used as part of the dedupe fingerprint.  Pass an empty string only if the
    # device cannot supply one — fingerprint falls back to body hash in that case.
    device_message_id: str = Field(default="", max_length=255)
    # Raw sender address as reported by Android (e.g. "+919876543210", "SBIINB")
    sender: str = Field(min_length=1, max_length=64)
    # Full message body — stored as a hash only; 2 000-char cap fits any SMS
    body: str = Field(min_length=1, max_length=2000)
    # Timestamp reported by device; must be timezone-aware or UTC assumed
    received_at: datetime


class BatchIn(BaseModel):
    """Batch of SMS items to ingest."""

    items: list[SmsItemIn] = Field(min_length=0, max_length=100)


# ---------------------------------------------------------------------------
# Response shapes
# ---------------------------------------------------------------------------


class RejectedItem(BaseModel):
    """An item that failed pre-ingest validation."""

    device_message_id: str
    # Stable machine-readable reasons — clients can filter on these
    reason: str  # "body_too_large" | "received_at_too_old" | "received_at_future" | "sender_too_long"


class BatchResult(BaseModel):
    """Summary returned by POST /v1/sms-ingest/batch."""

    accepted: int = Field(description="New rows inserted")
    duplicates: int = Field(description="Items already present (fingerprint match)")
    rejected: list[RejectedItem] = Field(description="Items that failed validation")


class SmsIngestItemRead(BaseModel):
    """Detailed read-back of a stored ingest row."""

    id: UUID
    user_id: UUID
    source: str
    sender_key: str
    device_message_id: str
    received_at: datetime
    ingested_at: datetime
    parse_status: str
    template_key: str | None
    parsed_payload: dict | None
    ledger_tx_id: UUID | None

    model_config = {"from_attributes": True}

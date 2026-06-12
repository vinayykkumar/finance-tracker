from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

ParseStatus = Literal["parsed", "unparsed", "rejected"]

# A sync batch maps to one device "read recent SMS" pass. 50 keeps a single
# request small (well under typical body-size limits) while still letting a
# device catch up after being offline for a while.
MAX_BATCH_SIZE = 50

# Hard cap on a single message's body as accepted over the wire. Real SMS
# (even concatenated, ~10 segments) top out well below this; anything larger
# is almost certainly not a bank SMS and is rejected by FastAPI/pydantic
# before it reaches the service layer.
MAX_INGEST_BODY_LEN = 6000


class SmsMessageIngest(BaseModel):
    """One device SMS as reported by the client."""

    sender: str = Field(min_length=1, max_length=64)
    body: str = Field(min_length=1, max_length=MAX_INGEST_BODY_LEN)
    received_at: datetime
    device_msg_id: str | None = Field(default=None, max_length=128)


class SmsSyncRequest(BaseModel):
    messages: list[SmsMessageIngest] = Field(min_length=1, max_length=MAX_BATCH_SIZE)


class SmsSyncResultItem(BaseModel):
    """Per-message outcome — lets the client reconcile its local list 1:1."""

    id: UUID
    device_msg_id: str | None
    fingerprint: str
    duplicate: bool
    parse_status: ParseStatus
    parser_template: str | None
    reject_reason: str | None


class SmsSyncResponse(BaseModel):
    results: list[SmsSyncResultItem]
    received: int
    created: int
    duplicates: int
    parsed: int
    unparsed: int
    rejected: int


class SmsMessageRead(BaseModel):
    id: UUID
    source: str
    sender: str
    sender_key: str
    device_msg_id: str | None
    received_at: datetime
    body: str
    body_length: int
    parse_status: ParseStatus
    parser_template: str | None
    parsed_payload: dict | None
    reject_reason: str | None
    created_at: datetime

    model_config = {"from_attributes": True}

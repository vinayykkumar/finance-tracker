"""SMS ingest HTTP surface — delegates to ``SmsMessageService``.

Out of scope here: no ledger postings, no account mapping, no ML
categorization. This is the ingest boundary only (see docs/sms-ingest.md).
"""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.session_user import require_session_user_id
from app.db.session import get_db
from app.modules.sms_messages.schemas import (
    ParseStatus,
    SmsMessageRead,
    SmsSyncRequest,
    SmsSyncResponse,
)
from app.modules.sms_messages.service import SmsMessageService
from app.modules.sms_messages.throttle import is_sync_throttled, record_sync_call

router = APIRouter(prefix="/sms-messages", tags=["sms-messages"])


def get_sms_message_service(db: AsyncSession = Depends(get_db)) -> SmsMessageService:
    return SmsMessageService(db)


@router.post("/sync", response_model=SmsSyncResponse, status_code=status.HTTP_200_OK)
async def sync_sms_messages(
    request: Request,
    body: SmsSyncRequest,
    svc: SmsMessageService = Depends(get_sms_message_service),
) -> SmsSyncResponse:
    uid = require_session_user_id(request)
    if is_sync_throttled(uid):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many SMS sync requests. Try again in a minute.",
        )
    record_sync_call(uid)
    return await svc.sync_messages(uid, body.messages)


@router.get("", response_model=list[SmsMessageRead])
async def list_sms_messages(
    request: Request,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    parse_status: ParseStatus | None = Query(default=None),
    svc: SmsMessageService = Depends(get_sms_message_service),
) -> list[SmsMessageRead]:
    uid = require_session_user_id(request)
    return await svc.list_messages(uid, limit=limit, offset=offset, parse_status=parse_status)


@router.get("/{message_id}", response_model=SmsMessageRead)
async def get_sms_message(
    request: Request,
    message_id: UUID,
    svc: SmsMessageService = Depends(get_sms_message_service),
) -> SmsMessageRead:
    uid = require_session_user_id(request)
    row = await svc.get(uid, message_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="SMS message not found")
    return row

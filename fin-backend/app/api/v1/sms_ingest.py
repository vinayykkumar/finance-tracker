"""REST routes for SMS ingest — POST /v1/sms-ingest/batch."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.session_user import require_session_user_id
from app.db.session import get_db
from app.modules.sms_ingest.schemas import BatchIn, BatchResult
from app.modules.sms_ingest.service import MAX_BATCH_SIZE, SmsIngestService

router = APIRouter(prefix="/sms-ingest", tags=["sms-ingest"])


def get_sms_ingest_service(db: AsyncSession = Depends(get_db)) -> SmsIngestService:
    return SmsIngestService(db)


@router.post(
    "/batch",
    response_model=BatchResult,
    status_code=status.HTTP_200_OK,
    summary="Ingest a batch of bank SMS alerts",
    description=(
        "Idempotent upsert by (user_id, dedupe_fingerprint). "
        f"Maximum {MAX_BATCH_SIZE} items per request. "
        "Raw message bodies are hashed server-side and never stored in full. "
        "Requires an active authenticated session."
    ),
)
async def ingest_batch(
    body: BatchIn,
    # Declared as Depends so tests can override without session middleware
    uid: UUID = Depends(require_session_user_id),
    svc: SmsIngestService = Depends(get_sms_ingest_service),
) -> BatchResult:
    if len(body.items) > MAX_BATCH_SIZE:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Batch may contain at most {MAX_BATCH_SIZE} items.",
        )
    return await svc.ingest_batch(uid, body)

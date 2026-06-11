"""Repository for sms_ingest_items — thin async wrapper around SQLAlchemy."""

import uuid
from datetime import datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.sms_ingest import SmsIngestItem


class SmsIngestRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def upsert_by_fingerprint(
        self,
        *,
        user_id: UUID,
        sender_key: str,
        raw_body_hash: str,
        device_message_id: str,
        received_at: datetime,
        parsed_payload: dict | None,
        parse_status: str,
        template_key: str | None,
        dedupe_fingerprint: str,
    ) -> bool:
        """Insert a new row; skip silently if fingerprint already exists.

        Returns ``True`` when a new row was inserted, ``False`` on duplicate.
        Uses PostgreSQL's ``ON CONFLICT DO NOTHING`` so the operation is safe
        under concurrent retries without application-level locking.
        """
        stmt = (
            insert(SmsIngestItem)
            .values(
                id=uuid.uuid4(),
                user_id=user_id,
                source="sms",
                sender_key=sender_key,
                raw_body_hash=raw_body_hash,
                device_message_id=device_message_id,
                received_at=received_at,
                parsed_payload=parsed_payload,
                parse_status=parse_status,
                template_key=template_key,
                dedupe_fingerprint=dedupe_fingerprint,
            )
            .on_conflict_do_nothing(
                index_elements=["user_id", "dedupe_fingerprint"],
            )
        )
        result = await self._session.execute(stmt)
        await self._session.flush()
        return result.rowcount > 0

    async def list_for_user(
        self, user_id: UUID, *, limit: int = 100, offset: int = 0
    ) -> list[SmsIngestItem]:
        """Return ingest rows for a user, most-recently-received first."""
        q = (
            select(SmsIngestItem)
            .where(SmsIngestItem.user_id == user_id)
            .order_by(SmsIngestItem.received_at.desc())
            .limit(limit)
            .offset(offset)
        )
        r = await self._session.execute(q)
        return list(r.scalars().all())

    async def get_for_user(self, user_id: UUID, item_id: UUID) -> SmsIngestItem | None:
        r = await self._session.execute(
            select(SmsIngestItem).where(
                SmsIngestItem.id == item_id,
                SmsIngestItem.user_id == user_id,
            )
        )
        return r.scalar_one_or_none()

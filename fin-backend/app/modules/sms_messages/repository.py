from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.sms_message import SmsMessage


class SmsMessageRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    def _active(self):
        return SmsMessage.deleted_at.is_(None)

    async def get_by_fingerprint(self, user_id: UUID, fingerprint: str) -> SmsMessage | None:
        """Includes soft-deleted rows: a fingerprint is a permanent dedupe key."""
        r = await self._session.execute(
            select(SmsMessage).where(
                SmsMessage.user_id == user_id,
                SmsMessage.fingerprint == fingerprint,
            )
        )
        return r.scalar_one_or_none()

    async def add(self, row: SmsMessage) -> SmsMessage:
        self._session.add(row)
        await self._session.flush()
        await self._session.refresh(row)
        return row

    async def list_for_user(
        self,
        user_id: UUID,
        *,
        limit: int = 50,
        offset: int = 0,
        parse_status: str | None = None,
    ) -> list[SmsMessage]:
        q = select(SmsMessage).where(SmsMessage.user_id == user_id, self._active())
        if parse_status is not None:
            q = q.where(SmsMessage.parse_status == parse_status)
        q = q.order_by(SmsMessage.received_at.desc()).limit(limit).offset(offset)
        r = await self._session.execute(q)
        return list(r.scalars().all())

    async def get_for_user(self, user_id: UUID, msg_id: UUID) -> SmsMessage | None:
        r = await self._session.execute(
            select(SmsMessage).where(
                SmsMessage.id == msg_id,
                SmsMessage.user_id == user_id,
                self._active(),
            )
        )
        return r.scalar_one_or_none()

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit_event import AuditEvent


class AuditRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def append(
        self,
        *,
        user_id: UUID,
        action: str,
        entity_type: str,
        entity_id: UUID,
        payload: dict | None = None,
    ) -> None:
        self._session.add(
            AuditEvent(
                user_id=user_id,
                action=action,
                entity_type=entity_type,
                entity_id=entity_id,
                payload=payload,
            )
        )
        await self._session.flush()

    async def list_for_user(
        self, user_id: UUID, *, entity_types: list[str], limit: int = 1000
    ) -> list[AuditEvent]:
        r = await self._session.execute(
            select(AuditEvent)
            .where(AuditEvent.user_id == user_id, AuditEvent.entity_type.in_(entity_types))
            .order_by(AuditEvent.created_at.asc())
            .limit(limit)
        )
        return list(r.scalars().all())

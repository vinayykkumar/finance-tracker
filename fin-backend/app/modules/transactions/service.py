"""Ledger transaction use-cases — keeps account balance consistent."""

from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.transaction import LedgerTransaction
from app.modules.accounts.repository import AccountRepository
from app.modules.transactions.repository import TransactionRepository
from app.modules.transactions.schemas import TransactionCreate, TransactionRead, TransactionUpdate


class TransactionService:
    def __init__(self, session: AsyncSession) -> None:
        self._repo = TransactionRepository(session)
        self._accounts = AccountRepository(session)
        self._session = session

    def _to_read(self, t: LedgerTransaction) -> TransactionRead:
        return TransactionRead.model_validate(t)

    async def list_transactions(
        self, user_id: UUID, *, account_id: UUID | None = None
    ) -> list[TransactionRead]:
        rows = await self._repo.list_for_user(user_id, account_id=account_id)
        return [self._to_read(x) for x in rows]

    async def get(self, user_id: UUID, tx_id: UUID) -> TransactionRead | None:
        row = await self._repo.get_for_user(user_id, tx_id)
        return self._to_read(row) if row else None

    async def create(self, user_id: UUID, body: TransactionCreate) -> TransactionRead:
        acc = await self._accounts.get_for_user(user_id, body.account_id)
        if acc is None:
            raise ValueError("Account not found")
        row = LedgerTransaction(
            user_id=user_id,
            account_id=body.account_id,
            amount=body.amount,
            description=body.description,
            category_slug=body.category_slug,
            occurred_at=body.occurred_at,
            notes=body.notes,
        )
        acc.balance = Decimal(acc.balance) + body.amount
        acc.updated_at = datetime.now(UTC)
        await self._repo.add(row)
        await self._session.commit()
        await self._session.refresh(row)
        return self._to_read(row)

    async def update(self, user_id: UUID, tx_id: UUID, body: TransactionUpdate) -> TransactionRead | None:
        row = await self._repo.get_for_user(user_id, tx_id)
        if row is None:
            return None
        acc = await self._accounts.get_for_user(user_id, row.account_id)
        if acc is None:
            return None
        data = body.model_dump(exclude_unset=True)
        old_amount = row.amount
        for k, v in data.items():
            setattr(row, k, v)
        if "amount" in data:
            delta = row.amount - old_amount
            acc.balance = Decimal(acc.balance) + delta
        acc.updated_at = datetime.now(UTC)
        await self._session.commit()
        await self._session.refresh(row)
        return self._to_read(row)

    async def delete(self, user_id: UUID, tx_id: UUID) -> bool:
        row = await self._repo.get_for_user(user_id, tx_id)
        if row is None:
            return False
        acc = await self._accounts.get_for_user(user_id, row.account_id)
        if acc is None:
            return False
        acc.balance = Decimal(acc.balance) - row.amount
        acc.updated_at = datetime.now(UTC)
        self._repo.delete(row)
        await self._session.commit()
        return True

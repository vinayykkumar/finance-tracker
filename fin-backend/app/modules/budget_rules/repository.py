from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.budget_rule import BudgetRule
from app.models.transaction import LedgerTransaction
from app.modules.budget_rules.calculation import ZERO
from app.modules.categories.normalization import normalize_category_slug


class BudgetRuleRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_for_user(
        self, user_id: UUID, *, category_slug: str | None = None
    ) -> list[BudgetRule]:
        q = select(BudgetRule).where(BudgetRule.user_id == user_id)
        if category_slug is not None:
            q = q.where(BudgetRule.category_slug == category_slug)
        q = q.order_by(BudgetRule.category_slug, BudgetRule.effective_from)
        r = await self._session.execute(q)
        return list(r.scalars().all())

    async def get_for_user(self, user_id: UUID, rule_id: UUID) -> BudgetRule | None:
        r = await self._session.execute(
            select(BudgetRule).where(BudgetRule.id == rule_id, BudgetRule.user_id == user_id)
        )
        return r.scalar_one_or_none()

    async def find_composite(
        self, user_id: UUID, category_slug: str, effective_from: date
    ) -> BudgetRule | None:
        r = await self._session.execute(
            select(BudgetRule).where(
                BudgetRule.user_id == user_id,
                BudgetRule.category_slug == category_slug,
                BudgetRule.effective_from == effective_from,
            )
        )
        return r.scalar_one_or_none()

    async def add(self, row: BudgetRule) -> BudgetRule:
        self._session.add(row)
        await self._session.flush()
        await self._session.refresh(row)
        return row

    async def delete(self, row: BudgetRule) -> None:
        await self._session.delete(row)

    async def spend_by_category_and_month(
        self, user_id: UUID, range_start: datetime, range_end: datetime
    ) -> dict[tuple[str, date], Decimal]:
        """Sum non-deleted transaction amounts for ``user_id`` whose
        ``occurred_at`` falls in ``[range_start, range_end)``, grouped by
        (normalized category_slug, UTC calendar-month start).

        Spend is sign-flipped (positive = money spent), so net refunds in a
        category reduce its total naturally. Bucketing and normalization are
        done in Python — deliberately, so behavior doesn't depend on the
        database's session timezone (Postgres ``date_trunc`` on a
        ``timestamptz`` is timezone-dependent) and is identical across
        Postgres/SQLite in tests.
        """
        q = select(
            LedgerTransaction.category_slug,
            LedgerTransaction.amount,
            LedgerTransaction.occurred_at,
        ).where(
            LedgerTransaction.user_id == user_id,
            LedgerTransaction.deleted_at.is_(None),
            LedgerTransaction.occurred_at >= range_start,
            LedgerTransaction.occurred_at < range_end,
        )
        rows = (await self._session.execute(q)).all()

        totals: dict[tuple[str, date], Decimal] = {}
        for category_slug, amount, occurred_at in rows:
            try:
                normalized = normalize_category_slug(category_slug)
            except ValueError:
                # Defensive: pre-existing rows that normalize to empty (e.g. only
                # punctuation) keep their raw value rather than being dropped.
                normalized = category_slug
            period = date(occurred_at.year, occurred_at.month, 1)
            key = (normalized, period)
            totals[key] = totals.get(key, ZERO) - Decimal(amount)
        return totals

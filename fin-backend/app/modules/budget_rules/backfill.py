"""Backfill ``budget_rules`` from the legacy ``budget_lines`` table.

This is the reference implementation of the mapping performed by Alembic
migration ``0003_budget_rules``'s data backfill (written there as a single
``INSERT ... SELECT ... ON CONFLICT DO NOTHING`` for the sync/Postgres
migration context). It's exercised in tests to pin down the mapping, and can
also be run directly for an out-of-band/manual backfill:

    poetry run python -m app.modules.budget_rules.backfill

Mapping, per existing ``budget_lines`` row:

* ``effective_from`` = the first day of that row's ``(year, month)``
* ``cap_amount``     = ``limit_amount``
* ``rollover_mode``  = ``"none"`` (reproduces today's fixed-cap, no-rollover behavior)
* ``rollover_cap_amount`` = ``None``
* ``rule_type``      = ``"category_cap"``

Idempotent: skips any ``(user_id, category_slug, effective_from)`` that
already has a ``budget_rules`` row.
"""

import asyncio

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.budget import BudgetLine
from app.models.budget_rule import BudgetRule
from app.modules.budget_rules.calculation import period_start_date


async def backfill_from_budget_lines(session: AsyncSession) -> int:
    """Insert one ``budget_rules`` row per ``budget_lines`` row not already
    represented. Returns the number of rows inserted."""
    rows = (await session.execute(select(BudgetLine))).scalars().all()
    inserted = 0
    for line in rows:
        effective_from = period_start_date(line.year, line.month)
        existing = await session.execute(
            select(BudgetRule).where(
                BudgetRule.user_id == line.user_id,
                BudgetRule.category_slug == line.category_slug,
                BudgetRule.effective_from == effective_from,
            )
        )
        if existing.scalar_one_or_none() is not None:
            continue
        session.add(
            BudgetRule(
                user_id=line.user_id,
                category_slug=line.category_slug,
                rule_type="category_cap",
                cap_amount=line.limit_amount,
                currency=line.currency,
                rollover_mode="none",
                rollover_cap_amount=None,
                effective_from=effective_from,
            )
        )
        inserted += 1
    await session.flush()
    return inserted


async def _main() -> None:  # pragma: no cover - manual entry point
    from app.db.session import AsyncSessionLocal

    async with AsyncSessionLocal() as session:
        count = await backfill_from_budget_lines(session)
        await session.commit()
        print(f"Inserted {count} budget_rules row(s) from budget_lines.")


if __name__ == "__main__":  # pragma: no cover
    asyncio.run(_main())

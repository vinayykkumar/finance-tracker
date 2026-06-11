"""Integration tests: persistence + recalculation-on-read for the budget
rules engine.

These exercise BudgetRuleService and TransactionService together against a
real (SQLite) async session, covering the scenarios from the edge-case list:
back-dating across months, recategorization, retroactive rules, rule
deletion, soft-delete, unbudgeted spend, timezone boundaries, legacy
unnormalized category data, and the budget_lines -> budget_rules backfill.
"""

from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from app.models.budget import BudgetLine
from app.models.budget_rule import BudgetRule
from app.modules.budget_rules.backfill import backfill_from_budget_lines
from app.modules.budget_rules.schemas import BudgetRuleCreate, BudgetRuleUpdate
from app.modules.budget_rules.service import (
    BudgetRuleService,
    CurrencyMismatchError,
    RolloverConsistencyError,
)
from app.modules.transactions.schemas import TransactionCreate, TransactionUpdate
from app.modules.transactions.service import TransactionService
from sqlalchemy import select

D = Decimal


def utc(y, m, d, hour=12, minute=0, second=0, micro=0):
    return datetime(y, m, d, hour, minute, second, micro, tzinfo=UTC)


# ---------------------------------------------------------------------------
# Basic cap + rollover via the summary endpoint's service
# ---------------------------------------------------------------------------


async def test_summary_basic_cap_no_rollover(db_session, user, account):
    rules = BudgetRuleService(db_session)
    txs = TransactionService(db_session)

    await rules.upsert(
        user.id,
        BudgetRuleCreate(
            category_slug="groceries",
            cap_amount=D("10000"),
            currency="INR",
            rollover_mode="none",
            effective_from=date(2026, 6, 1),
        ),
    )
    await txs.create(
        user.id,
        TransactionCreate(
            account_id=account.id,
            amount=D("-4000"),
            category_slug="groceries",
            occurred_at=utc(2026, 6, 10),
        ),
    )

    summary = await rules.summary(user.id, 2026, 6)
    cat = next(c for c in summary.categories if c.category_slug == "groceries")
    assert cat.cap_amount == D("10000")
    assert cat.actual_spend == D("4000")
    assert cat.available == D("10000")
    assert cat.remaining == D("6000")
    assert cat.rollover_out == D("0")
    assert cat.over_budget is False


async def test_unbudgeted_spend_for_category_without_rule(db_session, user, account):
    rules = BudgetRuleService(db_session)
    txs = TransactionService(db_session)

    await txs.create(
        user.id,
        TransactionCreate(
            account_id=account.id,
            amount=D("-850"),
            category_slug="pet-supplies",
            occurred_at=utc(2026, 6, 5),
        ),
    )

    summary = await rules.summary(user.id, 2026, 6)
    assert summary.categories == []
    assert summary.unbudgeted.actual_spend == D("850")
    assert summary.unbudgeted.categories[0].category_slug == "pet-supplies"


# ---------------------------------------------------------------------------
# Back-dating across months recalculates both periods on next read
# ---------------------------------------------------------------------------


async def test_backdated_transaction_recalculates_both_periods(db_session, user, account):
    rules = BudgetRuleService(db_session)
    txs = TransactionService(db_session)

    await rules.upsert(
        user.id,
        BudgetRuleCreate(
            category_slug="groceries",
            cap_amount=D("10000"),
            currency="INR",
            rollover_mode="full",
            effective_from=date(2026, 6, 1),
        ),
    )
    june_tx = await txs.create(
        user.id,
        TransactionCreate(
            account_id=account.id,
            amount=D("-4000"),
            category_slug="groceries",
            occurred_at=utc(2026, 6, 10),
        ),
    )
    july_tx = await txs.create(
        user.id,
        TransactionCreate(
            account_id=account.id,
            amount=D("-9000"),
            category_slug="groceries",
            occurred_at=utc(2026, 7, 20),
        ),
    )

    before_june = await rules.summary(user.id, 2026, 6)
    before_july = await rules.summary(user.id, 2026, 7)
    june_cat = before_june.categories[0]
    july_cat = before_july.categories[0]
    assert june_cat.actual_spend == D("4000")
    assert june_cat.rollover_out == D("6000")
    assert july_cat.rollover_in == D("6000")
    assert july_cat.available == D("16000")
    assert july_cat.remaining == D("7000")

    # Back-date the July transaction by 1500 worth of spend into June.
    await txs.update(
        user.id,
        july_tx.id,
        TransactionUpdate(amount=D("-7500"), occurred_at=utc(2026, 7, 20)),
    )
    await txs.update(
        user.id,
        june_tx.id,
        TransactionUpdate(amount=D("-5500")),
    )

    after_june = await rules.summary(user.id, 2026, 6)
    after_july = await rules.summary(user.id, 2026, 7)
    june_cat = after_june.categories[0]
    july_cat = after_july.categories[0]
    assert june_cat.actual_spend == D("5500")
    assert june_cat.rollover_out == D("4500")
    assert july_cat.rollover_in == D("4500")
    assert july_cat.available == D("14500")
    assert july_cat.actual_spend == D("7500")
    assert july_cat.remaining == D("7000")


# ---------------------------------------------------------------------------
# Recategorization moves spend between categories' totals
# ---------------------------------------------------------------------------


async def test_recategorization_moves_spend_between_categories(db_session, user, account):
    rules = BudgetRuleService(db_session)
    txs = TransactionService(db_session)

    for slug in ("groceries", "dining"):
        await rules.upsert(
            user.id,
            BudgetRuleCreate(
                category_slug=slug,
                cap_amount=D("10000"),
                currency="INR",
                rollover_mode="none",
                effective_from=date(2026, 6, 1),
            ),
        )

    tx = await txs.create(
        user.id,
        TransactionCreate(
            account_id=account.id,
            amount=D("-1200"),
            category_slug="groceries",
            occurred_at=utc(2026, 6, 8),
        ),
    )

    before = await rules.summary(user.id, 2026, 6)
    groceries_before = next(c for c in before.categories if c.category_slug == "groceries")
    dining_before = next(c for c in before.categories if c.category_slug == "dining")
    assert groceries_before.actual_spend == D("1200")
    assert dining_before.actual_spend == D("0")

    await txs.update(user.id, tx.id, TransactionUpdate(category_slug="dining"))

    after = await rules.summary(user.id, 2026, 6)
    groceries_after = next(c for c in after.categories if c.category_slug == "groceries")
    dining_after = next(c for c in after.categories if c.category_slug == "dining")
    assert groceries_after.actual_spend == D("0")
    assert dining_after.actual_spend == D("1200")


async def test_recategorization_to_category_with_no_rule_becomes_unbudgeted(db_session, user, account):
    rules = BudgetRuleService(db_session)
    txs = TransactionService(db_session)

    await rules.upsert(
        user.id,
        BudgetRuleCreate(
            category_slug="groceries",
            cap_amount=D("10000"),
            currency="INR",
            rollover_mode="none",
            effective_from=date(2026, 6, 1),
        ),
    )
    tx = await txs.create(
        user.id,
        TransactionCreate(
            account_id=account.id,
            amount=D("-1200"),
            category_slug="groceries",
            occurred_at=utc(2026, 6, 8),
        ),
    )

    await txs.update(user.id, tx.id, TransactionUpdate(category_slug="hobbies"))

    summary = await rules.summary(user.id, 2026, 6)
    groceries = next(c for c in summary.categories if c.category_slug == "groceries")
    assert groceries.actual_spend == D("0")
    assert summary.unbudgeted.actual_spend == D("1200")
    assert summary.unbudgeted.categories[0].category_slug == "hobbies"


# ---------------------------------------------------------------------------
# Soft-deleted transactions excluded from totals
# ---------------------------------------------------------------------------


async def test_soft_deleted_transaction_excluded_from_summary(db_session, user, account):
    rules = BudgetRuleService(db_session)
    txs = TransactionService(db_session)

    await rules.upsert(
        user.id,
        BudgetRuleCreate(
            category_slug="groceries",
            cap_amount=D("10000"),
            currency="INR",
            rollover_mode="full",
            effective_from=date(2026, 6, 1),
        ),
    )
    tx = await txs.create(
        user.id,
        TransactionCreate(
            account_id=account.id,
            amount=D("-4000"),
            category_slug="groceries",
            occurred_at=utc(2026, 6, 10),
        ),
    )

    before = await rules.summary(user.id, 2026, 6)
    assert before.categories[0].actual_spend == D("4000")

    await txs.delete(user.id, tx.id)

    after = await rules.summary(user.id, 2026, 6)
    cat = after.categories[0]
    assert cat.actual_spend == D("0")
    assert cat.rollover_out == D("10000")  # full cap now rolls forward


# ---------------------------------------------------------------------------
# Retroactive rules added after spend already exists
# ---------------------------------------------------------------------------


async def test_retroactive_rule_added_after_spend_exists(db_session, user, account):
    rules = BudgetRuleService(db_session)
    txs = TransactionService(db_session)

    await txs.create(
        user.id,
        TransactionCreate(
            account_id=account.id,
            amount=D("-3000"),
            category_slug="groceries",
            occurred_at=utc(2026, 5, 15),
        ),
    )
    await txs.create(
        user.id,
        TransactionCreate(
            account_id=account.id,
            amount=D("-4000"),
            category_slug="groceries",
            occurred_at=utc(2026, 6, 15),
        ),
    )

    before_may = await rules.summary(user.id, 2026, 5)
    assert before_may.unbudgeted.actual_spend == D("3000")

    # Retroactively create a rule effective from May.
    await rules.upsert(
        user.id,
        BudgetRuleCreate(
            category_slug="groceries",
            cap_amount=D("5000"),
            currency="INR",
            rollover_mode="full",
            effective_from=date(2026, 5, 1),
        ),
    )

    after_may = await rules.summary(user.id, 2026, 5)
    may_cat = next(c for c in after_may.categories if c.category_slug == "groceries")
    assert may_cat.is_unbudgeted is False
    assert may_cat.available == D("5000")
    assert may_cat.rollover_out == D("2000")

    after_june = await rules.summary(user.id, 2026, 6)
    june_cat = next(c for c in after_june.categories if c.category_slug == "groceries")
    assert june_cat.rollover_in == D("2000")
    assert june_cat.available == D("7000")


# ---------------------------------------------------------------------------
# Deleting the earliest rule version shifts the rollover chain start
# ---------------------------------------------------------------------------


async def test_deleting_earliest_rule_resets_chain_start(db_session, user, account):
    rules = BudgetRuleService(db_session)
    txs = TransactionService(db_session)

    jan_rule = await rules.upsert(
        user.id,
        BudgetRuleCreate(
            category_slug="groceries",
            cap_amount=D("10000"),
            currency="INR",
            rollover_mode="full",
            effective_from=date(2026, 1, 1),
        ),
    )
    await rules.upsert(
        user.id,
        BudgetRuleCreate(
            category_slug="groceries",
            cap_amount=D("20000"),
            currency="INR",
            rollover_mode="full",
            effective_from=date(2026, 4, 1),
        ),
    )

    for month in (1, 2, 3, 4):
        await txs.create(
            user.id,
            TransactionCreate(
                account_id=account.id,
                amount=D("-8000"),
                category_slug="groceries",
                occurred_at=utc(2026, month, 15),
            ),
        )

    before = await rules.summary(user.id, 2026, 4)
    apr_cat = next(c for c in before.categories if c.category_slug == "groceries")
    assert apr_cat.rollover_in == D("6000")

    await rules.delete(user.id, jan_rule.id)

    after = await rules.summary(user.id, 2026, 4)
    apr_cat = next(c for c in after.categories if c.category_slug == "groceries")
    assert apr_cat.rollover_in == D("0")
    assert apr_cat.available == D("20000")

    jan_after = await rules.summary(user.id, 2026, 1)
    assert jan_after.unbudgeted.actual_spend == D("8000")


# ---------------------------------------------------------------------------
# Validation: currency continuity and rollover consistency
# ---------------------------------------------------------------------------


async def test_upsert_same_composite_key_updates_existing_row(db_session, user):
    rules = BudgetRuleService(db_session)

    first = await rules.upsert(
        user.id,
        BudgetRuleCreate(
            category_slug="groceries",
            cap_amount=D("10000"),
            currency="INR",
            rollover_mode="none",
            effective_from=date(2026, 6, 1),
        ),
    )
    second = await rules.upsert(
        user.id,
        BudgetRuleCreate(
            category_slug="groceries",
            cap_amount=D("12000"),
            currency="INR",
            rollover_mode="full",
            effective_from=date(2026, 6, 1),
        ),
    )

    assert first.id == second.id
    versions = await rules.list_versions(user.id, "groceries")
    assert len(versions) == 1
    assert versions[0].cap_amount == D("12000")
    assert versions[0].rollover_mode == "full"


async def test_currency_mismatch_between_rule_versions_rejected(db_session, user):
    rules = BudgetRuleService(db_session)

    await rules.upsert(
        user.id,
        BudgetRuleCreate(
            category_slug="groceries",
            cap_amount=D("10000"),
            currency="INR",
            rollover_mode="none",
            effective_from=date(2026, 1, 1),
        ),
    )

    with pytest.raises(CurrencyMismatchError):
        await rules.upsert(
            user.id,
            BudgetRuleCreate(
                category_slug="groceries",
                cap_amount=D("100"),
                currency="USD",
                rollover_mode="none",
                effective_from=date(2026, 6, 1),
            ),
        )


async def test_update_rollover_mode_to_capped_without_cap_amount_rejected(db_session, user):
    rules = BudgetRuleService(db_session)

    rule = await rules.upsert(
        user.id,
        BudgetRuleCreate(
            category_slug="groceries",
            cap_amount=D("10000"),
            currency="INR",
            rollover_mode="none",
            effective_from=date(2026, 6, 1),
        ),
    )

    with pytest.raises(RolloverConsistencyError):
        await rules.update(user.id, rule.id, BudgetRuleUpdate(rollover_mode="capped"))


async def test_update_switching_away_from_capped_clears_rollover_cap(db_session, user):
    rules = BudgetRuleService(db_session)

    rule = await rules.upsert(
        user.id,
        BudgetRuleCreate(
            category_slug="groceries",
            cap_amount=D("10000"),
            currency="INR",
            rollover_mode="capped",
            rollover_cap_amount=D("2000"),
            effective_from=date(2026, 6, 1),
        ),
    )

    updated = await rules.update(user.id, rule.id, BudgetRuleUpdate(rollover_mode="full"))
    assert updated.rollover_mode == "full"
    assert updated.rollover_cap_amount is None


# ---------------------------------------------------------------------------
# /explain — audit trail for "why did this number change"
# ---------------------------------------------------------------------------


async def test_explain_surfaces_recategorization_event(db_session, user, account):
    rules = BudgetRuleService(db_session)
    txs = TransactionService(db_session)

    for slug in ("groceries", "dining"):
        await rules.upsert(
            user.id,
            BudgetRuleCreate(
                category_slug=slug,
                cap_amount=D("10000"),
                currency="INR",
                rollover_mode="none",
                effective_from=date(2026, 6, 1),
            ),
        )

    tx = await txs.create(
        user.id,
        TransactionCreate(
            account_id=account.id,
            amount=D("-1200"),
            category_slug="groceries",
            occurred_at=utc(2026, 6, 8),
        ),
    )
    await txs.update(user.id, tx.id, TransactionUpdate(category_slug="dining"))

    groceries_explain = await rules.explain(user.id, 2026, 6, "groceries")
    dining_explain = await rules.explain(user.id, 2026, 6, "dining")

    assert any("dining" in e.description for e in groceries_explain.events)
    assert any("groceries" in e.description for e in dining_explain.events)


async def test_explain_surfaces_retroactive_rule_creation(db_session, user, account):
    rules = BudgetRuleService(db_session)
    txs = TransactionService(db_session)

    await txs.create(
        user.id,
        TransactionCreate(
            account_id=account.id,
            amount=D("-3000"),
            category_slug="groceries",
            occurred_at=utc(2026, 5, 15),
        ),
    )
    await rules.upsert(
        user.id,
        BudgetRuleCreate(
            category_slug="groceries",
            cap_amount=D("5000"),
            currency="INR",
            rollover_mode="full",
            effective_from=date(2026, 5, 1),
        ),
    )

    explain = await rules.explain(user.id, 2026, 5, "groceries")
    assert any(e.type == "budget_rule.create" for e in explain.events)
    assert explain.current.is_unbudgeted is False
    assert explain.current.available == D("5000")


# ---------------------------------------------------------------------------
# Timezone / period boundaries
# ---------------------------------------------------------------------------


async def test_transaction_at_exact_utc_month_boundary_belongs_to_next_month(db_session, user, account):
    rules = BudgetRuleService(db_session)
    txs = TransactionService(db_session)

    await rules.upsert(
        user.id,
        BudgetRuleCreate(
            category_slug="groceries",
            cap_amount=D("10000"),
            currency="INR",
            rollover_mode="none",
            effective_from=date(2026, 6, 1),
        ),
    )
    # Exactly midnight UTC on July 1st -> belongs to July, not June.
    await txs.create(
        user.id,
        TransactionCreate(
            account_id=account.id,
            amount=D("-500"),
            category_slug="groceries",
            occurred_at=datetime(2026, 7, 1, 0, 0, 0, tzinfo=UTC),
        ),
    )

    june = await rules.summary(user.id, 2026, 6)
    assert june.categories[0].actual_spend == D("0")

    july = await rules.summary(user.id, 2026, 7)
    july_cat = next(c for c in july.categories if c.category_slug == "groceries")
    assert july_cat.actual_spend == D("500")


# ---------------------------------------------------------------------------
# Legacy / un-normalized category_slug data
# ---------------------------------------------------------------------------


async def test_legacy_unnormalized_category_slug_matches_normalized_rule(db_session, user, account):
    """A pre-existing transaction stored with an un-normalized category_slug
    (e.g. written before normalization was enforced) still matches a rule
    created with the normalized form, thanks to defensive normalization in
    the aggregation query."""
    from tests.conftest import make_transaction

    rules = BudgetRuleService(db_session)

    await make_transaction(
        db_session,
        user_id=user.id,
        account_id=account.id,
        amount="-1200",
        category_slug="  Food  ",  # legacy, un-normalized
        occurred_at=utc(2026, 6, 8),
    )

    await rules.upsert(
        user.id,
        BudgetRuleCreate(
            category_slug="Food",  # normalizes to "food"
            cap_amount=D("10000"),
            currency="INR",
            rollover_mode="none",
            effective_from=date(2026, 6, 1),
        ),
    )

    summary = await rules.summary(user.id, 2026, 6)
    food = next(c for c in summary.categories if c.category_slug == "food")
    assert food.actual_spend == D("1200")
    assert summary.unbudgeted.categories == []


# ---------------------------------------------------------------------------
# Migration backfill: budget_lines -> budget_rules
# ---------------------------------------------------------------------------


async def test_backfill_from_budget_lines_is_idempotent_and_preserves_no_rollover(db_session, user, account):
    rules = BudgetRuleService(db_session)
    txs = TransactionService(db_session)

    line = BudgetLine(
        user_id=user.id,
        category_slug="groceries",
        year=2026,
        month=6,
        limit_amount=D("15000"),
        currency="INR",
    )
    db_session.add(line)
    await db_session.commit()

    await txs.create(
        user.id,
        TransactionCreate(
            account_id=account.id,
            amount=D("-5000"),
            category_slug="groceries",
            occurred_at=utc(2026, 6, 10),
        ),
    )

    inserted = await backfill_from_budget_lines(db_session)
    assert inserted == 1

    # Idempotent: running again inserts nothing more.
    inserted_again = await backfill_from_budget_lines(db_session)
    assert inserted_again == 0

    rows = (
        await db_session.execute(select(BudgetRule).where(BudgetRule.user_id == user.id))
    ).scalars().all()
    assert len(rows) == 1
    row = rows[0]
    assert row.category_slug == "groceries"
    assert row.effective_from == date(2026, 6, 1)
    assert row.cap_amount == D("15000")
    assert row.rollover_mode == "none"
    assert row.rollover_cap_amount is None

    summary = await rules.summary(user.id, 2026, 6)
    cat = next(c for c in summary.categories if c.category_slug == "groceries")
    assert cat.cap_amount == D("15000")
    assert cat.actual_spend == D("5000")
    assert cat.rollover_out == D("0")  # rollover_mode='none' preserves old behavior

"""Unit tests for the plain-language "why" copy (no DB).

These pin down the exact wording for each scenario the budget UI needs to
explain — rollover source, caps, over-budget, unbudgeted, and the audit-log
history for transaction/rule changes — and check that every number quoted in
the copy matches the structured input it was derived from.
"""

from datetime import UTC, datetime
from decimal import Decimal

from app.modules.budget_rules.explanations import (
    describe_budget_rule_event,
    describe_transaction_event,
    format_date,
    format_money,
    format_period,
    summary_lines,
)
from app.modules.budget_rules.schemas import CategoryPeriodSummary

D = Decimal


def period(year, month, day=1, hour=12):
    return datetime(year, month, day, hour, tzinfo=UTC)


def category(**overrides) -> CategoryPeriodSummary:
    base = dict(
        category_slug="groceries",
        is_unbudgeted=False,
        rule_id=None,
        rule_effective_from=None,
        cap_amount=D("10000"),
        currency="INR",
        rollover_mode="none",
        rollover_in=D("0"),
        available=D("10000"),
        actual_spend=D("4000"),
        rollover_out=D("0"),
        remaining=D("6000"),
        over_budget=False,
    )
    base.update(overrides)
    return CategoryPeriodSummary(**base)


# ---------------------------------------------------------------------------
# format_* helpers
# ---------------------------------------------------------------------------


def test_format_money():
    assert format_money(D("1200"), "INR") == "1,200.00 INR"
    assert format_money(D("0"), None) == "0.00 INR"


def test_format_period():
    assert format_period("2026-05-01") == "May 2026"


def test_format_date():
    assert format_date("2026-07-20T12:00:00+00:00") == "20 Jul 2026"


# ---------------------------------------------------------------------------
# summary_lines
# ---------------------------------------------------------------------------


def test_summary_lines_no_rollover_no_overspend():
    cat = category(rollover_mode="none", rollover_in=D("0"), rollover_out=D("0"))
    lines = summary_lines(cat, "groceries")
    assert lines == [
        "Your cap for 'groceries' this month is 10,000.00 INR.",
        "You've spent 4,000.00 INR, leaving 6,000.00 INR.",
    ]


def test_summary_lines_with_rollover_in():
    cat = category(
        rollover_mode="full",
        rollover_in=D("6200"),
        available=D("16200"),
        actual_spend=D("14000"),
        remaining=D("2200"),
        rollover_out=D("2200"),
    )
    lines = summary_lines(cat, "groceries")
    assert lines == [
        "Your cap for 'groceries' this month is 10,000.00 INR.",
        "6,200.00 INR rolled over from last month because you had budget left over.",
        "That makes 16,200.00 INR available this month.",
        "You've spent 14,000.00 INR, leaving 2,200.00 INR.",
        "At today's numbers, 2,200.00 INR would roll over into next month.",
    ]


def test_summary_lines_over_budget():
    cat = category(
        rollover_mode="none",
        cap_amount=D("10000"),
        available=D("10000"),
        actual_spend=D("15000"),
        remaining=D("-5000"),
        rollover_out=D("0"),
        over_budget=True,
    )
    lines = summary_lines(cat, "groceries")
    assert lines == [
        "Your cap for 'groceries' this month is 10,000.00 INR.",
        "You've spent 15,000.00 INR, which is 5,000.00 INR over what's available.",
    ]


def test_summary_lines_rollover_mode_none_does_not_mention_future_rollover():
    cat = category(rollover_mode="none", actual_spend=D("0"), remaining=D("10000"))
    lines = summary_lines(cat, "groceries")
    assert not any("roll over into next month" in line for line in lines)


def test_summary_lines_unbudgeted_with_no_spend():
    cat = category(
        is_unbudgeted=True,
        cap_amount=None,
        currency=None,
        rollover_mode=None,
        rollover_in=None,
        available=None,
        actual_spend=D("0"),
        rollover_out=None,
        remaining=None,
        over_budget=False,
    )
    lines = summary_lines(cat, "pet-supplies")
    assert lines == [
        "No budget rule covers 'pet-supplies' this month, so this spend isn't checked against a cap."
    ]


def test_summary_lines_unbudgeted_with_spend():
    cat = category(
        is_unbudgeted=True,
        cap_amount=None,
        currency=None,
        rollover_mode=None,
        rollover_in=None,
        available=None,
        actual_spend=D("850"),
        rollover_out=None,
        remaining=None,
        over_budget=False,
    )
    lines = summary_lines(cat, "pet-supplies")
    assert lines[1] == "You've spent 850.00 INR here so far this month."


# ---------------------------------------------------------------------------
# describe_transaction_event
# ---------------------------------------------------------------------------


def test_describe_transaction_create_expense():
    payload = {
        "account_id": "acc",
        "amount": "-1200.0000",
        "description": "",
        "category_slug": "groceries",
        "occurred_at": "2026-06-08T12:00:00+00:00",
    }
    desc = describe_transaction_event(
        action="transaction.create",
        payload=payload,
        category_slug="groceries",
        currency="INR",
        period_start=period(2026, 6, 1, 0),
        period_end=period(2026, 7, 1, 0),
    )
    assert desc == "On 08 Jun 2026, an expense of 1,200.00 INR was added to 'groceries'."


def test_describe_transaction_create_credit():
    payload = {
        "amount": "500.0000",
        "category_slug": "groceries",
        "occurred_at": "2026-06-08T12:00:00+00:00",
    }
    desc = describe_transaction_event(
        action="transaction.create",
        payload=payload,
        category_slug="groceries",
        currency="INR",
        period_start=period(2026, 6, 1, 0),
        period_end=period(2026, 7, 1, 0),
    )
    assert desc == "On 08 Jun 2026, a credit of 500.00 INR was added to 'groceries'."


def test_describe_transaction_irrelevant_returns_none():
    payload = {
        "amount": "-1200.0000",
        "category_slug": "dining",
        "occurred_at": "2026-06-08T12:00:00+00:00",
    }
    desc = describe_transaction_event(
        action="transaction.create",
        payload=payload,
        category_slug="groceries",
        currency="INR",
        period_start=period(2026, 6, 1, 0),
        period_end=period(2026, 7, 1, 0),
    )
    assert desc is None


def test_describe_transaction_update_recategorized_out():
    payload = {
        "fields": ["category_slug"],
        "category_slug": "dining",
        "occurred_at": "2026-06-08T12:00:00+00:00",
        "category_slug_old": "groceries",
    }
    desc = describe_transaction_event(
        action="transaction.update",
        payload=payload,
        category_slug="groceries",
        currency="INR",
        period_start=period(2026, 6, 1, 0),
        period_end=period(2026, 7, 1, 0),
    )
    assert desc == "A transaction was updated: it was moved from 'groceries' to 'dining'."


def test_describe_transaction_update_recategorized_in():
    payload = {
        "fields": ["category_slug"],
        "category_slug": "groceries",
        "occurred_at": "2026-06-08T12:00:00+00:00",
        "category_slug_old": "dining",
    }
    desc = describe_transaction_event(
        action="transaction.update",
        payload=payload,
        category_slug="groceries",
        currency="INR",
        period_start=period(2026, 6, 1, 0),
        period_end=period(2026, 7, 1, 0),
    )
    assert desc == "A transaction was updated: it was moved into 'groceries' from 'dining'."


def test_describe_transaction_update_amount_and_date_change():
    payload = {
        "fields": ["amount", "occurred_at"],
        "category_slug": "groceries",
        "occurred_at": "2026-06-10T12:00:00+00:00",
        "amount": {"old": "-9000.0000", "new": "-7500.0000"},
        "occurred_at_old": "2026-07-20T12:00:00+00:00",
    }
    desc = describe_transaction_event(
        action="transaction.update",
        payload=payload,
        category_slug="groceries",
        currency="INR",
        period_start=period(2026, 6, 1, 0),
        period_end=period(2026, 7, 1, 0),
    )
    assert desc == (
        "A transaction was updated: its amount changed from 9,000.00 INR to 7,500.00 INR; "
        "its date changed from 20 Jul 2026 to 10 Jun 2026."
    )


# ---------------------------------------------------------------------------
# describe_budget_rule_event
# ---------------------------------------------------------------------------


def test_describe_budget_rule_create_full_rollover():
    payload = {
        "category_slug": "groceries",
        "rule_type": "category_cap",
        "effective_from": "2026-05-01",
        "cap_amount": "5000.0000",
        "currency": "INR",
        "rollover_mode": "full",
        "rollover_cap_amount": None,
    }
    desc = describe_budget_rule_event(
        action="budget_rule.create",
        payload=payload,
        category_slug="groceries",
        period_start=period(2026, 5, 1, 0),
    )
    assert desc == (
        "A budget rule for 'groceries' took effect from May 2026: "
        "a 5,000.00 INR cap, with any unused amount carrying over to the next month."
    )


def test_describe_budget_rule_create_capped_rollover():
    payload = {
        "category_slug": "groceries",
        "effective_from": "2026-06-01",
        "cap_amount": "10000.0000",
        "currency": "INR",
        "rollover_mode": "capped",
        "rollover_cap_amount": "2000.0000",
    }
    desc = describe_budget_rule_event(
        action="budget_rule.create",
        payload=payload,
        category_slug="groceries",
        period_start=period(2026, 6, 1, 0),
    )
    assert desc == (
        "A budget rule for 'groceries' took effect from June 2026: "
        "a 10,000.00 INR cap, with up to 2,000.00 INR carrying over to the next month."
    )


def test_describe_budget_rule_future_effective_date_returns_none():
    """A rule that only takes effect in a later period doesn't explain
    anything about the period being viewed."""
    payload = {
        "category_slug": "groceries",
        "effective_from": "2026-08-01",
        "cap_amount": "10000.0000",
        "currency": "INR",
        "rollover_mode": "none",
    }
    desc = describe_budget_rule_event(
        action="budget_rule.create",
        payload=payload,
        category_slug="groceries",
        period_start=period(2026, 6, 1, 0),
    )
    assert desc is None


def test_describe_budget_rule_delete():
    payload = {
        "category_slug": "groceries",
        "effective_from": "2026-01-01",
        "cap_amount": "10000.0000",
        "currency": "INR",
        "rollover_mode": "full",
    }
    desc = describe_budget_rule_event(
        action="budget_rule.delete",
        payload=payload,
        category_slug="groceries",
        period_start=period(2026, 4, 1, 0),
    )
    assert desc == "The budget rule for 'groceries' (effective from January 2026) was removed."

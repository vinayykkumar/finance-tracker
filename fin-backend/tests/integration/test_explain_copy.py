"""Alignment tests: the /explain copy must always quote the same numbers as
`current` (and `current` must match the matching entry in /budgets/summary),
across the scenarios that actually move totals — rollover, retroactive
rules, recategorization, and back-dating.

These complement the unit tests in tests/unit/test_explanations.py (which
pin exact wording for fixed inputs) by checking real API responses produced
through the full summary/explain pipeline stay consistent with each other as
totals shift.
"""

from decimal import Decimal

import httpx
from app.modules.budget_rules.explanations import format_money, format_period

from tests.integration.conftest import create_account, create_transaction, upsert_rule

D = Decimal


def _joined(lines: list[str]) -> str:
    return " ".join(lines)


async def test_rollover_summary_lines_match_current(authed_client: httpx.AsyncClient):
    account = await create_account(authed_client)
    await upsert_rule(
        authed_client, cap_amount="10000", rollover_mode="full", effective_from="2026-06-01"
    )
    await create_transaction(
        authed_client,
        account_id=account["id"],
        amount="-4000",
        category_slug="groceries",
        occurred_at="2026-06-10T12:00:00Z",
    )
    await create_transaction(
        authed_client,
        account_id=account["id"],
        amount="-9000",
        category_slug="groceries",
        occurred_at="2026-07-20T12:00:00Z",
    )

    explain = await authed_client.get(
        "/v1/budgets/summary/explain",
        params={"year": 2026, "month": 7, "category_slug": "groceries"},
    )
    assert explain.status_code == 200
    body = explain.json()
    current = body["current"]
    currency = current["currency"]

    # available == cap + rollover_in (the relationship the rollover line claims)
    assert D(current["available"]) == D(current["cap_amount"]) + D(current["rollover_in"])

    text = _joined(body["summary_lines"])
    assert (
        f"Your cap for 'groceries' this month is {format_money(D(current['cap_amount']), currency)}."
        in text
    )
    assert (
        f"{format_money(D(current['rollover_in']), currency)} rolled over from last month"
        in text
    )
    assert f"{format_money(D(current['available']), currency)} available this month" in text
    assert (
        f"You've spent {format_money(D(current['actual_spend']), currency)}, "
        f"leaving {format_money(D(current['remaining']), currency)}."
        in text
    )

    # cross-endpoint alignment: /explain.current matches the /summary entry
    summary = await authed_client.get(
        "/v1/budgets/summary", params={"year": 2026, "month": 7}
    )
    summary_cat = next(
        c for c in summary.json()["categories"] if c["category_slug"] == "groceries"
    )
    assert summary_cat == current


async def test_over_budget_summary_lines_match_current(authed_client: httpx.AsyncClient):
    account = await create_account(authed_client)
    await upsert_rule(
        authed_client, cap_amount="10000", rollover_mode="none", effective_from="2026-06-01"
    )
    await create_transaction(
        authed_client,
        account_id=account["id"],
        amount="-15000",
        category_slug="groceries",
        occurred_at="2026-06-10T12:00:00Z",
    )

    explain = await authed_client.get(
        "/v1/budgets/summary/explain",
        params={"year": 2026, "month": 6, "category_slug": "groceries"},
    )
    body = explain.json()
    current = body["current"]
    currency = current["currency"]
    assert current["over_budget"] is True

    over_by = -D(current["remaining"])
    text = _joined(body["summary_lines"])
    assert (
        f"You've spent {format_money(D(current['actual_spend']), currency)}, "
        f"which is {format_money(over_by, currency)} over what's available."
        in text
    )
    # No future-rollover line for rollover_mode='none', even though over budget.
    assert "would roll over into next month" not in text


async def test_unbudgeted_summary_lines_match_actual_spend(authed_client: httpx.AsyncClient):
    account = await create_account(authed_client)
    await create_transaction(
        authed_client,
        account_id=account["id"],
        amount="-850",
        category_slug="pet-supplies",
        occurred_at="2026-06-05T12:00:00Z",
    )

    explain = await authed_client.get(
        "/v1/budgets/summary/explain",
        params={"year": 2026, "month": 6, "category_slug": "pet-supplies"},
    )
    body = explain.json()
    current = body["current"]
    assert current["is_unbudgeted"] is True

    text = _joined(body["summary_lines"])
    assert "No budget rule covers 'pet-supplies' this month" in text
    assert (
        f"You've spent {format_money(D(current['actual_spend']), 'INR')} here so far this month."
        in text
    )


async def test_retroactive_rule_event_quotes_correct_cap_and_period(authed_client: httpx.AsyncClient):
    account = await create_account(authed_client)
    await create_transaction(
        authed_client,
        account_id=account["id"],
        amount="-3000",
        category_slug="groceries",
        occurred_at="2026-05-15T12:00:00Z",
    )
    await upsert_rule(
        authed_client, cap_amount="5000", rollover_mode="full", effective_from="2026-05-01"
    )

    explain = await authed_client.get(
        "/v1/budgets/summary/explain",
        params={"year": 2026, "month": 5, "category_slug": "groceries"},
    )
    body = explain.json()
    create_events = [e for e in body["events"] if e["type"] == "budget_rule.create"]
    assert len(create_events) == 1
    expected_cap = format_money(D("5000"), "INR")
    expected_period = format_period("2026-05-01")
    assert expected_cap in create_events[0]["description"]
    assert expected_period in create_events[0]["description"]
    assert "with any unused amount carrying over to the next month" in create_events[0]["description"]

    # And the retroactive rule is reflected in current's numbers too.
    current = body["current"]
    assert current["is_unbudgeted"] is False
    assert D(current["cap_amount"]) == D("5000")


async def test_recategorization_event_quotes_amount_and_categories(authed_client: httpx.AsyncClient):
    account = await create_account(authed_client)
    for slug in ("groceries", "dining"):
        await upsert_rule(authed_client, category_slug=slug)

    tx = await create_transaction(
        authed_client,
        account_id=account["id"],
        amount="-1200",
        category_slug="groceries",
        occurred_at="2026-06-08T12:00:00Z",
    )
    await authed_client.patch(f"/v1/transactions/{tx['id']}", json={"category_slug": "dining"})

    groceries_explain = await authed_client.get(
        "/v1/budgets/summary/explain",
        params={"year": 2026, "month": 6, "category_slug": "groceries"},
    )
    dining_explain = await authed_client.get(
        "/v1/budgets/summary/explain",
        params={"year": 2026, "month": 6, "category_slug": "dining"},
    )

    groceries_events = [e for e in groceries_explain.json()["events"] if e["type"] == "transaction.update"]
    dining_events = [e for e in dining_explain.json()["events"] if e["type"] == "transaction.update"]
    assert len(groceries_events) == 1
    assert len(dining_events) == 1
    # Each category gets the framing relevant to it.
    assert groceries_events[0]["description"] == (
        "A transaction was updated: it was moved from 'groceries' to 'dining'."
    )
    assert dining_events[0]["description"] == (
        "A transaction was updated: it was moved into 'dining' from 'groceries'."
    )

    # The moved spend is reflected in both categories' current numbers.
    assert D(groceries_explain.json()["current"]["actual_spend"]) == D("0")
    assert D(dining_explain.json()["current"]["actual_spend"]) == D("1200")


async def test_backdated_amount_change_event_quotes_old_and_new_amounts(authed_client: httpx.AsyncClient):
    account = await create_account(authed_client)
    await upsert_rule(
        authed_client, cap_amount="10000", rollover_mode="full", effective_from="2026-06-01"
    )
    june_tx = await create_transaction(
        authed_client,
        account_id=account["id"],
        amount="-4000",
        category_slug="groceries",
        occurred_at="2026-06-10T12:00:00Z",
    )
    await authed_client.patch(f"/v1/transactions/{june_tx['id']}", json={"amount": "-5500"})

    explain = await authed_client.get(
        "/v1/budgets/summary/explain",
        params={"year": 2026, "month": 6, "category_slug": "groceries"},
    )
    body = explain.json()
    update_events = [e for e in body["events"] if e["type"] == "transaction.update"]
    assert len(update_events) == 1
    expected_old = format_money(D("4000"), "INR")
    expected_new = format_money(D("5500"), "INR")
    assert (
        update_events[0]["description"]
        == f"A transaction was updated: its amount changed from {expected_old} to {expected_new}."
    )

    # current.actual_spend reflects the new amount, not the old one.
    assert D(body["current"]["actual_spend"]) == D("5500")

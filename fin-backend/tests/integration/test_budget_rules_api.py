"""HTTP-level integration tests for the budget rules engine API:
/v1/budget-rules CRUD, /v1/budgets/summary, /v1/budgets/summary/explain, and
an end-to-end recalculation flow driven entirely through the HTTP API.
"""

from decimal import Decimal

import httpx
import pytest

from tests.integration.conftest import create_account, create_transaction, upsert_rule

D = Decimal


# ---------------------------------------------------------------------------
# /v1/budget-rules CRUD
# ---------------------------------------------------------------------------


async def test_create_list_get_rule(authed_client: httpx.AsyncClient):
    created = await upsert_rule(authed_client)
    assert created["category_slug"] == "groceries"
    assert created["cap_amount"] == "10000.0000"
    assert created["rollover_mode"] == "none"

    listed = await authed_client.get("/v1/budget-rules", params={"category_slug": "groceries"})
    assert listed.status_code == 200
    assert [r["id"] for r in listed.json()] == [created["id"]]

    got = await authed_client.get(f"/v1/budget-rules/{created['id']}")
    assert got.status_code == 200
    assert got.json()["id"] == created["id"]


async def test_upsert_same_composite_key_updates_existing(authed_client: httpx.AsyncClient):
    first = await upsert_rule(authed_client, cap_amount="10000")
    second = await upsert_rule(authed_client, cap_amount="12000", rollover_mode="full")

    assert first["id"] == second["id"]
    assert D(second["cap_amount"]) == D("12000")
    assert second["rollover_mode"] == "full"


async def test_patch_rule_updates_cap_and_rollover(authed_client: httpx.AsyncClient):
    rule = await upsert_rule(authed_client, rollover_mode="none")

    resp = await authed_client.patch(
        f"/v1/budget-rules/{rule['id']}",
        json={"cap_amount": "20000", "rollover_mode": "capped", "rollover_cap_amount": "5000"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["cap_amount"] == "20000.0000"
    assert body["rollover_mode"] == "capped"
    assert body["rollover_cap_amount"] == "5000.0000"


async def test_patch_rollover_capped_without_cap_amount_returns_422(authed_client: httpx.AsyncClient):
    rule = await upsert_rule(authed_client, rollover_mode="none")

    resp = await authed_client.patch(
        f"/v1/budget-rules/{rule['id']}", json={"rollover_mode": "capped"}
    )
    assert resp.status_code == 422


async def test_currency_mismatch_returns_422(authed_client: httpx.AsyncClient):
    await upsert_rule(authed_client, currency="INR", effective_from="2026-01-01")

    resp = await authed_client.post(
        "/v1/budget-rules",
        json={
            "category_slug": "groceries",
            "cap_amount": "100",
            "currency": "USD",
            "rollover_mode": "none",
            "effective_from": "2026-06-01",
        },
    )
    assert resp.status_code == 422


async def test_effective_from_must_be_first_of_month_returns_422(authed_client: httpx.AsyncClient):
    resp = await authed_client.post(
        "/v1/budget-rules",
        json={
            "category_slug": "groceries",
            "cap_amount": "100",
            "currency": "INR",
            "rollover_mode": "none",
            "effective_from": "2026-06-15",
        },
    )
    assert resp.status_code == 422


async def test_delete_rule_then_get_returns_404(authed_client: httpx.AsyncClient):
    rule = await upsert_rule(authed_client)

    resp = await authed_client.delete(f"/v1/budget-rules/{rule['id']}")
    assert resp.status_code == 204

    resp = await authed_client.get(f"/v1/budget-rules/{rule['id']}")
    assert resp.status_code == 404


async def test_get_unknown_rule_returns_404(authed_client: httpx.AsyncClient):
    resp = await authed_client.get("/v1/budget-rules/00000000-0000-0000-0000-000000000000")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Auth / CSRF
# ---------------------------------------------------------------------------


async def test_budget_rules_requires_auth(app_client: httpx.AsyncClient):
    resp = await app_client.get("/v1/budget-rules")
    assert resp.status_code == 401


async def test_post_without_csrf_token_is_rejected(app_client: httpx.AsyncClient):
    email = "csrf-test@example.com"
    register = await app_client.post(
        "/v1/auth/register", json={"email": email, "password": "correct horse battery staple"}
    )
    assert register.status_code == 201
    # Deliberately not setting X-CSRF-Token.
    resp = await app_client.post(
        "/v1/budget-rules",
        json={
            "category_slug": "groceries",
            "cap_amount": "100",
            "currency": "INR",
            "rollover_mode": "none",
            "effective_from": "2026-06-01",
        },
    )
    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# /v1/budgets/summary and /v1/budgets/summary/explain
# ---------------------------------------------------------------------------


async def test_summary_route_does_not_collide_with_budget_id_route(authed_client: httpx.AsyncClient):
    """Regression check: /v1/budgets/summary must not be matched by
    GET /v1/budgets/{budget_id} (which would 422 on UUID parsing of "summary")."""
    resp = await authed_client.get("/v1/budgets/summary", params={"year": 2026, "month": 6})
    assert resp.status_code == 200
    body = resp.json()
    assert body["year"] == 2026
    assert body["month"] == 6
    assert body["categories"] == []
    assert body["unbudgeted"] == {"actual_spend": "0", "categories": []}


async def test_summary_reflects_cap_and_actual_spend(authed_client: httpx.AsyncClient):
    account = await create_account(authed_client)
    await upsert_rule(authed_client, cap_amount="10000", rollover_mode="none")
    await create_transaction(
        authed_client,
        account_id=account["id"],
        amount="-4000",
        category_slug="groceries",
        occurred_at="2026-06-10T12:00:00Z",
    )

    resp = await authed_client.get("/v1/budgets/summary", params={"year": 2026, "month": 6})
    assert resp.status_code == 200
    cat = resp.json()["categories"][0]
    assert cat["category_slug"] == "groceries"
    assert cat["cap_amount"] == "10000.0000"
    assert cat["actual_spend"] == "4000.0000"
    assert cat["available"] == "10000.0000"
    assert cat["remaining"] == "6000.0000"
    assert cat["over_budget"] is False


async def test_summary_unbudgeted_category(authed_client: httpx.AsyncClient):
    account = await create_account(authed_client)
    await create_transaction(
        authed_client,
        account_id=account["id"],
        amount="-850",
        category_slug="pet-supplies",
        occurred_at="2026-06-05T12:00:00Z",
    )

    resp = await authed_client.get("/v1/budgets/summary", params={"year": 2026, "month": 6})
    body = resp.json()
    assert body["categories"] == []
    assert body["unbudgeted"]["actual_spend"] == "850.0000"
    assert body["unbudgeted"]["categories"][0]["category_slug"] == "pet-supplies"


async def test_explain_surfaces_recategorization(authed_client: httpx.AsyncClient):
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

    patch = await authed_client.patch(
        f"/v1/transactions/{tx['id']}", json={"category_slug": "dining"}
    )
    assert patch.status_code == 200

    explain = await authed_client.get(
        "/v1/budgets/summary/explain",
        params={"year": 2026, "month": 6, "category_slug": "groceries"},
    )
    assert explain.status_code == 200
    body = explain.json()
    assert D(body["current"]["actual_spend"]) == D("0")
    assert any("dining" in e["description"] for e in body["events"])


# ---------------------------------------------------------------------------
# End-to-end recalculation flow
# ---------------------------------------------------------------------------


async def test_e2e_backdated_transaction_recalculates_both_periods(authed_client: httpx.AsyncClient):
    """Full flow over HTTP: create a rule with rollover, post transactions in
    two months, read the summary for both, then edit a transaction's amount
    and date so spend shifts from July into June, and confirm both months'
    summaries reflect the change on the next read — no recalculation
    endpoint, just a fresh GET."""
    account = await create_account(authed_client)
    await upsert_rule(
        authed_client,
        cap_amount="10000",
        rollover_mode="full",
        effective_from="2026-06-01",
    )

    june_tx = await create_transaction(
        authed_client,
        account_id=account["id"],
        amount="-4000",
        category_slug="groceries",
        occurred_at="2026-06-10T12:00:00Z",
    )
    july_tx = await create_transaction(
        authed_client,
        account_id=account["id"],
        amount="-9000",
        category_slug="groceries",
        occurred_at="2026-07-20T12:00:00Z",
    )

    june_before = await authed_client.get("/v1/budgets/summary", params={"year": 2026, "month": 6})
    july_before = await authed_client.get("/v1/budgets/summary", params={"year": 2026, "month": 7})
    june_cat = june_before.json()["categories"][0]
    july_cat = july_before.json()["categories"][0]
    assert june_cat["actual_spend"] == "4000.0000"
    assert june_cat["rollover_out"] == "6000.0000"
    assert july_cat["rollover_in"] == "6000.0000"
    assert july_cat["available"] == "16000.0000"
    assert july_cat["remaining"] == "7000.0000"

    # Move 1500 worth of spend from the July transaction into the June one.
    resp = await authed_client.patch(
        f"/v1/transactions/{july_tx['id']}", json={"amount": "-7500"}
    )
    assert resp.status_code == 200
    resp = await authed_client.patch(
        f"/v1/transactions/{june_tx['id']}", json={"amount": "-5500"}
    )
    assert resp.status_code == 200

    june_after = await authed_client.get("/v1/budgets/summary", params={"year": 2026, "month": 6})
    july_after = await authed_client.get("/v1/budgets/summary", params={"year": 2026, "month": 7})
    june_cat = june_after.json()["categories"][0]
    july_cat = july_after.json()["categories"][0]
    assert june_cat["actual_spend"] == "5500.0000"
    assert june_cat["rollover_out"] == "4500.0000"
    assert july_cat["rollover_in"] == "4500.0000"
    assert july_cat["available"] == "14500.0000"
    assert july_cat["actual_spend"] == "7500.0000"
    assert july_cat["remaining"] == "7000.0000"


async def test_e2e_retroactive_rule_then_explain(authed_client: httpx.AsyncClient):
    """Create spend in a month with no rule (unbudgeted), then add a rule
    effective from that month, and confirm both the summary and the explain
    view reflect the retroactive change."""
    account = await create_account(authed_client)
    await create_transaction(
        authed_client,
        account_id=account["id"],
        amount="-3000",
        category_slug="groceries",
        occurred_at="2026-05-15T12:00:00Z",
    )

    before = await authed_client.get("/v1/budgets/summary", params={"year": 2026, "month": 5})
    assert before.json()["unbudgeted"]["actual_spend"] == "3000.0000"

    await upsert_rule(
        authed_client,
        cap_amount="5000",
        rollover_mode="full",
        effective_from="2026-05-01",
    )

    after = await authed_client.get("/v1/budgets/summary", params={"year": 2026, "month": 5})
    cat = after.json()["categories"][0]
    assert cat["is_unbudgeted"] is False
    assert cat["available"] == "5000.0000"
    assert cat["rollover_out"] == "2000.0000"

    explain = await authed_client.get(
        "/v1/budgets/summary/explain",
        params={"year": 2026, "month": 5, "category_slug": "groceries"},
    )
    assert any(e["type"] == "budget_rule.create" for e in explain.json()["events"])


@pytest.mark.parametrize("year,month", [(1999, 12), (2026, 13)])
async def test_summary_rejects_out_of_range_year_month(authed_client: httpx.AsyncClient, year, month):
    resp = await authed_client.get("/v1/budgets/summary", params={"year": year, "month": month})
    assert resp.status_code == 422

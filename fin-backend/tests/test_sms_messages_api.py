"""Integration tests for /v1/sms-messages/* — auth, dedupe, parsing, edge cases.

Run against the real FastAPI app (session cookies + CSRF middleware) backed
by an in-memory SQLite DB (see conftest.py).
"""

from httpx import AsyncClient

from tests.conftest import register_user

DEBIT_BODY = "Rs.500.00 debited from A/c XX1234 on 12-06-26 to VPA shop@okhdfcbank. Avl Bal Rs.9,500.00"
OTP_BODY = "Dear Customer, your OTP for login is 482913. Valid for 10 minutes. Do not share this with anyone."
PROMO_BODY = "Get Rs.2000 cashback on your AXIS a/c when you use UPI Lite this week. T&C apply."


def _msg(**overrides):
    base = {
        "sender": "AD-HDFCBK",
        "body": DEBIT_BODY,
        "received_at": "2026-06-11T10:00:00Z",
        "device_msg_id": "device-1",
    }
    base.update(overrides)
    return base


async def _register(client: AsyncClient, email: str) -> dict[str, str]:
    csrf = await register_user(client, email)
    return {"X-CSRF-Token": csrf}


# ---------------------------------------------------------------------------
# Auth + CSRF
# ---------------------------------------------------------------------------


async def test_sync_requires_authentication(app_client: AsyncClient) -> None:
    resp = await app_client.post("/v1/sms-messages/sync", json={"messages": [_msg()]})
    assert resp.status_code == 401


async def test_sync_requires_csrf_token(app_client: AsyncClient) -> None:
    await register_user(app_client, "csrf@example.com")
    resp = await app_client.post("/v1/sms-messages/sync", json={"messages": [_msg()]})
    assert resp.status_code == 403


async def test_list_requires_authentication(app_client: AsyncClient) -> None:
    resp = await app_client.get("/v1/sms-messages")
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


async def test_sync_happy_path_parses_and_persists(app_client: AsyncClient) -> None:
    headers = await _register(app_client, "happy@example.com")

    resp = await app_client.post(
        "/v1/sms-messages/sync", json={"messages": [_msg()]}, headers=headers
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["received"] == 1
    assert body["created"] == 1
    assert body["duplicates"] == 0
    assert body["parsed"] == 1
    assert body["unparsed"] == 0
    assert body["rejected"] == 0

    item = body["results"][0]
    assert item["duplicate"] is False
    assert item["parse_status"] == "parsed"
    assert item["parser_template"] == "generic_debit_inr_v1"

    # Land where it should: GET shows the structured payload.
    list_resp = await app_client.get("/v1/sms-messages", headers=headers)
    assert list_resp.status_code == 200
    rows = list_resp.json()
    assert len(rows) == 1
    row = rows[0]
    assert row["id"] == item["id"]
    assert row["sender"] == "AD-HDFCBK"
    assert row["sender_key"] == "ADHDFCBK"
    assert row["parse_status"] == "parsed"
    assert row["parsed_payload"] == {
        "template": "generic_debit_inr_v1",
        "direction": "debit",
        "amount": "500.00",
        "currency": "INR",
        "account_tail": "1234",
        "merchant": "VPA shop@okhdfcbank",
        "balance_after": "9500.00",
        "txn_date": "12-06-26",
    }

    get_resp = await app_client.get(f"/v1/sms-messages/{row['id']}", headers=headers)
    assert get_resp.status_code == 200
    assert get_resp.json()["id"] == row["id"]


# ---------------------------------------------------------------------------
# Dedupe
# ---------------------------------------------------------------------------


async def test_duplicate_upload_does_not_double_insert(app_client: AsyncClient) -> None:
    headers = await _register(app_client, "dupe@example.com")

    first = await app_client.post(
        "/v1/sms-messages/sync", json={"messages": [_msg()]}, headers=headers
    )
    assert first.status_code == 200
    first_item = first.json()["results"][0]
    assert first_item["duplicate"] is False

    # Re-sync the exact same SMS (e.g. device re-read its SMS provider cursor).
    second = await app_client.post(
        "/v1/sms-messages/sync", json={"messages": [_msg()]}, headers=headers
    )
    assert second.status_code == 200
    second_body = second.json()
    assert second_body["created"] == 0
    assert second_body["duplicates"] == 1
    second_item = second_body["results"][0]
    assert second_item["duplicate"] is True
    assert second_item["id"] == first_item["id"]
    assert second_item["fingerprint"] == first_item["fingerprint"]

    rows = (await app_client.get("/v1/sms-messages", headers=headers)).json()
    assert len(rows) == 1


async def test_duplicate_within_same_batch_does_not_double_insert(app_client: AsyncClient) -> None:
    headers = await _register(app_client, "dupe-batch@example.com")

    resp = await app_client.post(
        "/v1/sms-messages/sync",
        json={"messages": [_msg(), _msg()]},
        headers=headers,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["created"] == 1
    assert body["duplicates"] == 1
    assert body["results"][0]["id"] == body["results"][1]["id"]

    rows = (await app_client.get("/v1/sms-messages", headers=headers)).json()
    assert len(rows) == 1


# ---------------------------------------------------------------------------
# Honest match-vs-no-match
# ---------------------------------------------------------------------------


async def test_otp_message_is_unparsed_not_guessed(app_client: AsyncClient) -> None:
    headers = await _register(app_client, "otp@example.com")

    resp = await app_client.post(
        "/v1/sms-messages/sync",
        json={"messages": [_msg(body=OTP_BODY, device_msg_id="otp-1")]},
        headers=headers,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["unparsed"] == 1
    item = body["results"][0]
    assert item["parse_status"] == "unparsed"
    assert item["parser_template"] is None


async def test_bank_like_promo_is_unparsed(app_client: AsyncClient) -> None:
    """Sender looks like a bank and the body mentions 'Rs'/'a/c', but it's not
    a transaction alert — must be reported as unparsed, not misfired into a
    template."""
    headers = await _register(app_client, "promo@example.com")

    resp = await app_client.post(
        "/v1/sms-messages/sync",
        json={"messages": [_msg(sender="AX-AXISBK", body=PROMO_BODY, device_msg_id="promo-1")]},
        headers=headers,
    )
    assert resp.status_code == 200
    item = resp.json()["results"][0]
    assert item["parse_status"] == "unparsed"


# ---------------------------------------------------------------------------
# Rejection rules
# ---------------------------------------------------------------------------


async def test_oversized_body_is_truncated_and_rejected(app_client: AsyncClient) -> None:
    headers = await _register(app_client, "oversized@example.com")

    huge_body = "A" * 2000  # > MAX_BODY_STORAGE_LEN (1600), well under the 6000 hard cap
    resp = await app_client.post(
        "/v1/sms-messages/sync",
        json={"messages": [_msg(body=huge_body, device_msg_id="huge-1")]},
        headers=headers,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["rejected"] == 1
    item = body["results"][0]
    assert item["parse_status"] == "rejected"
    assert item["reject_reason"] == "body_too_long"

    row = (await app_client.get(f"/v1/sms-messages/{item['id']}", headers=headers)).json()
    assert row["body_length"] == 2000
    assert len(row["body"]) == 1600


async def test_invalid_sender_is_rejected(app_client: AsyncClient) -> None:
    headers = await _register(app_client, "badsender@example.com")

    resp = await app_client.post(
        "/v1/sms-messages/sync",
        json={"messages": [_msg(sender="!!!", device_msg_id="bad-sender-1")]},
        headers=headers,
    )
    assert resp.status_code == 200
    item = resp.json()["results"][0]
    assert item["parse_status"] == "rejected"
    assert item["reject_reason"] == "invalid_sender"


async def test_request_over_batch_limit_is_rejected(app_client: AsyncClient) -> None:
    headers = await _register(app_client, "bigbatch@example.com")

    messages = [_msg(device_msg_id=f"msg-{i}") for i in range(51)]
    resp = await app_client.post(
        "/v1/sms-messages/sync", json={"messages": messages}, headers=headers
    )
    assert resp.status_code == 422


async def test_empty_batch_is_rejected(app_client: AsyncClient) -> None:
    headers = await _register(app_client, "emptybatch@example.com")

    resp = await app_client.post("/v1/sms-messages/sync", json={"messages": []}, headers=headers)
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Clock skew
# ---------------------------------------------------------------------------


async def test_clock_skew_received_at_is_tolerated(app_client: AsyncClient) -> None:
    headers = await _register(app_client, "skew@example.com")

    resp = await app_client.post(
        "/v1/sms-messages/sync",
        json={
            "messages": [
                _msg(received_at="2099-01-01T00:00:00Z", device_msg_id="future-1"),
                _msg(received_at="1990-01-01T00:00:00Z", device_msg_id="past-1"),
            ]
        },
        headers=headers,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["created"] == 2
    assert all(r["parse_status"] == "parsed" for r in body["results"])


# ---------------------------------------------------------------------------
# Cross-user isolation
# ---------------------------------------------------------------------------


async def test_users_cannot_see_each_others_messages(app_client: AsyncClient) -> None:
    headers_a = await _register(app_client, "user-a@example.com")
    resp = await app_client.post(
        "/v1/sms-messages/sync", json={"messages": [_msg()]}, headers=headers_a
    )
    msg_id = resp.json()["results"][0]["id"]

    headers_b = await _register(app_client, "user-b@example.com")
    rows_b = (await app_client.get("/v1/sms-messages", headers=headers_b)).json()
    assert rows_b == []

    not_found = await app_client.get(f"/v1/sms-messages/{msg_id}", headers=headers_b)
    assert not_found.status_code == 404


async def test_get_unknown_message_returns_404(app_client: AsyncClient) -> None:
    headers = await _register(app_client, "notfound@example.com")
    resp = await app_client.get(
        "/v1/sms-messages/00000000-0000-0000-0000-000000000000", headers=headers
    )
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Throttle
# ---------------------------------------------------------------------------


async def test_sync_throttle_returns_429_after_limit(app_client: AsyncClient) -> None:
    headers = await _register(app_client, "throttle@example.com")

    statuses = []
    for i in range(8):
        resp = await app_client.post(
            "/v1/sms-messages/sync",
            json={"messages": [_msg(device_msg_id=f"throttle-{i}")]},
            headers=headers,
        )
        statuses.append(resp.status_code)

    assert statuses[:6] == [200] * 6
    assert 429 in statuses[6:]

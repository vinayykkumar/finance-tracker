"""Integration tests for POST /v1/sms-ingest/batch.

We build a slim FastAPI app that registers only the sms_ingest router so tests
don't need the full cookie/CSRF/session stack that the production app uses.
The auth dependency is overridden to either return a fixed UUID (authenticated)
or left as-is with a minimal SessionMiddleware so it correctly raises 401
(unauthenticated).
"""

import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from starlette.middleware.sessions import SessionMiddleware
from starlette.testclient import TestClient

from app.modules.sms_ingest.schemas import BatchResult, RejectedItem

TEST_USER_ID = uuid.uuid4()
NOW = datetime.now(UTC)
VALID_ITEM = {
    "device_message_id": "msg_001",
    "sender": "SBIINB",
    "body": "INR 100 debited from SBI account XX1234.",
    "received_at": NOW.isoformat(),
}


# ---------------------------------------------------------------------------
# App factory — no CSRF middleware, just optional session for unauth tests
# ---------------------------------------------------------------------------


def _make_app(
    *,
    authenticated: bool,
    mock_svc: AsyncMock,
) -> FastAPI:
    import fastapi

    from app.api.exception_handlers import register_exception_handlers
    from app.api.v1 import sms_ingest as sms_ingest_v1
    from app.auth.session_user import require_session_user_id

    app = FastAPI()
    register_exception_handlers(app)

    if authenticated:
        app.dependency_overrides[require_session_user_id] = lambda: TEST_USER_ID
    else:
        # Keep real dependency so it raises 401 — needs session scope present
        app.add_middleware(SessionMiddleware, secret_key="test-secret-only")

    app.dependency_overrides[sms_ingest_v1.get_sms_ingest_service] = lambda: mock_svc

    v1 = fastapi.APIRouter(prefix="/v1")
    v1.include_router(sms_ingest_v1.router)
    app.include_router(v1)
    return app


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def mock_svc() -> AsyncMock:
    svc = AsyncMock()
    svc.ingest_batch.return_value = BatchResult(accepted=1, duplicates=0, rejected=[])
    return svc


@pytest.fixture()
def client(mock_svc: AsyncMock) -> TestClient:
    return TestClient(_make_app(authenticated=True, mock_svc=mock_svc), raise_server_exceptions=False)


@pytest.fixture()
def unauthed_client(mock_svc: AsyncMock) -> TestClient:
    return TestClient(_make_app(authenticated=False, mock_svc=mock_svc), raise_server_exceptions=False)


# ---------------------------------------------------------------------------
# Auth guard
# ---------------------------------------------------------------------------


def test_unauthenticated_returns_401(unauthed_client: TestClient) -> None:
    resp = unauthed_client.post("/v1/sms-ingest/batch", json={"items": [VALID_ITEM]})
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


def test_batch_happy_path(client: TestClient, mock_svc: AsyncMock) -> None:
    resp = client.post("/v1/sms-ingest/batch", json={"items": [VALID_ITEM]})
    assert resp.status_code == 200
    data = resp.json()
    assert data["accepted"] == 1
    assert data["duplicates"] == 0
    assert data["rejected"] == []
    mock_svc.ingest_batch.assert_awaited_once()


def test_empty_batch_accepted(client: TestClient, mock_svc: AsyncMock) -> None:
    mock_svc.ingest_batch.return_value = BatchResult(accepted=0, duplicates=0, rejected=[])
    resp = client.post("/v1/sms-ingest/batch", json={"items": []})
    assert resp.status_code == 200
    assert resp.json()["accepted"] == 0


# ---------------------------------------------------------------------------
# Duplicate fingerprint — service returns duplicates=1 on replay
# ---------------------------------------------------------------------------


def test_duplicate_not_double_inserted(client: TestClient, mock_svc: AsyncMock) -> None:
    """Sending the same fingerprint again must increment duplicates, not rows."""
    mock_svc.ingest_batch.return_value = BatchResult(accepted=0, duplicates=1, rejected=[])
    resp = client.post("/v1/sms-ingest/batch", json={"items": [VALID_ITEM]})
    assert resp.status_code == 200
    data = resp.json()
    assert data["accepted"] == 0
    assert data["duplicates"] == 1


# ---------------------------------------------------------------------------
# Pydantic schema-level rejection
# ---------------------------------------------------------------------------


def test_oversized_body_rejected_by_schema(client: TestClient) -> None:
    """Bodies > 2000 chars are rejected at the Pydantic layer (max_length=2000)."""
    big_item = {**VALID_ITEM, "body": "x" * 2001}
    resp = client.post("/v1/sms-ingest/batch", json={"items": [big_item]})
    assert resp.status_code == 422


def test_batch_too_large_returns_422(client: TestClient) -> None:
    """101 items exceeds max_length=100 on BatchIn.items."""
    items = [{**VALID_ITEM, "device_message_id": f"msg_{i}"} for i in range(101)]
    resp = client.post("/v1/sms-ingest/batch", json={"items": items})
    assert resp.status_code == 422


def test_missing_sender_returns_422(client: TestClient) -> None:
    item_no_sender = {k: v for k, v in VALID_ITEM.items() if k != "sender"}
    resp = client.post("/v1/sms-ingest/batch", json={"items": [item_no_sender]})
    assert resp.status_code == 422


def test_invalid_received_at_returns_422(client: TestClient) -> None:
    bad_item = {**VALID_ITEM, "received_at": "not-a-date"}
    resp = client.post("/v1/sms-ingest/batch", json={"items": [bad_item]})
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Service-layer rejections propagated to caller
# ---------------------------------------------------------------------------


def test_service_rejection_propagated(client: TestClient, mock_svc: AsyncMock) -> None:
    """Service-layer rejections (e.g. received_at_too_old) flow back in JSON body."""
    mock_svc.ingest_batch.return_value = BatchResult(
        accepted=0,
        duplicates=0,
        rejected=[RejectedItem(device_message_id="msg_001", reason="received_at_too_old")],
    )
    old_item = {**VALID_ITEM, "received_at": (NOW - timedelta(days=60)).isoformat()}
    resp = client.post("/v1/sms-ingest/batch", json={"items": [old_item]})
    assert resp.status_code == 200
    data = resp.json()
    assert data["rejected"][0]["reason"] == "received_at_too_old"


# ---------------------------------------------------------------------------
# Mixed batch
# ---------------------------------------------------------------------------


def test_mixed_batch_counts(client: TestClient, mock_svc: AsyncMock) -> None:
    mock_svc.ingest_batch.return_value = BatchResult(
        accepted=2,
        duplicates=1,
        rejected=[RejectedItem(device_message_id="msg_old", reason="received_at_too_old")],
    )
    items = [
        VALID_ITEM,
        {**VALID_ITEM, "device_message_id": "msg_002"},
        {**VALID_ITEM, "device_message_id": "msg_dup"},
        {**VALID_ITEM, "device_message_id": "msg_old"},
    ]
    resp = client.post("/v1/sms-ingest/batch", json={"items": items})
    assert resp.status_code == 200
    data = resp.json()
    assert data["accepted"] == 2
    assert data["duplicates"] == 1
    assert len(data["rejected"]) == 1

"""Fixtures for HTTP-level (API) integration tests.

Builds the real FastAPI app (auth, CSRF, session middleware all active) with
``get_db`` overridden to a per-test in-memory SQLite database, and an
``httpx.AsyncClient`` talking to it over ``ASGITransport`` (no network, no
lifespan — so no dependency on a real Postgres).
"""

from collections.abc import AsyncIterator
from uuid import uuid4

import httpx
import pytest_asyncio
from app.db.base import Base
from app.db.session import get_db
from app.factory import create_app
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

TEST_PASSWORD = "correct horse battery staple"


@pytest_asyncio.fixture
async def app_client() -> AsyncIterator[httpx.AsyncClient]:
    # StaticPool: a single shared connection, so every request's session
    # (each `get_db()` call opens a new AsyncSession) sees the same in-memory
    # database — a plain in-memory engine gives each connection its own DB.
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async def override_get_db() -> AsyncIterator[AsyncSession]:
        async with session_factory() as session:
            yield session

    app = create_app(enable_auth=True)
    app.dependency_overrides[get_db] = override_get_db

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        yield client

    await engine.dispose()


@pytest_asyncio.fixture
async def authed_client(app_client: httpx.AsyncClient) -> httpx.AsyncClient:
    """Registers a fresh user, and configures the client with the session
    cookie (handled automatically by httpx's cookie jar) and the CSRF token
    required for mutating requests."""
    email = f"{uuid4()}@example.com"
    resp = await app_client.post(
        "/v1/auth/register", json={"email": email, "password": TEST_PASSWORD}
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    app_client.headers["X-CSRF-Token"] = body["csrf_token"]
    return app_client


async def create_account(client: httpx.AsyncClient, **overrides) -> dict:
    payload = {"display_name": "Checking", "currency": "INR", **overrides}
    resp = await client.post("/v1/accounts", json=payload)
    assert resp.status_code == 201, resp.text
    return resp.json()


async def create_transaction(client: httpx.AsyncClient, **overrides) -> dict:
    payload = {
        "amount": "-1000",
        "category_slug": "groceries",
        "occurred_at": "2026-06-10T12:00:00Z",
        **overrides,
    }
    resp = await client.post("/v1/transactions", json=payload)
    assert resp.status_code == 201, resp.text
    return resp.json()


async def upsert_rule(client: httpx.AsyncClient, **overrides) -> dict:
    payload = {
        "category_slug": "groceries",
        "cap_amount": "10000",
        "currency": "INR",
        "rollover_mode": "none",
        "effective_from": "2026-06-01",
        **overrides,
    }
    resp = await client.post("/v1/budget-rules", json=payload)
    assert resp.status_code == 201, resp.text
    return resp.json()

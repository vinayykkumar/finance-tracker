"""Shared test fixtures.

Runs the *real* FastAPI app (session auth, CSRF middleware, RFC7807 error
handlers — see app/factory.py) against an in-memory SQLite DB instead of
Postgres.

Cross-dialect note: ``app.models.sms_message.SmsMessage`` uses
``postgresql.UUID`` and ``JSON().with_variant(JSONB(), "postgresql")``, both
of which compile fine on SQLite (unlike the plain ``postgresql.JSONB`` used
by ``AuditEvent``), so we create only the ``users`` and ``sms_messages``
tables here — that's all the SMS ingest slice touches.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator

import pytest_asyncio
from app.db.base import Base
from app.db.session import get_db
from app.factory import create_app
from app.models.sms_message import SmsMessage
from app.models.user import User
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool


@pytest_asyncio.fixture
async def db_engine():
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all, tables=[User.__table__, SmsMessage.__table__])
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture
async def app_client(db_engine) -> AsyncGenerator[AsyncClient, None]:
    session_factory = async_sessionmaker(db_engine, class_=AsyncSession, expire_on_commit=False)

    async def override_get_db() -> AsyncGenerator[AsyncSession, None]:
        async with session_factory() as session:
            yield session

    app = create_app(enable_auth=True)
    app.dependency_overrides[get_db] = override_get_db

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


async def register_user(client: AsyncClient, email: str, password: str = "correct horse battery staple") -> str:
    """Register + log in a fresh user, returning the CSRF token to send on writes."""
    resp = await client.post("/v1/auth/register", json={"email": email, "password": password})
    assert resp.status_code == 201, resp.text
    return resp.json()["csrf_token"]

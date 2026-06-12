"""Shared test fixtures.

Two independent in-memory SQLite harnesses live here, used by different test
suites:

* ``db_session`` (+ ``user``, ``account``, ``make_transaction``, ``make_rule``)
  — a bare async session with ``Base.metadata.create_all`` standing in for the
  full migration chain. Used by the budget-rules unit/integration tests. Keeps
  tests fast and dependency-free; it does not replace running
  ``alembic upgrade head`` against Postgres before deploy.

* ``db_engine`` + ``app_client`` (+ ``register_user``) — runs the *real* FastAPI
  app (session auth, CSRF middleware, RFC7807 error handlers — see
  app/factory.py) against SQLite. Used by the SMS-ingest tests.

Cross-dialect note: ``app.models.sms_message.SmsMessage`` uses
``postgresql.UUID`` and ``JSON().with_variant(JSONB(), "postgresql")``, both of
which compile fine on SQLite (unlike the plain ``postgresql.JSONB`` used by
``AuditEvent``). The ``app_client`` harness therefore creates only the
``users`` and ``sms_messages`` tables — that's all the SMS ingest slice
touches.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator, AsyncIterator
from datetime import datetime
from decimal import Decimal
from uuid import uuid4

import pytest_asyncio
from app.db.base import Base
from app.db.session import get_db
from app.factory import create_app
from app.models.account import FinancialAccount
from app.models.budget_rule import BudgetRule
from app.models.sms_message import SmsMessage
from app.models.transaction import LedgerTransaction
from app.models.user import User
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

# ---------------------------------------------------------------------------
# Budget-rules harness: bare async session
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def db_session() -> AsyncIterator[AsyncSession]:
    engine = create_async_engine("sqlite+aiosqlite://")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with session_factory() as session:
        yield session
    await engine.dispose()


@pytest_asyncio.fixture
async def user(db_session: AsyncSession) -> User:
    u = User(id=uuid4(), email=f"{uuid4()}@example.com", hashed_password="not-a-real-hash")
    db_session.add(u)
    # Commit (not just flush) so the session starts each test's "request" with
    # no open transaction — TransactionService.create/update/delete open their
    # own transaction via `async with session.begin()`, which raises if one is
    # already active. expire_on_commit=False keeps `u` usable after this.
    await db_session.commit()
    return u


@pytest_asyncio.fixture
async def account(db_session: AsyncSession, user: User) -> FinancialAccount:
    a = FinancialAccount(
        id=uuid4(),
        user_id=user.id,
        display_name="Checking",
        currency="INR",
        balance=Decimal("0"),
    )
    db_session.add(a)
    await db_session.commit()
    return a


async def make_transaction(
    session: AsyncSession,
    *,
    user_id,
    account_id,
    amount: str,
    category_slug: str,
    occurred_at: datetime,
    description: str = "",
) -> LedgerTransaction:
    """Insert a transaction directly (bypassing TransactionService) for
    cheap test setup. Tests that exercise update/delete behavior should go
    through TransactionService instead, to also exercise audit logging and
    account balance maintenance."""
    tx = LedgerTransaction(
        id=uuid4(),
        user_id=user_id,
        account_id=account_id,
        amount=Decimal(amount),
        description=description,
        category_slug=category_slug,
        occurred_at=occurred_at,
    )
    session.add(tx)
    await session.flush()
    return tx


async def make_rule(
    session: AsyncSession,
    *,
    user_id,
    category_slug: str,
    cap_amount: str,
    effective_from,
    rollover_mode: str = "none",
    rollover_cap_amount: str | None = None,
    currency: str = "INR",
) -> BudgetRule:
    """Insert a budget rule version directly for cheap test setup. Tests that
    exercise create/update/delete behavior should go through
    BudgetRuleService instead, to also exercise audit logging and
    validation."""
    rule = BudgetRule(
        id=uuid4(),
        user_id=user_id,
        category_slug=category_slug,
        rule_type="category_cap",
        cap_amount=Decimal(cap_amount),
        currency=currency,
        rollover_mode=rollover_mode,
        rollover_cap_amount=Decimal(rollover_cap_amount) if rollover_cap_amount else None,
        effective_from=effective_from,
    )
    session.add(rule)
    await session.flush()
    return rule


# ---------------------------------------------------------------------------
# SMS-ingest harness: real FastAPI app over SQLite
# ---------------------------------------------------------------------------


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

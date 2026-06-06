# Production hardening — implementation guide

**Status:** Core items from this guide are **implemented in the codebase** (see git history). Use this file as a checklist for remaining P2+ work.

**File count:** The repo already has **374+** `.py`/`.ts`/`.tsx` files (well over 200). This guide adds **real** files only (no filler).

---

## 1. Alembic migration

**New file:** `fin-backend/alembic/versions/0002_production_hardening.py`

```python
"""Idempotency keys, audit events, soft-delete on ledger_transactions."""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0002_hardening"
down_revision: Union[str, None] = "0001_initial"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "ledger_transactions",
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_ledger_transactions_deleted_at", "ledger_transactions", ["deleted_at"])

    op.create_table(
        "idempotency_keys",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("scope", sa.String(128), nullable=False),
        sa.Column("key", sa.String(255), nullable=False),
        sa.Column("response_json", sa.Text(), nullable=True),
        sa.Column("http_status", sa.Integer(), nullable=False, server_default="201"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("user_id", "scope", "key", name="uq_idempotency_user_scope_key"),
    )
    op.create_index("ix_idempotency_keys_user_id", "idempotency_keys", ["user_id"])

    op.create_table(
        "audit_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("action", sa.String(64), nullable=False),
        sa.Column("entity_type", sa.String(64), nullable=False),
        sa.Column("entity_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_audit_events_user_id", "audit_events", ["user_id"])
    op.create_index("ix_audit_events_entity_id", "audit_events", ["entity_id"])


def downgrade() -> None:
    op.drop_index("ix_audit_events_entity_id", table_name="audit_events")
    op.drop_index("ix_audit_events_user_id", table_name="audit_events")
    op.drop_table("audit_events")
    op.drop_index("ix_idempotency_keys_user_id", table_name="idempotency_keys")
    op.drop_table("idempotency_keys")
    op.drop_index("ix_ledger_transactions_deleted_at", table_name="ledger_transactions")
    op.drop_column("ledger_transactions", "deleted_at")
```

---

## 2. New ORM models

**New:** `fin-backend/app/models/idempotency.py` — class `IdempotencyKey` matching the migration (columns as in migration).

**New:** `fin-backend/app/models/audit_event.py` — class `AuditEvent` matching the migration.

**Edit:** `fin-backend/app/models/transaction.py` — add `deleted_at: Mapped[datetime | None]` with `DateTime(timezone=True), nullable=True, index=True` before relationships.

**Edit:** `fin-backend/app/models/__init__.py` — export new models.

**Edit:** `fin-backend/alembic/env.py` — `import app.models.idempotency` and `import app.models.audit_event` (with `# noqa: F401`).

---

## 3. Account row lock

**Edit:** `fin-backend/app/modules/accounts/repository.py`

Add method:

```python
async def get_for_user_for_update(
    self, user_id: UUID, account_id: UUID
) -> FinancialAccount | None:
    r = await self._session.execute(
        select(FinancialAccount)
        .where(
            FinancialAccount.id == account_id,
            FinancialAccount.user_id == user_id,
        )
        .with_for_update()
    )
    return r.scalar_one_or_none()
```

Use `get_for_user_for_update` in `TransactionService` for every balance change.

---

## 4. Transaction repository

**Edit:** `fin-backend/app/modules/transactions/repository.py`

- All `select(LedgerTransaction)` queries: add `.where(LedgerTransaction.deleted_at.is_(None))`.
- Replace `delete()` with soft delete: set `row.deleted_at = datetime.now(UTC)` and flush (no `session.delete`).

---

## 5. Idempotency + audit repositories

**New:** `fin-backend/app/modules/transactions/idempotency_repository.py` — `begin_or_get_completed(user_id, scope, key)` using `INSERT ... ON CONFLICT DO NOTHING` then `SELECT ... FOR UPDATE`; if `response_json` set, return parsed dict; else return row id for completion.

**New:** `fin-backend/app/modules/transactions/audit_repository.py` — `append(user_id, action, entity_type, entity_id, payload)`.

**Constant:** `IDEMPOTENCY_SCOPE_TX_CREATE = "ledger_transaction.create"`.

---

## 6. Transaction service

**Edit:** `fin-backend/app/modules/transactions/service.py`

- `create(user_id, body, idempotency_key: str | None)` — single transaction: optional idempotency replay; lock account `get_for_user_for_update`; insert row; update balance; write idempotency `response_json`; append audit `transaction.create`.
- `update` / `delete` — use `get_for_user_for_update`; soft delete; audit `transaction.update` / `transaction.delete`.

Use `json.dumps(TransactionRead.model_dump(mode="json"), default=str)` for idempotency storage.

---

## 7. API router

**Edit:** `fin-backend/app/api/v1/transactions.py`

- Read optional header `Idempotency-Key`; pass to `svc.create(uid, body, key)`.
- Strip and validate length (e.g. max 255); ignore empty.

---

## 8. Remove boot migrations

**Edit:** `fin-backend/app/db/session.py`

- Remove `_alembic_upgrade` and `asyncio` import.
- Replace `init_db()` with:

```python
from sqlalchemy import text

async def init_db() -> None:
    """Verify DB connectivity. Run `poetry run alembic upgrade head` separately before deploy."""
    async with engine.connect() as conn:
        await conn.execute(text("SELECT 1"))
```

**New:** `fin-backend/scripts/migrate.ps1` — `Set-Location $PSScriptRoot/..; poetry run alembic upgrade head`

**Edit:** `docker-compose.yml` — comment: run `docker compose run --rm api poetry run alembic upgrade head` before first `up` or after schema changes.

---

## 9. RFC 7807

**New:** `fin-backend/app/api/problem.py` — `problem_json_response(status, title, detail, type_url=None, instance=None, request_id=None)` returning `JSONResponse` with `media_type="application/problem+json"`.

**New:** `fin-backend/app/api/exception_handlers.py` — register handlers for `HTTPException`, `RequestValidationError`, generic `Exception`; map `HTTPException.detail` string or list into `detail` string.

**Edit:** `fin-backend/app/factory.py` — call `register_exception_handlers(app)` after `FastAPI(...)`; remove per-route `HTTPException` where redundant (optional).

---

## 10. Request ID + CORS + middleware order

**New:** `fin-backend/app/middleware/request_id.py` — Starlette middleware: read `X-Request-Id` or `uuid4()`; set `scope["state"]["request_id"]`; add header on response.

**New:** `fin-backend/app/middleware/csrf.py` — For `POST`/`PATCH`/`DELETE` under `/v1/` except `/v1/auth/login`, `/v1/auth/register`, `/v1/health/`, `/docs`, `/openapi.json`, `/redoc`: if `request.session.get("user_id")` then require `X-CSRF-Token == request.session.get("csrf_token")`.

**Middleware order (last added = outermost / runs first):**

1. `CsrfProtectMiddleware` (inner)
2. `SessionMiddleware`
3. `CORSMiddleware` — `allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"]`, `allow_headers=[...]` including `X-CSRF-Token`, `X-Request-Id`, `Idempotency-Key`, `expose_headers=["X-Request-Id"]`
4. `RequestIdMiddleware` (outer)

**Edit:** `fin-backend/app/config.py` — properties `session_cookie_https_only` and `session_same_site` (e.g. `https_only` True in staging/production).

**Edit:** `fin-backend/app/auth/wiring.py` — use those settings; add `install_auth_stack(app)` that adds CSRF then Session in that order.

**Edit:** `fin-backend/app/factory.py` — call `install_auth_stack` instead of bare `install_session_middleware`; add CORS then RequestId.

---

## 11. Auth CSRF token + rate limit

**Edit:** `fin-backend/app/api/v1/auth.py` — on successful login/register: `request.session["csrf_token"] = secrets.token_urlsafe(32)`.

**Edit:** `fin-backend/app/schemas/auth.py` — `SessionResponse` add `csrf_token: str | None = None`; populate when authenticated.

**New:** `fin-backend/app/auth/login_throttle.py` — in-memory deque per normalized email; max N attempts per window; raise 429 with problem body.

---

## 12. Main entry + Docker

**Edit:** `fin-backend/app/main.py` — `app = create_app(enable_auth=True)`.

**Edit:** `fin-backend/app/main_auth.py` — `from app.main import app` (re-export).

**Edit:** `fin-backend/Dockerfile` — `CMD ["uvicorn", "app.main:app", ...]`.

**Edit:** `scripts/dev-backend.ps1`, `fin-backend/.env.example`, `fin-mobile/.env.example` — reference `app.main:app`.

---

## 13. Frontend

**New:** `fin-front/src/lib/http/csrfStore.ts` — `getCsrfToken` / `setCsrfToken`.

**Edit:** `fin-front/src/lib/http/fetchHttpClient.ts` — optional `getExtraHeaders?: () => Record<string, string>`; for mutating methods merge `X-CSRF-Token` if present.

**Edit:** `fin-front/src/lib/auth/liveAuthCoordinator.ts` — demo localStorage fallback only if `import.meta.env.DEV || import.meta.env.VITE_ENABLE_DEMO_AUTH === "true"`.

**Edit:** `liveAuthCoordinator` — parse `csrf_token` from session response; call `setCsrfToken`.

**Edit:** `fin-front/src/main.tsx` — pass `getExtraHeaders` from `csrfStore`.

**Edit:** `fin-front/.env.example` — document `VITE_ENABLE_DEMO_AUTH`.

**Edit:** `fin-front/src/lib/api/problemJson.ts` — extend `parseApiProblem` to accept legacy `{ "detail": "..." }`.

---

## 14. Mobile

**Edit:** `fin-mobile/src/core/api/ApiError.ts` — if body has `title`/`detail` (problem+json), use those before `detail`.

**Edit:** `fin-mobile/src/core/http/jsonHttpClient.ts` — optional CSRF header callback mirroring web.

---

## 15. Nginx

**Edit:** `fin-front/nginx.docker.conf` — inside `server { }`:

```nginx
add_header X-Frame-Options "SAMEORIGIN" always;
add_header X-Content-Type-Options "nosniff" always;
add_header Referrer-Policy "strict-origin-when-cross-origin" always;
# HSTS only when TLS terminates here; for local HTTP compose, omit HSTS or use short max-age in staging TLS.
```

---

## 16. Tests

**New:** `fin-backend/tests/test_problem_json_shape.py` — assert helper builds valid problem dict.

**Optional:** `fin-backend/tests/test_csrf_paths.py` — document exempt paths (lightweight).

---

## Run order after merge

```bash
cd fin-backend && poetry run alembic upgrade head
docker compose build && docker compose up -d
```

---

## Why Agent mode is required

Cursor **Plan mode** only allows editing markdown/canvas. All steps above touch `.py`, `.ts`, `.tsx`, `Dockerfile`, etc. Approve **Agent mode** (or disable Plan mode) so the assistant can apply this guide automatically.

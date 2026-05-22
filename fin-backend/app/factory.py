from contextlib import asynccontextmanager

from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1 import health as health_v1
from app.config import get_settings
from app.db.session import close_engine, init_db


def create_app(*, enable_auth: bool = False) -> FastAPI:
    settings = get_settings()

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        await init_db()
        yield
        await close_engine()

    app = FastAPI(title="Finance API", version="0.1.0", lifespan=lifespan)

    if enable_auth:
        from app.auth.wiring import install_session_middleware

        install_session_middleware(app)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    v1 = APIRouter(prefix="/v1")
    v1.include_router(health_v1.router)
    if enable_auth:
        from app.api.v1 import accounts as accounts_v1
        from app.api.v1 import budgets as budgets_v1
        from app.api.v1 import goals as goals_v1
        from app.api.v1 import transactions as transactions_v1
        from app.auth.wiring import include_auth_routes

        include_auth_routes(v1)
        v1.include_router(goals_v1.router)
        v1.include_router(accounts_v1.router)
        v1.include_router(transactions_v1.router)
        v1.include_router(budgets_v1.router)
    app.include_router(v1)

    @app.get("/")
    async def root() -> dict[str, str]:
        return {"service": "finance-api", "docs": "/docs"}

    return app

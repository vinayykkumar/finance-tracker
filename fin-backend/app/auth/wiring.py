"""Session cookie + `/v1/auth/*` routes.

Default dev server (`app.main:app`) does not load this module — keeps `/v1` free of auth
until you opt in.

When building or testing auth, run:

    uvicorn app.main_auth:app --reload

Middleware order: session is registered before CORS so the browser-facing stack stays
CORS-on-the-outside (same as a typical FastAPI setup).
"""

from fastapi import APIRouter, FastAPI
from starlette.middleware.sessions import SessionMiddleware

from app.api.v1 import auth as auth_v1
from app.config import get_settings


def install_session_middleware(app: FastAPI) -> None:
    settings = get_settings()
    app.add_middleware(
        SessionMiddleware,
        secret_key=settings.secret_key,
        session_cookie="session",
        max_age=14 * 24 * 60 * 60,
        same_site="lax",
        https_only=False,
    )


def include_auth_routes(v1: APIRouter) -> None:
    v1.include_router(auth_v1.router)

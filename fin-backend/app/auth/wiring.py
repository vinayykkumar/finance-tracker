"""Session cookie + CSRF + `/v1/auth/*` routes.

Run the full API:

    uvicorn app.main:app --reload

Middleware order (outer → inner): RequestId → CORS → Session → CSRF → routes.
"""

import secrets

from fastapi import APIRouter, FastAPI
from starlette.middleware.sessions import SessionMiddleware

from app.config import get_settings
from app.middleware.csrf import CsrfProtectMiddleware


def install_auth_stack(app: FastAPI) -> None:
    """CSRF must be inner to Session so `request.session` is populated before CSRF runs."""
    app.add_middleware(CsrfProtectMiddleware)
    settings = get_settings()
    app.add_middleware(
        SessionMiddleware,
        secret_key=settings.secret_key,
        session_cookie="session",
        max_age=14 * 24 * 60 * 60,
        same_site=settings.session_same_site,
        https_only=settings.session_cookie_https_only,
    )


def new_csrf_token() -> str:
    return secrets.token_urlsafe(32)


def include_auth_routes(v1: APIRouter) -> None:
    # Deferred import: app.api.v1.auth imports new_csrf_token from this module,
    # so importing it eagerly at module load time creates a circular import.
    from app.api.v1 import auth as auth_v1

    v1.include_router(auth_v1.router)

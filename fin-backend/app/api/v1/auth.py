from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.session_user import session_user_id_optional
from app.db.session import get_db
from app.schemas.auth import LoginBody, RegisterBody, SessionResponse
from app.services.auth_service import (
    authenticate,
    create_user,
    get_user_by_email,
    get_user_by_id,
    user_public,
)

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", status_code=status.HTTP_201_CREATED)
async def register(
    request: Request,
    body: RegisterBody,
    db: AsyncSession = Depends(get_db),
) -> SessionResponse:
    existing = await get_user_by_email(db, body.email)
    if existing:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already registered")
    try:
        user = await create_user(db, body.email, body.password)
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already registered") from None
    request.session["user_id"] = str(user.id)
    return SessionResponse(authenticated=True, user=user_public(user))


@router.post("/login")
async def login(
    request: Request,
    body: LoginBody,
    db: AsyncSession = Depends(get_db),
) -> SessionResponse:
    user = await authenticate(db, body.email, body.password)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )
    request.session["user_id"] = str(user.id)
    return SessionResponse(authenticated=True, user=user_public(user))


@router.get("/session")
async def session(request: Request, db: AsyncSession = Depends(get_db)) -> SessionResponse:
    uid = session_user_id_optional(request)
    if uid is None:
        return SessionResponse(authenticated=False, user=None)
    user = await get_user_by_id(db, uid)
    if user is None:
        request.session.clear()
        return SessionResponse(authenticated=False, user=None)
    return SessionResponse(authenticated=True, user=user_public(user))


@router.post("/logout")
async def logout(request: Request) -> dict[str, bool]:
    request.session.clear()
    return {"ok": True}

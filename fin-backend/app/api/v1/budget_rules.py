from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.session_user import require_session_user_id
from app.db.session import get_db
from app.modules.budget_rules.schemas import BudgetRuleCreate, BudgetRuleRead, BudgetRuleUpdate
from app.modules.budget_rules.service import (
    BudgetRuleService,
    CurrencyMismatchError,
    RolloverConsistencyError,
)

router = APIRouter(prefix="/budget-rules", tags=["budget-rules"])


def get_budget_rule_service(db: AsyncSession = Depends(get_db)) -> BudgetRuleService:
    return BudgetRuleService(db)


@router.get("", response_model=list[BudgetRuleRead])
async def list_budget_rules(
    request: Request,
    category_slug: str | None = Query(default=None),
    svc: BudgetRuleService = Depends(get_budget_rule_service),
) -> list[BudgetRuleRead]:
    """All rule versions for the user, optionally filtered to one category,
    ordered by category then effective_from — i.e. the "rule timeline"."""
    uid = require_session_user_id(request)
    return await svc.list_versions(uid, category_slug)


@router.post("", response_model=BudgetRuleRead, status_code=status.HTTP_201_CREATED)
async def upsert_budget_rule(
    request: Request,
    body: BudgetRuleCreate,
    svc: BudgetRuleService = Depends(get_budget_rule_service),
) -> BudgetRuleRead:
    """Create a rule version, or update the existing version for the same
    (category_slug, effective_from)."""
    uid = require_session_user_id(request)
    try:
        return await svc.upsert(uid, body)
    except CurrencyMismatchError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e)
        ) from None
    except IntegrityError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Budget rule already exists for this category and effective date",
        ) from None


@router.get("/{rule_id}", response_model=BudgetRuleRead)
async def get_budget_rule(
    request: Request,
    rule_id: UUID,
    svc: BudgetRuleService = Depends(get_budget_rule_service),
) -> BudgetRuleRead:
    uid = require_session_user_id(request)
    row = await svc.get(uid, rule_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Budget rule not found")
    return row


@router.patch("/{rule_id}", response_model=BudgetRuleRead)
async def update_budget_rule(
    request: Request,
    rule_id: UUID,
    body: BudgetRuleUpdate,
    svc: BudgetRuleService = Depends(get_budget_rule_service),
) -> BudgetRuleRead:
    """Edit cap/rollover policy. category_slug and effective_from are immutable —
    delete and recreate to change either."""
    uid = require_session_user_id(request)
    try:
        row = await svc.update(uid, rule_id, body)
    except (CurrencyMismatchError, RolloverConsistencyError) as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e)
        ) from None
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Budget rule not found")
    return row


@router.delete("/{rule_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_budget_rule(
    request: Request,
    rule_id: UUID,
    svc: BudgetRuleService = Depends(get_budget_rule_service),
) -> None:
    uid = require_session_user_id(request)
    ok = await svc.delete(uid, rule_id)
    if not ok:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Budget rule not found")

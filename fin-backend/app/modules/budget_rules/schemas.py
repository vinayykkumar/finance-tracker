from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator, model_validator

from app.modules.budget_rules.calculation import ROLLOVER_MODES
from app.modules.categories.normalization import normalize_category_slug


class BudgetRuleCreate(BaseModel):
    """Create or upsert a rule version, keyed by (category_slug, effective_from)."""

    category_slug: str = Field(min_length=1, max_length=64)
    rule_type: str = Field(default="category_cap", max_length=32)
    cap_amount: Decimal = Field(gt=0, decimal_places=4, max_digits=19)
    currency: str = Field(default="INR", min_length=3, max_length=3)
    rollover_mode: str = Field(default="none")
    rollover_cap_amount: Decimal | None = Field(
        default=None, ge=0, decimal_places=4, max_digits=19
    )
    effective_from: date

    @field_validator("category_slug")
    @classmethod
    def _normalize_category(cls, v: str) -> str:
        return normalize_category_slug(v)

    @field_validator("currency")
    @classmethod
    def _upper_currency(cls, v: str) -> str:
        return v.upper()

    @field_validator("rollover_mode")
    @classmethod
    def _check_rollover_mode(cls, v: str) -> str:
        if v not in ROLLOVER_MODES:
            raise ValueError(f"rollover_mode must be one of {ROLLOVER_MODES}")
        return v

    @field_validator("effective_from")
    @classmethod
    def _check_first_of_month(cls, v: date) -> date:
        if v.day != 1:
            raise ValueError("effective_from must be the first day of a month")
        return v

    @model_validator(mode="after")
    def _check_rollover_cap_consistency(self) -> "BudgetRuleCreate":
        if self.rollover_mode == "capped" and self.rollover_cap_amount is None:
            raise ValueError("rollover_cap_amount is required when rollover_mode is 'capped'")
        if self.rollover_mode != "capped" and self.rollover_cap_amount is not None:
            raise ValueError("rollover_cap_amount is only allowed when rollover_mode is 'capped'")
        return self


class BudgetRuleUpdate(BaseModel):
    """Edit an existing rule version's cap/rollover policy.

    ``category_slug`` and ``effective_from`` are immutable — delete and
    recreate the version to change either. Cross-field rollover/cap
    consistency is checked by the service after merging with the existing row,
    since this is a partial update.
    """

    cap_amount: Decimal | None = Field(default=None, gt=0, decimal_places=4, max_digits=19)
    currency: str | None = Field(default=None, min_length=3, max_length=3)
    rollover_mode: str | None = None
    rollover_cap_amount: Decimal | None = Field(
        default=None, ge=0, decimal_places=4, max_digits=19
    )

    @field_validator("currency")
    @classmethod
    def _upper_currency(cls, v: str | None) -> str | None:
        return v.upper() if v is not None else None

    @field_validator("rollover_mode")
    @classmethod
    def _check_rollover_mode(cls, v: str | None) -> str | None:
        if v is not None and v not in ROLLOVER_MODES:
            raise ValueError(f"rollover_mode must be one of {ROLLOVER_MODES}")
        return v


class BudgetRuleRead(BaseModel):
    id: UUID
    user_id: UUID
    category_slug: str
    rule_type: str
    cap_amount: Decimal
    currency: str
    rollover_mode: str
    rollover_cap_amount: Decimal | None
    effective_from: date
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class CategoryPeriodSummary(BaseModel):
    """A category's computed cap/rollover/spend picture for one period.

    ``is_unbudgeted`` is true when no rule version covers this period for this
    category (whether because none was ever created, or because the earliest
    rule's ``effective_from`` is after this period) — in that case only
    ``actual_spend`` is meaningful and the rest are ``None``.
    """

    category_slug: str
    is_unbudgeted: bool
    rule_id: UUID | None = None
    rule_effective_from: date | None = None
    cap_amount: Decimal | None = None
    currency: str | None = None
    rollover_mode: str | None = None
    rollover_in: Decimal | None = None
    available: Decimal | None = None
    actual_spend: Decimal
    rollover_out: Decimal | None = None
    remaining: Decimal | None = None
    over_budget: bool


class UnbudgetedCategory(BaseModel):
    category_slug: str
    actual_spend: Decimal


class UnbudgetedSummary(BaseModel):
    actual_spend: Decimal
    categories: list[UnbudgetedCategory]


class BudgetSummaryResponse(BaseModel):
    year: int
    month: int
    period_start: datetime
    period_end: datetime
    categories: list[CategoryPeriodSummary]
    unbudgeted: UnbudgetedSummary


class ExplainEvent(BaseModel):
    at: datetime
    type: str
    description: str


class ExplainResponse(BaseModel):
    category_slug: str
    year: int
    month: int
    current: CategoryPeriodSummary
    #: A short, calm narrative of how `current`'s numbers were arrived at
    #: (cap, rollover source, what's available, spent/remaining or
    #: over-budget). Always derived from `current`, so it can't drift from it.
    summary_lines: list[str]
    #: Plain-language history of recent transaction/rule changes that bear
    #: on this category and period, newest first.
    events: list[ExplainEvent]

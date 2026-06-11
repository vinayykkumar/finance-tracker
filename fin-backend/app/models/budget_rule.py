import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Numeric,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

ROLLOVER_MODES = ("none", "full", "capped")


class BudgetRule(Base):
    """A versioned cap/rollover policy for one category.

    A row is one *version* of the policy for ``category_slug``, effective from
    ``effective_from`` (always the first of a month) until superseded by a later
    version of the same category (no explicit end date — superseding is implicit).

    For a given category and period, the active rule is the row with the latest
    ``effective_from <= period start``. A category with no such row for a period
    is "unbudgeted" for that period.
    """

    __tablename__ = "budget_rules"
    __table_args__ = (
        UniqueConstraint(
            "user_id", "category_slug", "effective_from", name="uq_budget_rule_user_cat_effective"
        ),
        CheckConstraint("cap_amount > 0", name="ck_budget_rule_cap_positive"),
        CheckConstraint(
            "rollover_mode IN ('none', 'full', 'capped')", name="ck_budget_rule_rollover_mode"
        ),
        CheckConstraint(
            "rollover_mode <> 'capped' OR rollover_cap_amount IS NOT NULL",
            name="ck_budget_rule_rollover_cap_required",
        ),
        CheckConstraint(
            "rollover_cap_amount IS NULL OR rollover_cap_amount >= 0",
            name="ck_budget_rule_rollover_cap_nonneg",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    category_slug: Mapped[str] = mapped_column(String(64), nullable=False)
    rule_type: Mapped[str] = mapped_column(String(32), nullable=False, default="category_cap")
    cap_amount: Mapped[Decimal] = mapped_column(Numeric(19, 4), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="INR")
    rollover_mode: Mapped[str] = mapped_column(String(16), nullable=False, default="none")
    rollover_cap_amount: Mapped[Decimal | None] = mapped_column(Numeric(19, 4), nullable=True)
    effective_from: Mapped[date] = mapped_column(Date, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    user = relationship("User", back_populates="budget_rules")

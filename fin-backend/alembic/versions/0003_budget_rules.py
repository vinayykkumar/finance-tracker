"""Budget rules: versioned cap/rollover policy per category, with backfill from budget_lines.

This migration is purely additive and safe to deploy with zero downtime:

* ``CREATE TABLE budget_rules`` only adds a new table — it does not lock, alter,
  or rewrite ``budget_lines`` or any other existing table.
* The data backfill is a single idempotent ``INSERT ... SELECT ... ON CONFLICT
  DO NOTHING``: for every existing ``budget_lines`` row it creates one
  ``budget_rules`` version with ``effective_from = first day of that row's
  month``, ``cap_amount = limit_amount`` and ``rollover_mode = 'none'`` —
  i.e. it reproduces today's "no rollover, fixed monthly cap" behavior exactly.
  It can be re-run safely (e.g. if new ``budget_lines`` rows are written by old
  clients during the rollout window).

``budget_lines`` and the existing ``/v1/budgets`` endpoints are left untouched
by this migration. Removing them is a separate, later "contract" migration once
both frontends have moved to ``/v1/budget-rules``.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0003_budget_rules"
down_revision: Union[str, None] = "0002_hardening"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "budget_rules",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("category_slug", sa.String(64), nullable=False),
        sa.Column(
            "rule_type", sa.String(32), nullable=False, server_default="category_cap"
        ),
        sa.Column("cap_amount", sa.Numeric(19, 4), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False, server_default="INR"),
        sa.Column("rollover_mode", sa.String(16), nullable=False, server_default="none"),
        sa.Column("rollover_cap_amount", sa.Numeric(19, 4), nullable=True),
        sa.Column("effective_from", sa.Date(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.UniqueConstraint(
            "user_id", "category_slug", "effective_from", name="uq_budget_rule_user_cat_effective"
        ),
        sa.CheckConstraint("cap_amount > 0", name="ck_budget_rule_cap_positive"),
        sa.CheckConstraint(
            "rollover_mode IN ('none', 'full', 'capped')", name="ck_budget_rule_rollover_mode"
        ),
        sa.CheckConstraint(
            "rollover_mode <> 'capped' OR rollover_cap_amount IS NOT NULL",
            name="ck_budget_rule_rollover_cap_required",
        ),
        sa.CheckConstraint(
            "rollover_cap_amount IS NULL OR rollover_cap_amount >= 0",
            name="ck_budget_rule_rollover_cap_nonneg",
        ),
        sa.CheckConstraint(
            "extract(day from effective_from) = 1", name="ck_budget_rule_effective_from_first_of_month"
        ),
    )
    op.create_index("ix_budget_rules_user_id", "budget_rules", ["user_id"])

    # Idempotent backfill: one rule version per existing budget_lines row,
    # preserving today's behavior (fixed cap, no rollover).
    op.execute(
        """
        INSERT INTO budget_rules (
            id, user_id, category_slug, rule_type, cap_amount, currency,
            rollover_mode, rollover_cap_amount, effective_from, created_at, updated_at
        )
        SELECT
            gen_random_uuid(),
            user_id,
            category_slug,
            'category_cap',
            limit_amount,
            currency,
            'none',
            NULL,
            make_date(year, month, 1),
            now(),
            now()
        FROM budget_lines
        ON CONFLICT (user_id, category_slug, effective_from) DO NOTHING
        """
    )


def downgrade() -> None:
    op.drop_index("ix_budget_rules_user_id", table_name="budget_rules")
    op.drop_table("budget_rules")

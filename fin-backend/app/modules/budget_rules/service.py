"""Use-cases for budget rules: CRUD, period summaries, and explanations.

Summaries are computed on read (see app.modules.budget_rules.calculation) —
there is no persisted "spent" total to keep in sync. Editing a transaction or
a rule doesn't trigger a recalculation step; the next summary/explain call
simply reflects the new data.
"""

from datetime import UTC, date, datetime
from uuid import UUID

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.budget_rule import BudgetRule
from app.modules.budget_rules.calculation import (
    ZERO,
    PeriodResult,
    RuleVersion,
    compute_chain,
    month_bounds,
    period_start_date,
)
from app.modules.budget_rules.repository import BudgetRuleRepository
from app.modules.budget_rules.schemas import (
    BudgetRuleCreate,
    BudgetRuleRead,
    BudgetRuleUpdate,
    BudgetSummaryResponse,
    CategoryPeriodSummary,
    ExplainEvent,
    ExplainResponse,
    UnbudgetedCategory,
    UnbudgetedSummary,
)
from app.modules.categories.normalization import normalize_category_slug
from app.modules.transactions.audit_repository import AuditRepository


class CurrencyMismatchError(ValueError):
    """A rule version's currency conflicts with other versions of the same category."""


class RolloverConsistencyError(ValueError):
    """rollover_mode / rollover_cap_amount combination is inconsistent."""


class BudgetRuleService:
    def __init__(self, session: AsyncSession) -> None:
        self._repo = BudgetRuleRepository(session)
        self._audit = AuditRepository(session)
        self._session = session

    # -- conversions ----------------------------------------------------

    def _to_read(self, row: BudgetRule) -> BudgetRuleRead:
        return BudgetRuleRead.model_validate(row)

    def _to_rule_version(self, row: BudgetRule) -> RuleVersion:
        return RuleVersion(
            id=row.id,
            category_slug=row.category_slug,
            cap_amount=row.cap_amount,
            currency=row.currency,
            rollover_mode=row.rollover_mode,
            rollover_cap_amount=row.rollover_cap_amount,
            effective_from=row.effective_from,
        )

    def _audit_payload(self, row: BudgetRule) -> dict:
        return {
            "category_slug": row.category_slug,
            "rule_type": row.rule_type,
            "effective_from": row.effective_from.isoformat(),
            "cap_amount": str(row.cap_amount),
            "currency": row.currency,
            "rollover_mode": row.rollover_mode,
            "rollover_cap_amount": (
                str(row.rollover_cap_amount) if row.rollover_cap_amount is not None else None
            ),
        }

    # -- CRUD -------------------------------------------------------------

    async def list_versions(
        self, user_id: UUID, category_slug: str | None = None
    ) -> list[BudgetRuleRead]:
        normalized = normalize_category_slug(category_slug) if category_slug else None
        rows = await self._repo.list_for_user(user_id, category_slug=normalized)
        result = [self._to_read(r) for r in rows]
        # End the implicit (autobegun) read transaction without expiring
        # already-loaded objects (expire_on_commit=False) — otherwise a
        # subsequent TransactionService call's `session.begin()` would raise
        # "a transaction is already begun on this session".
        await self._session.commit()
        return result

    async def get(self, user_id: UUID, rule_id: UUID) -> BudgetRuleRead | None:
        row = await self._repo.get_for_user(user_id, rule_id)
        result = self._to_read(row) if row else None
        await self._session.commit()
        return result

    async def _check_currency_continuity(
        self, user_id: UUID, category_slug: str, currency: str, *, exclude_id: UUID | None = None
    ) -> None:
        """All rule versions of a category must share one currency — multi-currency
        rollover would require conversion, which is out of scope."""
        versions = await self._repo.list_for_user(user_id, category_slug=category_slug)
        for v in versions:
            if exclude_id is not None and v.id == exclude_id:
                continue
            if v.currency != currency:
                raise CurrencyMismatchError(
                    f"category '{category_slug}' already has rule versions in {v.currency}; "
                    f"cannot add or change a version to {currency}"
                )

    async def upsert(self, user_id: UUID, body: BudgetRuleCreate) -> BudgetRuleRead:
        """Create a new rule version, or update the existing version for the
        same (category_slug, effective_from) — same upsert semantics as the
        legacy /v1/budgets endpoint."""
        existing = await self._repo.find_composite(user_id, body.category_slug, body.effective_from)
        await self._check_currency_continuity(
            user_id,
            body.category_slug,
            body.currency,
            exclude_id=existing.id if existing else None,
        )

        if existing:
            existing.rule_type = body.rule_type
            existing.cap_amount = body.cap_amount
            existing.currency = body.currency
            existing.rollover_mode = body.rollover_mode
            existing.rollover_cap_amount = body.rollover_cap_amount
            existing.updated_at = datetime.now(UTC)
            row = existing
            action = "budget_rule.update"
            await self._session.flush()
        else:
            row = BudgetRule(
                user_id=user_id,
                category_slug=body.category_slug,
                rule_type=body.rule_type,
                cap_amount=body.cap_amount,
                currency=body.currency,
                rollover_mode=body.rollover_mode,
                rollover_cap_amount=body.rollover_cap_amount,
                effective_from=body.effective_from,
            )
            action = "budget_rule.create"
            try:
                await self._repo.add(row)
            except IntegrityError:
                await self._session.rollback()
                raise

        await self._audit.append(
            user_id=user_id,
            action=action,
            entity_type="budget_rule",
            entity_id=row.id,
            payload=self._audit_payload(row),
        )
        await self._session.commit()
        return self._to_read(row)

    async def update(
        self, user_id: UUID, rule_id: UUID, body: BudgetRuleUpdate
    ) -> BudgetRuleRead | None:
        row = await self._repo.get_for_user(user_id, rule_id)
        if row is None:
            return None

        data = body.model_dump(exclude_unset=True)

        new_currency = data.get("currency", row.currency)
        if new_currency != row.currency:
            await self._check_currency_continuity(
                user_id, row.category_slug, new_currency, exclude_id=row.id
            )

        new_rollover_mode = data.get("rollover_mode", row.rollover_mode)
        if "rollover_cap_amount" in data:
            new_rollover_cap = data["rollover_cap_amount"]
        else:
            new_rollover_cap = row.rollover_cap_amount if new_rollover_mode == "capped" else None

        if new_rollover_mode == "capped" and new_rollover_cap is None:
            raise RolloverConsistencyError(
                "rollover_cap_amount is required when rollover_mode is 'capped'"
            )
        if new_rollover_mode != "capped" and new_rollover_cap is not None:
            raise RolloverConsistencyError(
                "rollover_cap_amount is only allowed when rollover_mode is 'capped'"
            )

        if "cap_amount" in data:
            row.cap_amount = data["cap_amount"]
        row.currency = new_currency
        row.rollover_mode = new_rollover_mode
        row.rollover_cap_amount = new_rollover_cap
        row.updated_at = datetime.now(UTC)

        await self._session.flush()
        await self._session.refresh(row)

        await self._audit.append(
            user_id=user_id,
            action="budget_rule.update",
            entity_type="budget_rule",
            entity_id=row.id,
            payload=self._audit_payload(row),
        )
        await self._session.commit()
        return self._to_read(row)

    async def delete(self, user_id: UUID, rule_id: UUID) -> bool:
        row = await self._repo.get_for_user(user_id, rule_id)
        if row is None:
            return False
        await self._audit.append(
            user_id=user_id,
            action="budget_rule.delete",
            entity_type="budget_rule",
            entity_id=row.id,
            payload=self._audit_payload(row),
        )
        await self._repo.delete(row)
        await self._session.commit()
        return True

    # -- summary ------------------------------------------------------------

    async def summary(self, user_id: UUID, year: int, month: int) -> BudgetSummaryResponse:
        target_period = period_start_date(year, month)
        period_start, period_end = month_bounds(year, month)

        all_rows = await self._repo.list_for_user(user_id)
        by_category: dict[str, list[RuleVersion]] = {}
        for row in all_rows:
            by_category.setdefault(row.category_slug, []).append(self._to_rule_version(row))

        if by_category:
            earliest = min(v.effective_from for versions in by_category.values() for v in versions)
            range_start_period = min(earliest, target_period)
        else:
            range_start_period = target_period
        range_start = month_bounds(range_start_period.year, range_start_period.month)[0]

        actuals = await self._repo.spend_by_category_and_month(user_id, range_start, period_end)

        target_categories = {cat for (cat, period) in actuals if period == target_period}
        all_categories = set(by_category.keys()) | target_categories

        categories: list[CategoryPeriodSummary] = []
        unbudgeted_categories: list[UnbudgetedCategory] = []
        unbudgeted_total = ZERO

        for cat_slug in sorted(all_categories):
            versions = by_category.get(cat_slug, [])
            cat_actuals = {p: amt for (c, p), amt in actuals.items() if c == cat_slug}
            result = compute_chain(versions, cat_actuals, target_period)
            if result.is_unbudgeted:
                unbudgeted_categories.append(
                    UnbudgetedCategory(category_slug=cat_slug, actual_spend=result.actual_spend)
                )
                unbudgeted_total += result.actual_spend
            else:
                categories.append(self._period_result_to_summary(cat_slug, result))

        response = BudgetSummaryResponse(
            year=year,
            month=month,
            period_start=period_start,
            period_end=period_end,
            categories=categories,
            unbudgeted=UnbudgetedSummary(
                actual_spend=unbudgeted_total, categories=unbudgeted_categories
            ),
        )
        await self._session.commit()
        return response

    def _period_result_to_summary(
        self, category_slug: str, result: PeriodResult
    ) -> CategoryPeriodSummary:
        rule = result.rule
        assert rule is not None
        return CategoryPeriodSummary(
            category_slug=category_slug,
            is_unbudgeted=False,
            rule_id=rule.id,
            rule_effective_from=rule.effective_from,
            cap_amount=result.cap_amount,
            currency=rule.currency,
            rollover_mode=rule.rollover_mode,
            rollover_in=result.rollover_in,
            available=result.available,
            actual_spend=result.actual_spend,
            rollover_out=result.rollover_out,
            remaining=result.remaining,
            over_budget=result.over_budget,
        )

    # -- explain --------------------------------------------------------------

    async def explain(
        self, user_id: UUID, year: int, month: int, category_slug: str
    ) -> ExplainResponse:
        normalized = normalize_category_slug(category_slug)
        period_start, period_end = month_bounds(year, month)

        summary = await self.summary(user_id, year, month)
        current = next(
            (c for c in summary.categories if c.category_slug == normalized), None
        )
        if current is None:
            unb = next(
                (c for c in summary.unbudgeted.categories if c.category_slug == normalized), None
            )
            current = CategoryPeriodSummary(
                category_slug=normalized,
                is_unbudgeted=True,
                actual_spend=unb.actual_spend if unb else ZERO,
                over_budget=False,
            )

        events_rows = await self._audit.list_for_user(
            user_id, entity_types=["ledger_transaction", "budget_rule"]
        )
        events: list[ExplainEvent] = []
        for row in events_rows:
            description = self._describe_event(
                action=row.action,
                entity_type=row.entity_type,
                payload=row.payload or {},
                category_slug=normalized,
                period_start=period_start,
                period_end=period_end,
            )
            if description is not None:
                events.append(ExplainEvent(at=row.created_at, type=row.action, description=description))

        response = ExplainResponse(
            category_slug=normalized,
            year=year,
            month=month,
            current=current,
            events=events,
        )
        await self._session.commit()
        return response

    def _describe_event(
        self,
        *,
        action: str,
        entity_type: str,
        payload: dict,
        category_slug: str,
        period_start: datetime,
        period_end: datetime,
    ) -> str | None:
        if entity_type == "ledger_transaction":
            return self._describe_transaction_event(
                action, payload, category_slug, period_start, period_end
            )
        if entity_type == "budget_rule":
            return self._describe_budget_rule_event(action, payload, category_slug, period_start)
        return None

    @staticmethod
    def _norm_or_none(slug: str | None) -> str | None:
        if slug is None:
            return None
        try:
            return normalize_category_slug(slug)
        except ValueError:
            return None

    @staticmethod
    def _in_period(iso: str | None, period_start: datetime, period_end: datetime) -> bool:
        if not iso:
            return False
        try:
            ts = datetime.fromisoformat(iso)
        except ValueError:
            return False
        if ts.tzinfo is None:
            # SQLite (tests) round-trips DateTime(timezone=True) as naive;
            # all stored timestamps are UTC instants by convention.
            ts = ts.replace(tzinfo=UTC)
        return period_start <= ts < period_end

    def _describe_transaction_event(
        self,
        action: str,
        payload: dict,
        category_slug: str,
        period_start: datetime,
        period_end: datetime,
    ) -> str | None:
        cur_cat = self._norm_or_none(payload.get("category_slug"))
        cur_occ = payload.get("occurred_at")
        cur_relevant = cur_cat == category_slug and self._in_period(cur_occ, period_start, period_end)

        old_cat_raw = payload.get("category_slug_old")
        old_occ_raw = payload.get("occurred_at_old")
        old_cat = self._norm_or_none(old_cat_raw) if old_cat_raw is not None else cur_cat
        old_occ = old_occ_raw if old_occ_raw is not None else cur_occ
        old_relevant = old_cat == category_slug and self._in_period(old_occ, period_start, period_end)

        if not (cur_relevant or old_relevant):
            return None

        if action == "transaction.create":
            return (
                f"Transaction created: {payload.get('amount')} in '{payload.get('category_slug')}' "
                f"(occurred {payload.get('occurred_at')})"
            )
        if action == "transaction.delete":
            return (
                f"Transaction deleted: {payload.get('amount')} from '{payload.get('category_slug')}' "
                f"(occurred {payload.get('occurred_at')})"
            )
        if action == "transaction.update":
            changes = []
            if "amount" in payload:
                changes.append(f"amount {payload['amount']['old']} -> {payload['amount']['new']}")
            if old_cat_raw is not None:
                changes.append(f"category '{old_cat_raw}' -> '{payload.get('category_slug')}'")
            if old_occ_raw is not None:
                changes.append(f"date {old_occ_raw} -> {payload.get('occurred_at')}")
            if not changes:
                return "Transaction updated"
            return "Transaction updated: " + ", ".join(changes)
        return None

    def _describe_budget_rule_event(
        self, action: str, payload: dict, category_slug: str, period_start: datetime
    ) -> str | None:
        if self._norm_or_none(payload.get("category_slug")) != category_slug:
            return None
        eff_raw = payload.get("effective_from")
        try:
            eff_date = date.fromisoformat(eff_raw) if eff_raw else None
        except ValueError:
            eff_date = None
        if eff_date is None or eff_date > period_start.date():
            return None

        cap = payload.get("cap_amount")
        currency = payload.get("currency")
        rollover_mode = payload.get("rollover_mode")
        if action == "budget_rule.create":
            return (
                f"Rule created for '{category_slug}' effective {eff_raw}: "
                f"cap {cap} {currency}, rollover {rollover_mode}"
            )
        if action == "budget_rule.update":
            return (
                f"Rule for '{category_slug}' effective {eff_raw} updated: "
                f"cap {cap} {currency}, rollover {rollover_mode}"
            )
        if action == "budget_rule.delete":
            return f"Rule for '{category_slug}' effective {eff_raw} deleted (was cap {cap} {currency})"
        return None

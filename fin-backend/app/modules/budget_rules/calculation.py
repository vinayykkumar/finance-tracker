"""Pure rules-engine math: period boundaries, rule selection, and the
cap/rollover chain.

Nothing in this module touches the database — it operates on plain dataclasses
so it can be unit-tested exhaustively without a session/fixtures, and so the
service layer can call it once with whatever data it has fetched.

Period model
------------
A "period" is a calendar month, represented by its first-of-month ``date``
(e.g. ``date(2026, 6, 1)`` for June 2026), in UTC. ``month_bounds`` derives the
``[start, end)`` UTC datetime range used to filter ``occurred_at``.

Rule model
----------
``RuleVersion`` is one versioned cap/rollover policy for a category, effective
from ``effective_from`` (always first-of-month) until superseded by a later
version of the same category. ``active_rule_for_period`` picks the version
with the latest ``effective_from <= period_start``.

Rollover chain
--------------
``compute_chain`` walks every period from a category's earliest rule version
through the target period, carrying ``rollover_in`` forward period-to-period.
This is what makes the engine correct under retroactive edits: change a past
rule or a past transaction, and the next call simply walks the same chain with
different inputs — there is no separate "recalculation" step.
"""

from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal

ROLLOVER_MODES = ("none", "full", "capped")

ZERO = Decimal("0")


def month_bounds(year: int, month: int) -> tuple[datetime, datetime]:
    """Return the ``[start, end)`` UTC bounds of a calendar month.

    ``start`` is ``00:00:00`` UTC on the first of the month (inclusive);
    ``end`` is ``00:00:00`` UTC on the first of the following month
    (exclusive). A transaction with ``occurred_at == end`` belongs to the
    *next* month, not this one.
    """
    start = datetime(year, month, 1, tzinfo=UTC)
    if month == 12:
        end = datetime(year + 1, 1, 1, tzinfo=UTC)
    else:
        end = datetime(year, month + 1, 1, tzinfo=UTC)
    return start, end


def period_start_date(year: int, month: int) -> date:
    """The canonical first-of-month ``date`` identifying a period."""
    return date(year, month, 1)


def add_months(period: date, n: int) -> date:
    """Add ``n`` months to a first-of-month date, returning a first-of-month date.

    ``n`` may be negative. ``period`` must already be the first of a month.
    """
    month_index = period.year * 12 + (period.month - 1) + n
    year, month0 = divmod(month_index, 12)
    return date(year, month0 + 1, 1)


def is_first_of_month(d: date) -> bool:
    return d.day == 1


@dataclass(frozen=True)
class RuleVersion:
    """One versioned cap/rollover policy for a category."""

    id: object
    category_slug: str
    cap_amount: Decimal
    currency: str
    rollover_mode: str  # "none" | "full" | "capped"
    rollover_cap_amount: Decimal | None
    effective_from: date  # always first-of-month


def active_rule_for_period(
    versions: list[RuleVersion], period_start: date
) -> RuleVersion | None:
    """The rule version governing ``period_start``: the latest version with
    ``effective_from <= period_start``, or ``None`` if the category has no
    rule covering this period (i.e. unbudgeted).
    """
    candidates = [v for v in versions if v.effective_from <= period_start]
    if not candidates:
        return None
    return max(candidates, key=lambda v: v.effective_from)


@dataclass(frozen=True)
class PeriodResult:
    """The computed cap/rollover/spend picture for one category in one period."""

    period_start: date
    rule: RuleVersion | None
    cap_amount: Decimal | None
    rollover_in: Decimal
    available: Decimal | None
    actual_spend: Decimal
    rollover_out: Decimal
    remaining: Decimal | None
    over_budget: bool
    is_unbudgeted: bool


def compute_period(
    *,
    period_start: date,
    rule: RuleVersion | None,
    rollover_in: Decimal,
    actual_spend: Decimal,
) -> PeriodResult:
    """Compute one period's result given the rule active for it and the
    rollover carried in from the previous period.

    ``rollover_in`` is always >= 0: a period that overspends its ``available``
    amount produces ``rollover_out = 0`` (clamped), never a negative carry —
    overspending in one period never reduces a future period's cap.
    """
    if rule is None:
        return PeriodResult(
            period_start=period_start,
            rule=None,
            cap_amount=None,
            rollover_in=ZERO,
            available=None,
            actual_spend=actual_spend,
            rollover_out=ZERO,
            remaining=None,
            over_budget=False,
            is_unbudgeted=True,
        )

    available = rule.cap_amount + rollover_in
    surplus = available - actual_spend  # may be negative (over budget)

    if rule.rollover_mode == "none":
        rollover_out = ZERO
    elif rule.rollover_mode == "full":
        rollover_out = max(surplus, ZERO)
    elif rule.rollover_mode == "capped":
        cap = rule.rollover_cap_amount if rule.rollover_cap_amount is not None else ZERO
        rollover_out = min(max(surplus, ZERO), cap)
    else:  # pragma: no cover - guarded by schema validation
        raise ValueError(f"Unknown rollover_mode: {rule.rollover_mode!r}")

    return PeriodResult(
        period_start=period_start,
        rule=rule,
        cap_amount=rule.cap_amount,
        rollover_in=rollover_in,
        available=available,
        actual_spend=actual_spend,
        rollover_out=rollover_out,
        remaining=surplus,
        over_budget=actual_spend > available,
        is_unbudgeted=False,
    )


def compute_chain(
    versions: list[RuleVersion],
    monthly_actuals: dict[date, Decimal],
    target_period_start: date,
) -> PeriodResult:
    """Compute the result for ``target_period_start`` by walking the rollover
    chain from the category's earliest rule version up to the target.

    ``monthly_actuals`` maps period-start dates to actual spend for that
    period; periods with no entry are treated as zero spend. The chain starts
    at the earliest ``effective_from`` across ``versions`` — a category can't
    roll over budget from before it had a budget. If ``target_period_start``
    is before the earliest rule (or there are no versions at all), the
    category is unbudgeted for that period and the chain is not walked.
    """
    if not versions:
        actual = monthly_actuals.get(target_period_start, ZERO)
        return compute_period(
            period_start=target_period_start, rule=None, rollover_in=ZERO, actual_spend=actual
        )

    earliest = min(v.effective_from for v in versions)
    if target_period_start < earliest:
        actual = monthly_actuals.get(target_period_start, ZERO)
        return compute_period(
            period_start=target_period_start, rule=None, rollover_in=ZERO, actual_spend=actual
        )

    rollover_in = ZERO
    period = earliest
    result: PeriodResult | None = None
    while period <= target_period_start:
        rule = active_rule_for_period(versions, period)
        actual = monthly_actuals.get(period, ZERO)
        result = compute_period(
            period_start=period, rule=rule, rollover_in=rollover_in, actual_spend=actual
        )
        rollover_in = result.rollover_out
        period = add_months(period, 1)

    assert result is not None
    return result

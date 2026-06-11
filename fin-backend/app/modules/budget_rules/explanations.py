"""Plain-language copy for the budget "why is this number what it is" view.

Pure, presentation-layer helpers (no DB access) so the copy can be
unit-tested directly against the same numbers the API returns in
``CategoryPeriodSummary`` — the goal is that the numbers embedded in this
text and the structured fields on ``current`` can never drift apart, because
they're derived from the exact same values in the same call.

Two kinds of copy:

* :func:`summary_lines` — a short, calm narrative of *this period's* numbers:
  the cap, where any rolled-over amount came from, what's available, and
  what's been spent/left (or how far over budget). This is the primary
  explanation.
* :func:`describe_event` — turns one audit-log event (a transaction edit or a
  rule change) into a plain-language sentence, for the secondary "what
  changed recently" history.
"""

from datetime import UTC, date, datetime
from decimal import Decimal

from app.modules.budget_rules.schemas import CategoryPeriodSummary
from app.modules.categories.normalization import normalize_category_slug

ZERO = Decimal("0")
DEFAULT_CURRENCY = "INR"


def format_money(amount: Decimal, currency: str | None) -> str:
    return f"{amount:,.2f} {currency or DEFAULT_CURRENCY}"


def format_period(value: str | date) -> str:
    """``date(2026, 5, 1)`` / ``"2026-05-01"`` -> ``"May 2026"``."""
    d = date.fromisoformat(value) if isinstance(value, str) else value
    return d.strftime("%B %Y")


def format_date(value: str) -> str:
    """An ISO timestamp -> ``"20 Jul 2026"``."""
    ts = datetime.fromisoformat(value)
    return ts.strftime("%d %b %Y")


def _amount_phrase(amount: Decimal, currency: str) -> str:
    if amount < ZERO:
        return f"an expense of {format_money(-amount, currency)}"
    if amount > ZERO:
        return f"a credit of {format_money(amount, currency)}"
    return f"a {format_money(ZERO, currency)} entry"


def summary_lines(current: CategoryPeriodSummary, category_slug: str) -> list[str]:
    """A short narrative of how ``current``'s numbers were arrived at.

    Every amount mentioned here is read directly from ``current``, so if the
    underlying numbers change, this text changes with them — there's no
    separate copy to keep in sync.
    """
    if current.is_unbudgeted:
        lines = [
            f"No budget rule covers '{category_slug}' this month, "
            f"so this spend isn't checked against a cap."
        ]
        if current.actual_spend != ZERO:
            lines.append(
                f"You've spent {format_money(current.actual_spend, DEFAULT_CURRENCY)} "
                f"here so far this month."
            )
        return lines

    currency = current.currency or DEFAULT_CURRENCY
    cap = current.cap_amount or ZERO
    rollover_in = current.rollover_in or ZERO
    available = current.available or ZERO
    actual = current.actual_spend
    remaining = current.remaining or ZERO
    rollover_out = current.rollover_out or ZERO

    lines = [f"Your cap for '{category_slug}' this month is {format_money(cap, currency)}."]

    if rollover_in != ZERO:
        lines.append(
            f"{format_money(rollover_in, currency)} rolled over from last month "
            f"because you had budget left over."
        )
        lines.append(f"That makes {format_money(available, currency)} available this month.")

    if current.over_budget:
        over_by = -remaining
        lines.append(
            f"You've spent {format_money(actual, currency)}, which is "
            f"{format_money(over_by, currency)} over what's available."
        )
    else:
        lines.append(
            f"You've spent {format_money(actual, currency)}, "
            f"leaving {format_money(remaining, currency)}."
        )

    if current.rollover_mode and current.rollover_mode != "none" and rollover_out != ZERO:
        lines.append(
            f"At today's numbers, {format_money(rollover_out, currency)} "
            f"would roll over into next month."
        )

    return lines


# ---------------------------------------------------------------------------
# Event history — "what changed recently"
# ---------------------------------------------------------------------------


def _norm_or_none(slug: str | None) -> str | None:
    if slug is None:
        return None
    try:
        return normalize_category_slug(slug)
    except ValueError:
        return None


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


def describe_transaction_event(
    *,
    action: str,
    payload: dict,
    category_slug: str,
    currency: str,
    period_start: datetime,
    period_end: datetime,
) -> str | None:
    cur_cat = _norm_or_none(payload.get("category_slug"))
    cur_occ = payload.get("occurred_at")
    cur_relevant = cur_cat == category_slug and _in_period(cur_occ, period_start, period_end)

    old_cat_raw = payload.get("category_slug_old")
    old_occ_raw = payload.get("occurred_at_old")
    old_cat = _norm_or_none(old_cat_raw) if old_cat_raw is not None else cur_cat
    old_occ = old_occ_raw if old_occ_raw is not None else cur_occ
    old_relevant = old_cat == category_slug and _in_period(old_occ, period_start, period_end)

    if not (cur_relevant or old_relevant):
        return None

    if action == "transaction.create":
        amount = Decimal(payload.get("amount", "0"))
        return (
            f"On {format_date(payload['occurred_at'])}, {_amount_phrase(amount, currency)} "
            f"was added to '{category_slug}'."
        )
    if action == "transaction.delete":
        amount = Decimal(payload.get("amount", "0"))
        return (
            f"On {format_date(payload['occurred_at'])}, {_amount_phrase(amount, currency)} "
            f"was removed from '{category_slug}'."
        )
    if action == "transaction.update":
        clauses: list[str] = []
        if "amount" in payload:
            old_amt = abs(Decimal(payload["amount"]["old"]))
            new_amt = abs(Decimal(payload["amount"]["new"]))
            clauses.append(
                f"its amount changed from {format_money(old_amt, currency)} "
                f"to {format_money(new_amt, currency)}"
            )
        if old_cat_raw is not None:
            new_cat = payload.get("category_slug")
            if old_cat == category_slug:
                clauses.append(f"it was moved from '{category_slug}' to '{new_cat}'")
            else:
                clauses.append(f"it was moved into '{category_slug}' from '{old_cat_raw}'")
        if old_occ_raw is not None:
            clauses.append(
                f"its date changed from {format_date(old_occ_raw)} "
                f"to {format_date(payload['occurred_at'])}"
            )
        if not clauses:
            clauses.append("it was edited")
        return "A transaction was updated: " + "; ".join(clauses) + "."
    return None


def describe_budget_rule_event(
    *,
    action: str,
    payload: dict,
    category_slug: str,
    period_start: datetime,
) -> str | None:
    if _norm_or_none(payload.get("category_slug")) != category_slug:
        return None
    eff_raw = payload.get("effective_from")
    try:
        eff_date = date.fromisoformat(eff_raw) if eff_raw else None
    except ValueError:
        eff_date = None
    if eff_date is None or eff_date > period_start.date():
        return None

    currency = payload.get("currency") or DEFAULT_CURRENCY
    cap = Decimal(payload.get("cap_amount", "0"))
    rollover_mode = payload.get("rollover_mode")
    rollover_clause = ""
    if rollover_mode == "full":
        rollover_clause = ", with any unused amount carrying over to the next month"
    elif rollover_mode == "capped":
        rollover_cap_raw = payload.get("rollover_cap_amount")
        if rollover_cap_raw is not None:
            rollover_clause = (
                f", with up to {format_money(Decimal(rollover_cap_raw), currency)} "
                f"carrying over to the next month"
            )

    period_label = format_period(eff_date)
    if action == "budget_rule.create":
        return (
            f"A budget rule for '{category_slug}' took effect from {period_label}: "
            f"a {format_money(cap, currency)} cap{rollover_clause}."
        )
    if action == "budget_rule.update":
        return (
            f"The budget rule for '{category_slug}' (effective from {period_label}) "
            f"was updated to a {format_money(cap, currency)} cap{rollover_clause}."
        )
    if action == "budget_rule.delete":
        return f"The budget rule for '{category_slug}' (effective from {period_label}) was removed."
    return None


def describe_event(
    *,
    action: str,
    entity_type: str,
    payload: dict,
    category_slug: str,
    currency: str,
    period_start: datetime,
    period_end: datetime,
) -> str | None:
    if entity_type == "ledger_transaction":
        return describe_transaction_event(
            action=action,
            payload=payload,
            category_slug=category_slug,
            currency=currency,
            period_start=period_start,
            period_end=period_end,
        )
    if entity_type == "budget_rule":
        return describe_budget_rule_event(
            action=action, payload=payload, category_slug=category_slug, period_start=period_start
        )
    return None

"""Unit tests for the pure rules-engine math (no DB).

Each test is tied back to an item in the edge-case list from the design
discussion (see PR description / docs). Numbers in test names refer to that
list where useful.
"""

from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from app.modules.budget_rules.calculation import (
    PeriodResult,
    RuleVersion,
    active_rule_for_period,
    add_months,
    compute_chain,
    compute_period,
    month_bounds,
)

D = Decimal


def rule(
    *,
    cap: str,
    effective_from: date,
    rollover_mode: str = "none",
    rollover_cap: str | None = None,
    category_slug: str = "groceries",
    currency: str = "INR",
    rule_id: object = "r",
) -> RuleVersion:
    return RuleVersion(
        id=rule_id,
        category_slug=category_slug,
        cap_amount=D(cap),
        currency=currency,
        rollover_mode=rollover_mode,
        rollover_cap_amount=D(rollover_cap) if rollover_cap is not None else None,
        effective_from=effective_from,
    )


# ---------------------------------------------------------------------------
# month_bounds / add_months — period & timezone edge cases
# ---------------------------------------------------------------------------


def test_month_bounds_basic():
    start, end = month_bounds(2026, 6)
    assert start == datetime(2026, 6, 1, tzinfo=UTC)
    assert end == datetime(2026, 7, 1, tzinfo=UTC)


def test_month_bounds_december_rolls_into_next_year():
    start, end = month_bounds(2026, 12)
    assert start == datetime(2026, 12, 1, tzinfo=UTC)
    assert end == datetime(2027, 1, 1, tzinfo=UTC)


def test_month_bounds_exact_boundary_instant_belongs_to_next_month():
    """Edge case: the instant 2026-07-01T00:00:00Z is the *end* of June (exclusive)
    and the *start* of July (inclusive) — start-inclusive/end-exclusive avoids
    double counting or dropping a transaction posted exactly at midnight UTC."""
    _, june_end = month_bounds(2026, 6)
    july_start, _ = month_bounds(2026, 7)
    assert june_end == july_start
    boundary = datetime(2026, 7, 1, tzinfo=UTC)
    assert not (month_bounds(2026, 6)[0] <= boundary < month_bounds(2026, 6)[1])
    assert month_bounds(2026, 7)[0] <= boundary < month_bounds(2026, 7)[1]


def test_add_months_within_year():
    assert add_months(date(2026, 6, 1), 1) == date(2026, 7, 1)
    assert add_months(date(2026, 6, 1), -1) == date(2026, 5, 1)


def test_add_months_across_year_boundary():
    assert add_months(date(2026, 12, 1), 1) == date(2027, 1, 1)
    assert add_months(date(2026, 1, 1), -1) == date(2025, 12, 1)


# ---------------------------------------------------------------------------
# active_rule_for_period — rule versioning / selection
# ---------------------------------------------------------------------------


def test_active_rule_none_when_no_versions():
    assert active_rule_for_period([], date(2026, 6, 1)) is None


def test_active_rule_none_when_period_before_first_rule():
    versions = [rule(cap="15000", effective_from=date(2026, 6, 1))]
    assert active_rule_for_period(versions, date(2026, 5, 1)) is None


def test_active_rule_picks_latest_effective_from_le_period():
    jan = rule(cap="10000", effective_from=date(2026, 1, 1), rule_id="jan")
    jul = rule(cap="20000", effective_from=date(2026, 7, 1), rule_id="jul")
    versions = [jan, jul]
    assert active_rule_for_period(versions, date(2026, 6, 1)) is jan
    assert active_rule_for_period(versions, date(2026, 7, 1)) is jul
    assert active_rule_for_period(versions, date(2026, 12, 1)) is jul


def test_active_rule_inserted_between_two_existing_versions():
    """A rule with effective_from strictly between two existing versions only
    governs the periods between its own effective_from and the next version's."""
    jan = rule(cap="10000", effective_from=date(2026, 1, 1), rule_id="jan")
    jul = rule(cap="20000", effective_from=date(2026, 7, 1), rule_id="jul")
    apr = rule(cap="15000", effective_from=date(2026, 4, 1), rule_id="apr")
    versions = [jan, jul, apr]

    assert active_rule_for_period(versions, date(2026, 3, 1)) is jan
    assert active_rule_for_period(versions, date(2026, 4, 1)) is apr
    assert active_rule_for_period(versions, date(2026, 6, 1)) is apr
    assert active_rule_for_period(versions, date(2026, 7, 1)) is jul


# ---------------------------------------------------------------------------
# compute_period — caps, rollover modes, negative carry
# ---------------------------------------------------------------------------


def test_compute_period_unbudgeted_when_no_rule():
    result = compute_period(
        period_start=date(2026, 6, 1), rule=None, rollover_in=D("0"), actual_spend=D("850")
    )
    assert result.is_unbudgeted is True
    assert result.cap_amount is None
    assert result.available is None
    assert result.remaining is None
    assert result.over_budget is False
    assert result.rollover_out == D("0")
    assert result.actual_spend == D("850")


def test_compute_period_rollover_mode_none_never_carries_surplus():
    r = rule(cap="10000", effective_from=date(2026, 6, 1), rollover_mode="none")
    result = compute_period(
        period_start=date(2026, 6, 1), rule=r, rollover_in=D("0"), actual_spend=D("4000")
    )
    assert result.available == D("10000")
    assert result.remaining == D("6000")
    assert result.rollover_out == D("0")
    assert result.over_budget is False


def test_compute_period_rollover_mode_full_carries_positive_surplus():
    r = rule(cap="10000", effective_from=date(2026, 6, 1), rollover_mode="full")
    result = compute_period(
        period_start=date(2026, 6, 1), rule=r, rollover_in=D("0"), actual_spend=D("4000")
    )
    assert result.rollover_out == D("6000")


def test_compute_period_capped_rollover_clamps_at_rollover_cap():
    r = rule(
        cap="10000",
        effective_from=date(2026, 6, 1),
        rollover_mode="capped",
        rollover_cap="2000",
    )
    # Surplus of 6000, but rollover_cap_amount limits carry-forward to 2000.
    result = compute_period(
        period_start=date(2026, 6, 1), rule=r, rollover_in=D("0"), actual_spend=D("4000")
    )
    assert result.remaining == D("6000")
    assert result.rollover_out == D("2000")


@pytest.mark.parametrize("rollover_mode,rollover_cap", [("none", None), ("full", None), ("capped", "5000")])
def test_compute_period_overspend_never_produces_negative_rollover_out(rollover_mode, rollover_cap):
    """Edge case: negative carry. An over-budget period must roll forward 0,
    never a negative amount — overspending this month never reduces next
    month's available cap."""
    r = rule(
        cap="10000",
        effective_from=date(2026, 6, 1),
        rollover_mode=rollover_mode,
        rollover_cap=rollover_cap,
    )
    result = compute_period(
        period_start=date(2026, 6, 1), rule=r, rollover_in=D("0"), actual_spend=D("15000")
    )
    assert result.over_budget is True
    assert result.remaining == D("-5000")
    assert result.rollover_out == D("0")
    assert result.rollover_out >= D("0")


def test_compute_period_negative_actual_spend_from_net_refunds():
    """Edge case: negative carry / refund-heavy category. Inflows exceeding
    outflows in a category produce negative actual_spend, which increases the
    surplus beyond the cap itself."""
    r = rule(cap="10000", effective_from=date(2026, 6, 1), rollover_mode="full")
    result = compute_period(
        period_start=date(2026, 6, 1), rule=r, rollover_in=D("0"), actual_spend=D("-500")
    )
    assert result.available == D("10000")
    assert result.remaining == D("10500")
    assert result.rollover_out == D("10500")
    assert result.over_budget is False


def test_compute_period_over_budget_boundary_is_not_over_when_exactly_equal():
    r = rule(cap="10000", effective_from=date(2026, 6, 1))
    result = compute_period(
        period_start=date(2026, 6, 1), rule=r, rollover_in=D("0"), actual_spend=D("10000")
    )
    assert result.over_budget is False
    assert result.remaining == D("0")


# ---------------------------------------------------------------------------
# compute_chain — rollover propagation across periods, retroactive edits
# ---------------------------------------------------------------------------


def test_compute_chain_no_versions_is_unbudgeted():
    result = compute_chain([], {date(2026, 6, 1): D("850")}, date(2026, 6, 1))
    assert result.is_unbudgeted is True
    assert result.actual_spend == D("850")


def test_compute_chain_target_before_earliest_rule_is_unbudgeted():
    versions = [rule(cap="10000", effective_from=date(2026, 6, 1))]
    result = compute_chain(versions, {date(2026, 5, 1): D("300")}, date(2026, 5, 1))
    assert result.is_unbudgeted is True
    assert result.actual_spend == D("300")


def test_compute_chain_first_period_has_zero_rollover_in():
    versions = [rule(cap="10000", effective_from=date(2026, 6, 1), rollover_mode="full")]
    result = compute_chain(versions, {date(2026, 6, 1): D("4000")}, date(2026, 6, 1))
    assert result.rollover_in == D("0")
    assert result.available == D("10000")
    assert result.rollover_out == D("6000")


def test_compute_chain_propagates_surplus_across_months():
    versions = [rule(cap="10000", effective_from=date(2026, 6, 1), rollover_mode="full")]
    actuals = {
        date(2026, 6, 1): D("4000"),  # surplus 6000 -> rolls into July
        date(2026, 7, 1): D("9000"),  # available 16000, spend 9000 -> surplus 7000
    }
    result = compute_chain(versions, actuals, date(2026, 7, 1))
    assert result.rollover_in == D("6000")
    assert result.available == D("16000")
    assert result.remaining == D("7000")
    assert result.rollover_out == D("7000")


def test_compute_chain_back_dated_transaction_changes_downstream_periods():
    """Edge case: a transaction's occurred_at is edited from July into June.
    Re-running compute_chain with the updated monthly_actuals changes both
    June's and July's results — there is no separate recalculation step."""
    versions = [rule(cap="10000", effective_from=date(2026, 6, 1), rollover_mode="full")]

    before = {date(2026, 6, 1): D("4000"), date(2026, 7, 1): D("9000")}
    after_backdate = {date(2026, 6, 1): D("5500"), date(2026, 7, 1): D("7500")}  # moved 1500 from Jul -> Jun

    before_jul = compute_chain(versions, before, date(2026, 7, 1))
    after_jul = compute_chain(versions, after_backdate, date(2026, 7, 1))

    assert before_jul.rollover_in == D("6000")
    # June surplus shrinks from 6000 to 4500, so July's rollover_in shrinks too.
    assert after_jul.rollover_in == D("4500")
    # July spend also dropped by 1500, so remaining increases by (1500 carried away) + 1500 (less spend)
    assert after_jul.available == D("14500")
    assert after_jul.remaining == D("7000")


def test_compute_chain_retroactive_rule_added_after_spend_exists():
    """Edge case: a rule with effective_from in the past is created after
    transactions for that month already exist. Spend that was previously
    unbudgeted becomes budgeted, and rollover starts from that period."""
    actuals = {
        date(2026, 5, 1): D("3000"),
        date(2026, 6, 1): D("4000"),
    }

    # Before the retroactive rule: May has no rule at all.
    before = compute_chain([], actuals, date(2026, 5, 1))
    assert before.is_unbudgeted is True

    # User retroactively adds a rule effective 2026-05-01.
    versions = [rule(cap="5000", effective_from=date(2026, 5, 1), rollover_mode="full")]
    may_after = compute_chain(versions, actuals, date(2026, 5, 1))
    assert may_after.is_unbudgeted is False
    assert may_after.available == D("5000")
    assert may_after.rollover_out == D("2000")

    june_after = compute_chain(versions, actuals, date(2026, 6, 1))
    assert june_after.rollover_in == D("2000")
    assert june_after.available == D("7000")


def test_compute_chain_rule_inserted_mid_chain_only_affects_its_window():
    """A rule version inserted between two existing versions changes
    rollover/cap only for the periods from its effective_from up to the next
    version's effective_from."""
    jan = rule(cap="10000", effective_from=date(2026, 1, 1), rollover_mode="full", rule_id="jan")
    apr = rule(cap="20000", effective_from=date(2026, 4, 1), rollover_mode="full", rule_id="apr")

    actuals = {
        date(2026, 1, 1): D("8000"),
        date(2026, 2, 1): D("8000"),
        date(2026, 3, 1): D("8000"),
        date(2026, 4, 1): D("8000"),
    }

    before = compute_chain([jan, apr], actuals, date(2026, 4, 1))
    # Jan-Mar each surplus 2000 (cap 10000), accumulating: 2000, 4000, 6000 -> rollover_in to Apr = 6000
    assert before.rollover_in == D("6000")
    assert before.available == D("26000")  # 20000 + 6000

    mar = rule(cap="15000", effective_from=date(2026, 3, 1), rollover_mode="full", rule_id="mar")
    after = compute_chain([jan, mar, apr], actuals, date(2026, 4, 1))
    # Jan surplus 2000, Feb surplus 2000 (rollover_in 2000) -> rollover_in to Mar = 4000
    # Mar: available = 15000 + 4000 = 19000, spend 8000 -> surplus 11000 -> rollover_in to Apr = 11000
    assert after.rollover_in == D("11000")
    assert after.available == D("31000")  # 20000 + 11000


def test_compute_chain_rollover_mode_change_uses_source_period_mode():
    """If a category's rollover_mode changes from 'full' to 'none' starting a
    later period, the *earlier* period's surplus (earned under 'full') still
    rolls forward; the later period (now 'none') doesn't pass anything on."""
    full_rule = rule(cap="10000", effective_from=date(2026, 5, 1), rollover_mode="full", rule_id="full")
    none_rule = rule(cap="10000", effective_from=date(2026, 6, 1), rollover_mode="none", rule_id="none")
    versions = [full_rule, none_rule]

    actuals = {
        date(2026, 5, 1): D("4000"),  # surplus 6000, rolls into June (May was 'full')
        date(2026, 6, 1): D("4000"),  # available 16000, surplus 12000, but mode is 'none'
        date(2026, 7, 1): D("4000"),
    }

    june = compute_chain(versions, actuals, date(2026, 6, 1))
    assert june.rollover_in == D("6000")
    assert june.available == D("16000")
    assert june.rollover_out == D("0")  # June's rule is 'none' -> nothing carries to July

    july = compute_chain(versions, actuals, date(2026, 7, 1))
    assert july.rollover_in == D("0")
    assert july.available == D("10000")


def test_compute_chain_deleting_earliest_rule_resets_chain_start():
    """Edge case: deleting the earliest rule version shifts the chain's
    starting point to the next-earliest version, resetting rollover_in to 0
    for what is now the first period — even if it previously had carry-in."""
    jan = rule(cap="10000", effective_from=date(2026, 1, 1), rollover_mode="full", rule_id="jan")
    apr = rule(cap="20000", effective_from=date(2026, 4, 1), rollover_mode="full", rule_id="apr")
    actuals = {
        date(2026, 1, 1): D("8000"),
        date(2026, 2, 1): D("8000"),
        date(2026, 3, 1): D("8000"),
        date(2026, 4, 1): D("8000"),
    }

    with_jan = compute_chain([jan, apr], actuals, date(2026, 4, 1))
    assert with_jan.rollover_in == D("6000")

    # Jan rule deleted -> Apr is now the earliest version.
    without_jan = compute_chain([apr], actuals, date(2026, 4, 1))
    assert without_jan.rollover_in == D("0")
    assert without_jan.available == D("20000")

    # Jan-Mar are now unbudgeted.
    jan_after = compute_chain([apr], actuals, date(2026, 1, 1))
    assert jan_after.is_unbudgeted is True


def test_compute_chain_zero_spend_period_with_active_rule_is_not_unbudgeted():
    versions = [rule(cap="10000", effective_from=date(2026, 6, 1), rollover_mode="full")]
    result = compute_chain(versions, {}, date(2026, 6, 1))
    assert result.is_unbudgeted is False
    assert result.actual_spend == D("0")
    assert result.rollover_out == D("10000")


def test_compute_chain_long_chain_is_walked_in_order():
    """Sanity check over a longer chain (also exercises the year-boundary in
    add_months) with capped rollover bounding accumulation."""
    versions = [
        rule(cap="1000", effective_from=date(2025, 11, 1), rollover_mode="capped", rollover_cap="500")
    ]
    actuals = {
        date(2025, 11, 1): D("700"),  # surplus 300 -> rollover_in Dec = 300
        date(2025, 12, 1): D("700"),  # available 1300, surplus 600 -> capped at 500
        date(2026, 1, 1): D("700"),  # available 1500, surplus 800 -> capped at 500
    }
    result = compute_chain(versions, actuals, date(2026, 1, 1))
    assert result.rollover_in == D("500")
    assert result.available == D("1500")
    assert result.remaining == D("800")
    assert result.rollover_out == D("500")


def test_period_result_is_immutable_dataclass():
    r = rule(cap="10000", effective_from=date(2026, 6, 1))
    result = compute_period(period_start=date(2026, 6, 1), rule=r, rollover_in=D("0"), actual_spend=D("0"))
    assert isinstance(result, PeriodResult)
    with pytest.raises(AttributeError):
        result.actual_spend = D("1")  # type: ignore[misc]

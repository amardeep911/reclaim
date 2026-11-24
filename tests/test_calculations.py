from datetime import date, datetime, timedelta, timezone

import pytest

from utils import calculations as calc
from utils.constants import CONSUMED, CRAVING_RESISTED, SUCCESS

UTC = timezone.utc


def test_standard_drinks_beer_who():
    # 330 ml * 5% * 0.789 g/ml = 13.02 g -> 1.3 standard drinks at 10 g
    assert calc.standard_drinks(1, 330, 5.0, 10) == pytest.approx(1.3, abs=0.01)


def test_standard_drinks_scales_with_quantity_and_region():
    us = calc.standard_drinks(2, 150, 12.5, 14)
    who = calc.standard_drinks(2, 150, 12.5, 10)
    assert who > us
    assert calc.standard_drinks(2, 150, 12.5, 10) == pytest.approx(2 * calc.standard_drinks(1, 150, 12.5, 10), abs=0.01)


@pytest.mark.parametrize("args", [(0, 330, 5, 10), (1, 0, 5, 10), (1, 330, 0, 10), (1, 330, 5, 0)])
def test_standard_drinks_invalid_inputs_are_zero(args):
    assert calc.standard_drinks(*args) == 0


def test_cigarettes_avoided_never_negative():
    assert calc.cigarettes_avoided(10, 3, 12) == 18
    assert calc.cigarettes_avoided(10, 1, 25) == 0


def test_smoking_savings():
    # baseline 10/day for 2 days, smoked 5 -> 15 avoided * 18 = 270
    assert calc.smoking_savings(10, 18, 2, 5) == 270
    assert calc.smoking_spent(5, 18) == 90


def test_alcohol_savings_uses_logged_cost_or_typical_spend():
    day_costs = {date(2026, 11, 1): 300.0, date(2026, 11, 3): None}
    # spent = 300 (logged) + 500 (estimated)
    assert calc.alcohol_spent(day_costs, 500) == 800
    # expected over 14 days at 3.5 days/week = 7 occasions * 500 = 3500 -> saved 2700
    assert calc.alcohol_savings(3.5, 500, 14, day_costs) == 2700


def test_alcohol_savings_floor_at_zero():
    heavy = {date(2026, 11, d): 1000.0 for d in range(1, 8)}
    assert calc.alcohol_savings(1, 500, 7, heavy) == 0


def test_current_streak_resets_on_consumption_but_not_before_start():
    start = datetime(2026, 11, 1, tzinfo=UTC)
    now = datetime(2026, 11, 4, tzinfo=UTC)
    assert calc.current_streak(start, None, now) == timedelta(days=3)
    assert calc.current_streak(start, datetime(2026, 11, 3, 12, tzinfo=UTC), now) == timedelta(hours=12)
    # consumption before tracking started doesn't shorten the streak
    assert calc.current_streak(start, datetime(2026, 10, 1, tzinfo=UTC), now) == timedelta(days=3)


def test_free_days_counts_completed_days_only():
    start, today = date(2026, 11, 1), date(2026, 11, 8)  # 7 completed days (1st..7th)
    assert calc.free_days(start, today, set()) == 7
    assert calc.free_days(start, today, {date(2026, 11, 2), date(2026, 11, 8)}) == 6  # today ignored
    assert calc.free_days(today, today, set()) == 0


def test_summarize_hours():
    s = calc.summarize_hours([SUCCESS, SUCCESS, CRAVING_RESISTED, CONSUMED])
    assert s == {"success": 2, "craving_resisted": 1, "consumed": 1, "free": 3, "tracked": 4}


def test_percent_handles_zero():
    assert calc.percent(3, 0) == 0
    assert calc.percent(1, 3) == 33


def test_milestone_progress():
    m = calc.milestone_progress(30)
    assert m["next"] == (72, "3 days")
    assert [h for h, _ in m["reached"]] == [1, 24]
    assert m["pct"] == round(100 * (30 - 24) / (72 - 24))
    assert calc.milestone_progress(10000)["next"] is None


def test_savings_projection():
    p = calc.savings_projection(700, 7)
    assert p["daily"] == 100 and p["weekly"] == 700 and p["yearly"] == 36500


# ---------------------------------------------------------------- Phase 2

def test_longest_streak_includes_current_and_ignores_pre_start_events():
    start = datetime(2026, 11, 1, tzinfo=UTC)
    now = datetime(2026, 11, 10, tzinfo=UTC)
    events = [datetime(2026, 10, 1, tzinfo=UTC), datetime(2026, 11, 5, tzinfo=UTC), datetime(2026, 11, 6, tzinfo=UTC)]
    assert calc.longest_streak(start, events, now) == timedelta(days=4)  # Nov 1 -> Nov 5 and Nov 6 -> Nov 10
    assert calc.longest_streak(start, [datetime(2026, 11, 9, tzinfo=UTC)], now) == timedelta(days=8)
    assert calc.longest_streak(start, [], now) == timedelta(days=9)


def test_consecutive_days():
    today = date(2026, 11, 10)
    days = {date(2026, 11, d) for d in (1, 2, 3, 4, 7, 8, 9)}
    assert calc.consecutive_days(days, today) == {"current": 3, "best": 4}  # current run ends yesterday
    assert calc.consecutive_days(days | {today}, today)["current"] == 4
    assert calc.consecutive_days(set(), today) == {"current": 0, "best": 0}


def _days(start: date, n: int) -> set[date]:
    return {start + timedelta(days=i) for i in range(n)}


def test_reduced_week_needs_lower_total_and_real_tracking():
    start, today = date(2026, 11, 1), date(2026, 11, 9)
    low = {d: 3.0 for d in _days(start, 8)}  # 21 per week vs baseline 70
    assert calc.reduced_week(low, _days(start, 8), start, today, 10)
    assert not calc.reduced_week(low, _days(start, 3), start, today, 10)  # not tracked enough
    assert not calc.reduced_week({d: 12.0 for d in _days(start, 8)}, _days(start, 8), start, today, 10)
    assert not calc.reduced_week(low, _days(start, 8), start, date(2026, 11, 5), 10)  # no complete week yet
    assert not calc.reduced_week(low, _days(start, 8), start, today, 0)  # no baseline


def test_best_week():
    start, today = date(2026, 11, 1), date(2026, 11, 15)  # two complete weeks: Nov 1-7, Nov 8-14
    tracked = _days(start, 14)
    improving = {d: (10.0 if d.day <= 7 else 4.0) for d in tracked}
    assert calc.best_week(improving, tracked, start, today)
    worsening = {d: (4.0 if d.day <= 7 else 10.0) for d in tracked}
    assert not calc.best_week(worsening, tracked, start, today)
    assert not calc.best_week(improving, tracked, start, date(2026, 11, 10))  # only one complete week


def test_allocate_savings_fills_goals_in_order():
    assert calc.allocate_savings([1000, 500, 2000], 1200) == [1000, 200, 0]
    assert calc.allocate_savings([100], -50) == [0]
    assert calc.allocate_savings([], 500) == []


def test_craving_stats():
    cravings = [
        {"resisted": True, "intensity": 8, "trigger": "Stress"},
        {"resisted": True, "intensity": 4, "trigger": "Stress"},
        {"resisted": False, "intensity": 6, "trigger": "After eating"},
        {"resisted": True, "intensity": 2, "trigger": None},
    ]
    s = calc.craving_stats(cravings)
    assert (s["total"], s["resisted"], s["consumed"], s["resisted_pct"]) == (4, 3, 1, 75)
    assert s["avg_intensity"] == 5.0
    assert s["top_triggers"][0] == ("Stress", 2)
    assert calc.craving_stats([])["avg_intensity"] == 0.0


def test_waking_fraction_only_counts_waking_hours():
    assert calc.waking_fraction(datetime(2026, 11, 25, 2, 45), 7, 23) == 0      # asleep: nothing accrues
    assert calc.waking_fraction(datetime(2026, 11, 25, 15, 0), 7, 23) == 0.5
    assert calc.waking_fraction(datetime(2026, 11, 25, 23, 30), 7, 23) == 1
    assert calc.waking_fraction(datetime(2026, 11, 25, 12, 0), 0, 24) == 0.5


def test_effective_days():
    assert calc.effective_days(date(2026, 11, 20), date(2026, 11, 25), 0.5) == 5.5
    assert calc.effective_days(date(2026, 11, 25), date(2026, 11, 25), 0.25) == 0.25
    assert calc.effective_days(date(2026, 11, 26), date(2026, 11, 25), 0.9) == 0  # starts in the future


def test_savings_stay_flat_overnight():
    # baseline 14/day at ₹18 – at 2:45 AM with waking hours 7–23 nothing has been "saved" yet
    early = calc.waking_fraction(datetime(2026, 11, 25, 2, 45), 7, 23)
    assert calc.smoking_savings(14, 18, early, 0) == 0
    # by bedtime the whole day's baseline counts
    assert calc.smoking_savings(14, 18, 1.0, 0) == 252

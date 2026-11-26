from datetime import date

import pandas as pd

from services import analytics_service as an
from utils import calculations as calc
from utils.insights import (
    InsightInput, baseline_comparison, build_insights, coping_pattern, peak_window, time_pattern, tracking_trend,
    trigger_pattern, weekday_pattern, window_label,
)


def base(**kw) -> InsightInput:
    return InsightInput(habit="smoking", units="cigarettes", free_label="smoke-free", **kw)


# ---------------------------------------------------------------- insight rules

def test_peak_window_wraps_midnight():
    assert peak_window([16, 17, 17, 9]) == (16, 3)
    assert peak_window([23, 0, 0, 12]) == (23, 3)
    assert window_label(16) == "4 PM and 6 PM"
    assert window_label(23) == "11 PM and 1 AM"


def test_time_pattern_needs_enough_data_and_a_real_peak():
    assert time_pattern([16, 17, 16], "x") is None                     # too few
    assert time_pattern([1, 5, 9, 13, 17, 21], "x") is None             # spread out, no peak
    ins = time_pattern([16, 16, 17, 17, 9, 11], "You experience most smoking cravings")
    assert ins.text == "You experience most smoking cravings between 4 PM and 6 PM (4 of 6)."


def test_trigger_pattern_ignores_ties_and_small_samples():
    assert trigger_pattern(["Stress"] * 4) is None
    assert trigger_pattern(["Stress"] * 3 + ["Boredom"] * 3) is None    # tie: no single answer
    ins = trigger_pattern(["After eating"] * 3 + ["Stress", "Boredom"])
    assert "“After eating” is your most common craving trigger (3 of 5" in ins.text


def test_weekday_pattern():
    assert weekday_pattern([0, 1, 2, 3], "cravings") is None
    ins = weekday_pattern([4, 4, 4, 4, 0, 1, 2, 3], "cravings")
    assert ins.text.startswith("Fridays stand out: 4 of your 8 cravings")


def test_baseline_comparison_wording_is_never_shaming():
    down = baseline_comparison(base(avg_per_day=6, baseline_per_day=10, observed_days=7))
    assert down.kind == "progress" and "decreased by 40%" in down.text
    up = baseline_comparison(base(avg_per_day=12, baseline_per_day=10, observed_days=7))
    assert "fresh start" in up.text and "fail" not in up.text.lower()
    assert baseline_comparison(base(avg_per_day=6, baseline_per_day=10, observed_days=2)) is None


def test_tracking_trend():
    assert "improved" in tracking_trend(base(tracked_days_this_week=6, tracked_days_last_week=3)).text
    assert tracking_trend(base(tracked_days_this_week=3, tracked_days_last_week=3)) is None
    assert tracking_trend(base(tracked_days_this_week=0, tracked_days_last_week=0)) is None


def test_coping_pattern_needs_repeated_use():
    assert coping_pattern([("Short walk", True)] * 2) is None
    ins = coping_pattern([("Short walk", True)] * 3 + [("Distraction", False)] * 3)
    assert "“Short walk” works well for you – you resisted 3 of 3" in ins.text


def test_build_insights_with_no_data_says_nothing():
    assert build_insights(base()) == []


def test_build_insights_orders_progress_first():
    d = base(avg_per_day=5, baseline_per_day=10, observed_days=7, tracked_hours=20, free_hours=18,
             craving_hours=[16, 16, 17, 17, 9], craving_triggers=["Stress"] * 3 + ["Habit"] * 2)
    kinds = [i.kind for i in build_insights(d)]
    assert kinds == sorted(kinds, key=["progress", "pattern", "tip"].index)
    assert len(kinds) >= 3


# ---------------------------------------------------------------- range maths

def test_observed_days():
    start, today = date(2026, 11, 10), date(2026, 11, 26)
    assert calc.observed_days(date(2026, 11, 1), date(2026, 11, 20), start, today, 0.5) == 11
    assert calc.observed_days(date(2026, 11, 20), today, start, today, 0.5) == 6.5
    assert calc.observed_days(date(2026, 11, 1), date(2026, 11, 5), start, today, 0.5) == 0


def test_change_pct():
    assert calc.change_pct(6, 10) == -40 and calc.change_pct(5, 0) is None


# ---------------------------------------------------------------- frames

def _rd(consumption: pd.DataFrame, first: date, last: date) -> an.RangeData:
    return an.RangeData("smoking", first, last, (last - first).days + 1, (last - first).days,
                        consumption, pd.DataFrame(), pd.DataFrame())


def test_daily_and_weekly_frames_zero_fill_and_flag_partial_weeks():
    c = pd.DataFrame({"local_date": [date(2026, 11, 2), date(2026, 11, 2), date(2026, 11, 10)],
                      "quantity": [2.0, 1.0, 4.0]})
    daily = an.daily_frame(_rd(c, date(2026, 11, 1), date(2026, 11, 14)))
    assert len(daily) == 14 and daily["quantity"].sum() == 7
    assert daily.loc[daily["date"] == date(2026, 11, 2), "quantity"].item() == 3
    weekly = an.period_frame(daily, "quantity", "week")
    # 1 Nov 2026 is a Sunday: weeks start 26 Oct (partial), 2 Nov (full), 9 Nov (partial – ends 15 Nov)
    assert list(weekly["label"]) == ["26 Oct", "02 Nov", "09 Nov"]
    assert list(weekly["partial"]) == [True, False, True]
    assert list(weekly["value"]) == [0, 3, 4]


def test_avoided_frame_running_total_never_negative():
    daily = pd.DataFrame({"date": [date(2026, 11, 1), date(2026, 11, 2), date(2026, 11, 3)],
                          "quantity": [2.0, 25.0, 0.0]})
    out = an.avoided_frame(daily, baseline=10, today=date(2026, 11, 3), today_frac=0.5)
    assert list(out["value"]) == [8, 0, 5]

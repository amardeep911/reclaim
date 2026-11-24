"""Statistics built from the user's real records (dashboard + consumption page).

Phase 3 will add trend analysis and behavioural insights here.
"""

from collections import defaultdict
from datetime import date, datetime, timedelta

import pandas as pd

from services.database_service import UserContext
from services.tracking_service import count_hours, get_consumption, get_hourly_logs, get_last_consumption
from utils import calculations as calc
from utils.constants import ALCOHOL, CRAVING_RESISTED, DRINKING_FREQUENCY, SMOKING, SUCCESS
from utils.datetime_utils import (
    day_bounds_utc, generate_day_slots, local_now, local_today, now_utc, parse_date, range_bounds_utc,
    sleep_slots,
)


def _num(value, default: float = 0.0) -> float:
    return float(value) if value is not None else default


def tracking_start(ctx: UserContext, addiction_type: str) -> date:
    ap = ctx.addiction_profiles[addiction_type]
    return parse_date(ap.get("tracking_start_date")) or local_today(ctx.tz)


def alcohol_days_per_week(ap: dict) -> float:
    if ap.get("drinking_days_per_week") is not None:
        return _num(ap["drinking_days_per_week"])
    return DRINKING_FREQUENCY.get(ap.get("drinking_frequency") or "", ("", 0.0))[1]


def consumption_frame(rows: list[dict], tz) -> pd.DataFrame:
    """Consumption rows as a DataFrame with local date/hour columns."""
    if not rows:
        return pd.DataFrame(columns=["id", "occurred_at", "local_time", "local_date", "quantity",
                                     "standard_drinks", "cost"])
    df = pd.DataFrame(rows)
    df["local_time"] = df["occurred_at"].apply(lambda t: t.astimezone(tz))
    df["local_date"] = df["local_time"].apply(lambda t: t.date())
    for col in ("quantity", "standard_drinks", "cost", "volume_ml", "abv_percent"):
        df[col] = pd.to_numeric(df[col], errors="coerce") if col in df else float("nan")
    return df


def today_fraction(ctx: UserContext) -> float:
    """Share of today's waking hours that have passed – baselines accrue only while you're awake."""
    return calc.waking_fraction(local_now(ctx.tz), ctx.wake_hour, ctx.sleep_hour)


def addiction_overview(ctx: UserContext, addiction_type: str) -> dict:
    """Lifetime + streak numbers for one addiction, since its tracking start date."""
    tz, now = ctx.tz, now_utc()
    today = local_today(tz)
    ap = ctx.addiction_profiles[addiction_type]
    start_day = tracking_start(ctx, addiction_type)
    start = day_bounds_utc(start_day, tz)[0]

    df = consumption_frame(get_consumption(start, None, addiction_type), tz)
    days = calc.effective_days(start_day, today, today_fraction(ctx))
    actual = float(df["quantity"].sum()) if not df.empty else 0.0
    consumption_dates = set(df["local_date"]) if not df.empty else set()
    streak = calc.current_streak(start, get_last_consumption(addiction_type), now)
    best = calc.longest_streak(start, list(df["occurred_at"]) if not df.empty else [], now)
    daily = df.groupby("local_date")["quantity"].sum().to_dict() if not df.empty else {}

    stats = {
        "start_day": start_day,
        "days": days,
        "actual": actual,
        "streak": streak,
        "streak_hours": streak.total_seconds() / 3600,
        "best_streak": best,
        "best_streak_hours": best.total_seconds() / 3600,
        "daily_totals": {d: float(q) for d, q in daily.items()},
        "consumption_dates": consumption_dates,
        "free_days": calc.free_days(start_day, today, consumption_dates),
        # Only completed hours the user actually logged.
        "tracked_free_hours": count_hours(addiction_type, (SUCCESS, CRAVING_RESISTED), until=now),
        "craving_hours": count_hours(addiction_type, (CRAVING_RESISTED,), until=now),
    }

    if addiction_type == SMOKING:
        baseline, cost = _num(ap.get("baseline_per_day")), _num(ap.get("cost_per_unit"))
        stats.update(
            baseline=baseline,
            avoided=calc.cigarettes_avoided(baseline, days, actual),
            saved=calc.smoking_savings(baseline, cost, days, actual),
            spent=calc.smoking_spent(actual, cost),
        )
    else:
        per_week, per_occasion = alcohol_days_per_week(ap), _num(ap.get("spend_per_occasion"))
        day_costs: dict[date, float | None] = {}
        if not df.empty:
            for day, group in df.groupby("local_date"):
                costs = group["cost"].dropna()
                day_costs[day] = float(costs.sum()) if not costs.empty else None
        stats.update(
            baseline=per_week,
            occasions=len(consumption_dates),
            avoided=calc.avoided_drinking_occasions(per_week, days, len(consumption_dates)),
            saved=calc.alcohol_savings(per_week, per_occasion, days, day_costs),
            spent=calc.alcohol_spent(day_costs, per_occasion),
            standard_drinks=float(df["standard_drinks"].sum()) if not df.empty else 0.0,
        )
    stats["projection"] = calc.savings_projection(stats["saved"], days)
    stats["milestones"] = calc.milestone_progress(stats["streak_hours"])
    return stats


def day_summary(ctx: UserContext, addiction_type: str, day: date) -> dict:
    """Hourly + consumption summary for one local day. Only finished hours the user logged count.

    Hour totals include every logged hour of the day (sleep hours too); the tracking-completion
    figures only look at the waking window.
    """
    tz, now = ctx.tz, now_utc()
    start, end = day_bounds_utc(day, tz)
    slots = generate_day_slots(day, tz, ctx.wake_hour, ctx.sleep_hour)
    completed = [s for s in slots if s.end <= now]
    completed_starts = {s.start for s in completed}

    logs = [row for row in get_hourly_logs(start, end, addiction_type)
            if row["slot_start"] + timedelta(hours=1) <= now]
    hours = calc.summarize_hours([row["status"] for row in logs])
    window_tracked = sum(1 for row in logs if row["slot_start"] in completed_starts)

    df = consumption_frame(get_consumption(start, end, addiction_type), tz)
    first = df["local_time"].min() if not df.empty else None
    return {
        **hours,
        "window_hours": len(slots),
        "completed_hours": len(completed),
        "window_tracked": window_tracked,
        "completion_pct": calc.percent(window_tracked, len(completed)),
        "quantity": float(df["quantity"].sum()) if not df.empty else 0.0,
        "standard_drinks": float(df["standard_drinks"].sum()) if addiction_type == ALCOHOL and not df.empty else 0.0,
        "first_time": first,
    }


def sleep_hours_to_log(ctx: UserContext, addiction_type: str) -> list[datetime]:
    """Untracked hours from last night, once the night is over. Empty if there's nothing to offer."""
    night = sleep_slots(local_today(ctx.tz), ctx.tz, ctx.wake_hour, ctx.sleep_hour)
    if not night or night[-1].end > now_utc():
        return []
    logged = {row["slot_start"] for row in get_hourly_logs(night[0].start, night[-1].end, addiction_type)}
    return [s.start for s in night if s.start not in logged]


def daily_series(ctx: UserContext, addiction_type: str, days: int = 7) -> pd.DataFrame:
    """Quantity per local day for the last `days` days (zero-filled)."""
    tz = ctx.tz
    today = local_today(tz)
    first = today - timedelta(days=days - 1)
    start, end = range_bounds_utc(first, today, tz)
    df = consumption_frame(get_consumption(start, end, addiction_type), tz)
    totals = defaultdict(float)
    for _, row in df.iterrows():
        totals[row["local_date"]] += row["quantity"]
    dates = [first + timedelta(days=i) for i in range(days)]
    return pd.DataFrame({"date": dates, "quantity": [totals[d] for d in dates]})


def period_totals(ctx: UserContext, addiction_type: str) -> dict:
    """Today / last 7 days / last 30 days totals and averages for the consumption page."""
    tz = ctx.tz
    today = local_today(tz)
    start_day = tracking_start(ctx, addiction_type)
    month_first = today - timedelta(days=29)
    start, end = range_bounds_utc(min(month_first, start_day), today, tz)
    df = consumption_frame(get_consumption(start, end, addiction_type), tz)

    def total(since: date, col: str = "quantity") -> float:
        if df.empty:
            return 0.0
        return float(df.loc[df["local_date"] >= since, col].sum())

    tracked_days = max(1, (today - start_day).days + 1)
    since_start = total(start_day)
    return {
        "today": total(today),
        "week": total(today - timedelta(days=6)),
        "month": total(month_first),
        "avg_per_day": since_start / tracked_days if (today - start_day).days < 30 else total(month_first) / 30,
        "week_std": total(today - timedelta(days=6), "standard_drinks"),
        "month_std": total(month_first, "standard_drinks"),
        "frame": df,
    }

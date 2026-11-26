"""Statistics built from the user's real records (dashboard + consumption page).

Phase 3 will add trend analysis and behavioural insights here.
"""

from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timedelta

import pandas as pd

from services.craving_service import get_cravings
from services.database_service import UserContext
from services.tracking_service import count_hours, get_consumption, get_hourly_logs, get_last_consumption
from utils import calculations as calc
from utils.constants import ALCOHOL, CONSUMED, CRAVING_RESISTED, DRINKING_FREQUENCY, SMOKING, SUCCESS
from utils.datetime_utils import (
    day_bounds_utc, generate_day_slots, local_now, local_today, now_utc, parse_date, range_bounds_utc,
    sleep_slots,
)
from utils.insights import InsightInput


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


# ---------------------------------------------------------------------------
# Phase 3: analytics over a date range
# ---------------------------------------------------------------------------

@dataclass
class RangeData:
    addiction: str
    first: date
    last: date
    days: float              # observed days (partial today counts by waking hours)
    completed_days: int      # whole days that have finished
    consumption: pd.DataFrame
    hourly: pd.DataFrame     # finished, logged hours only
    cravings: pd.DataFrame

    @property
    def empty(self) -> bool:
        return self.days <= 0


def _with_time_parts(df: pd.DataFrame, column: str, tz) -> pd.DataFrame:
    df["local_time"] = df[column].apply(lambda t: t.astimezone(tz))
    df["local_date"] = df["local_time"].apply(lambda t: t.date())
    df["hour"] = df["local_time"].apply(lambda t: t.hour)
    df["weekday"] = df["local_time"].apply(lambda t: t.weekday())
    return df


def load_range(ctx: UserContext, addiction_type: str, first: date, last: date) -> RangeData:
    """Everything logged for one habit between two local dates (clamped to tracking start and today)."""
    tz, today = ctx.tz, local_today(ctx.tz)
    start_day = tracking_start(ctx, addiction_type)
    first, last = max(first, start_day), min(last, today)
    completed = max(0, (min(last, today - timedelta(days=1)) - first).days + 1)
    days = calc.observed_days(first, last, start_day, today, today_fraction(ctx))
    if first > last:
        empty = pd.DataFrame()
        return RangeData(addiction_type, first, last, 0.0, 0, empty, empty, empty)

    lo, hi = range_bounds_utc(first, last, tz)
    now = now_utc()
    consumption = consumption_frame(get_consumption(lo, hi, addiction_type), tz)
    if not consumption.empty:
        consumption = _with_time_parts(consumption, "occurred_at", tz)

    hourly_rows = [r for r in get_hourly_logs(lo, hi, addiction_type) if r["slot_start"] + timedelta(hours=1) <= now]
    hourly = _with_time_parts(pd.DataFrame(hourly_rows), "slot_start", tz) if hourly_rows else pd.DataFrame()

    craving_rows = get_cravings(lo, hi, addiction_type)
    cravings = _with_time_parts(pd.DataFrame(craving_rows), "occurred_at", tz) if craving_rows else pd.DataFrame()
    return RangeData(addiction_type, first, last, days, completed, consumption, hourly, cravings)


def period_metrics(ctx: UserContext, rd: RangeData) -> dict:
    """Headline numbers for a range – used by the analytics KPIs and the weekly/monthly reports."""
    ap = ctx.addiction_profiles[rd.addiction]
    c, h, cr = rd.consumption, rd.hourly, rd.cravings
    quantity = float(c["quantity"].sum()) if not c.empty else 0.0
    statuses = list(h["status"]) if not h.empty else []
    hours = calc.summarize_hours(statuses)
    resisted = int(cr["resisted"].sum()) if not cr.empty else 0
    m = {
        "days": rd.days,
        "quantity": quantity,
        "avg_per_day": quantity / rd.days if rd.days >= 1 else quantity,
        "tracked_hours": hours["tracked"],
        "free_hours": hours["free"],
        "free_pct": calc.percent(hours["free"], hours["tracked"]),
        "tracked_days": int(h["local_date"].nunique()) if not h.empty else 0,
        "cravings": len(cr),
        "cravings_resisted": resisted,
        "resisted_pct": calc.percent(resisted, len(cr)),
        "avg_intensity": round(float(cr["intensity"].mean()), 1) if not cr.empty else 0.0,
    }
    if rd.addiction == SMOKING:
        baseline, cost = _num(ap.get("baseline_per_day")), _num(ap.get("cost_per_unit"))
        m.update(baseline=baseline,
                 avoided=calc.cigarettes_avoided(baseline, rd.days, quantity),
                 saved=calc.smoking_savings(baseline, cost, rd.days, quantity),
                 spent=calc.smoking_spent(quantity, cost))
    else:
        per_week, per_occasion = alcohol_days_per_week(ap), _num(ap.get("spend_per_occasion"))
        day_costs: dict[date, float | None] = {}
        if not c.empty:
            for day, group in c.groupby("local_date"):
                costs = group["cost"].dropna()
                day_costs[day] = float(costs.sum()) if not costs.empty else None
        last_complete = rd.first + timedelta(days=rd.completed_days - 1)
        drinking_complete = sum(1 for d in day_costs if d <= last_complete) if rd.completed_days else 0
        m.update(baseline=per_week * _num(ap.get("drinks_per_occasion")) / 7,
                 standard_drinks=float(c["standard_drinks"].sum()) if not c.empty else 0.0,
                 occasions=len(day_costs),
                 free_days=rd.completed_days - drinking_complete,
                 saved=calc.alcohol_savings(per_week, per_occasion, rd.days, day_costs),
                 spent=calc.alcohol_spent(day_costs, per_occasion))
    return m


def compare_periods(ctx: UserContext, addiction_type: str, length: int) -> tuple[dict, dict]:
    """Metrics for the last `length` days (including today) and the `length` days before that."""
    today = local_today(ctx.tz)
    current = load_range(ctx, addiction_type, today - timedelta(days=length - 1), today)
    previous = load_range(ctx, addiction_type, today - timedelta(days=2 * length - 1), today - timedelta(days=length))
    return period_metrics(ctx, current), period_metrics(ctx, previous)


def _column(df: pd.DataFrame, name: str) -> list:
    return df[name].tolist() if not df.empty and name in df else []


def _hours_per_unit(consumption: pd.DataFrame) -> list[int]:
    """One entry per cigarette/drink, so 3 cigarettes at 4 PM weigh three times one at 9 AM."""
    hours = []
    for hour, qty in zip(_column(consumption, "hour"), _column(consumption, "quantity")):
        hours += [hour] * max(1, round(qty))
    return hours


def insight_input(ctx: UserContext, rd: RangeData, metrics: dict, this_week_days: int | None,
                  last_week_days: int | None):
    meta = {SMOKING: ("smoking", "cigarettes", "smoke-free"), ALCOHOL: ("drinking", "drinks", "alcohol-free")}
    habit, units, free_label = meta[rd.addiction]
    c, cr = rd.consumption, rd.cravings
    return InsightInput(
        habit=habit, units=units, free_label=free_label,
        consumption_hours=_hours_per_unit(c),
        consumption_weekdays=_column(c, "weekday"),
        craving_hours=_column(cr, "hour"),
        craving_weekdays=_column(cr, "weekday"),
        craving_triggers=[t for t in _column(cr, "trigger") if t],
        coping=[(s, bool(r)) for s, r in zip(_column(cr, "coping_strategy"), _column(cr, "resisted")) if s],
        avg_per_day=metrics["avg_per_day"],
        baseline_per_day=metrics["baseline"],
        observed_days=rd.days,
        tracked_hours=metrics["tracked_hours"],
        free_hours=metrics["free_hours"],
        tracked_days_this_week=this_week_days,
        tracked_days_last_week=last_week_days,
        free_days=metrics.get("free_days") if rd.addiction == ALCOHOL else None,
        completed_days=rd.completed_days if rd.addiction == ALCOHOL else None,
    )


# ---------------------------------------------------------------------------
# Chart-ready frames (pure functions of a RangeData)
# ---------------------------------------------------------------------------

def _dates(first: date, last: date) -> list[date]:
    return [first + timedelta(days=i) for i in range((last - first).days + 1)] if first <= last else []


def daily_frame(rd: RangeData, value_col: str = "quantity") -> pd.DataFrame:
    """Total per local day across the range, zero-filled."""
    totals = rd.consumption.groupby("local_date")[value_col].sum() if not rd.consumption.empty else pd.Series(dtype=float)
    dates = _dates(rd.first, rd.last)
    return pd.DataFrame({"date": dates, value_col: [float(totals.get(d, 0.0)) for d in dates]})


def period_frame(daily: pd.DataFrame, value_col: str, freq: str) -> pd.DataFrame:
    """Weekly (Monday-start) or monthly totals. 'partial' marks periods the range only partly covers."""
    if daily.empty:
        return pd.DataFrame(columns=["label", "value", "partial"])
    first, last = daily["date"].min(), daily["date"].max()
    rows = []
    if freq == "week":
        keys = daily["date"].apply(lambda d: d - timedelta(days=d.weekday()))
        for key, group in daily.groupby(keys):
            rows.append({"label": key.strftime("%d %b"), "value": float(group[value_col].sum()),
                         "partial": key < first or key + timedelta(days=6) > last})
    else:
        keys = daily["date"].apply(lambda d: d.replace(day=1))
        for key, group in daily.groupby(keys):
            month_end = (key + timedelta(days=32)).replace(day=1) - timedelta(days=1)
            rows.append({"label": key.strftime("%b %Y"), "value": float(group[value_col].sum()),
                         "partial": key < first or month_end > last})
    return pd.DataFrame(rows)


def avoided_frame(daily: pd.DataFrame, baseline: float, today: date, today_frac: float) -> pd.DataFrame:
    """Running total of cigarettes avoided (never below zero), day by day."""
    running, values = 0.0, []
    for d, qty in zip(daily["date"], daily["quantity"]):
        expected = baseline * (today_frac if d == today else 1.0)
        running = max(0.0, running + expected - qty)
        values.append(running)
    return pd.DataFrame({"date": daily["date"], "value": values})


def status_per_day(rd: RangeData) -> pd.DataFrame:
    dates = _dates(rd.first, rd.last)
    out = pd.DataFrame({"date": dates})
    for status in (SUCCESS, CRAVING_RESISTED, CONSUMED):
        if rd.hourly.empty:
            out[status] = 0
        else:
            counts = rd.hourly[rd.hourly["status"] == status].groupby("local_date").size()
            out[status] = [int(counts.get(d, 0)) for d in dates]
    return out

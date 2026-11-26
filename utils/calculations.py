"""Pure calculation functions (no Streamlit, no database) – easy to unit test.

All results are estimates based on the user's own baselines and logs.
"""

from collections import Counter
from datetime import date, datetime, timedelta

from utils.constants import (
    CONSUMED, CRAVING_RESISTED, ETHANOL_DENSITY_G_PER_ML, MILESTONES, SUCCESS,
)


def standard_drinks(quantity: float, volume_ml: float, abv_percent: float, grams_per_drink: float) -> float:
    """Estimated standard drinks for `quantity` servings of `volume_ml` at `abv_percent`."""
    if quantity <= 0 or volume_ml <= 0 or abv_percent <= 0 or grams_per_drink <= 0:
        return 0.0
    grams = quantity * volume_ml * (abv_percent / 100) * ETHANOL_DENSITY_G_PER_ML
    return round(grams / grams_per_drink, 2)


def elapsed_days(start: datetime, now: datetime) -> float:
    """Fractional days between two aware datetimes (0 if start is in the future)."""
    return max(0.0, (now - start).total_seconds() / 86400)


def cigarettes_avoided(baseline_per_day: float, days: float, actual: float) -> float:
    return max(0.0, baseline_per_day * days - actual)


def smoking_savings(baseline_per_day: float, cost_per_unit: float, days: float, actual: float) -> float:
    return round(cigarettes_avoided(baseline_per_day, days, actual) * cost_per_unit, 2)


def smoking_spent(actual: float, cost_per_unit: float) -> float:
    return round(actual * cost_per_unit, 2)


def alcohol_spent(drinking_day_costs: dict[date, float | None], spend_per_occasion: float) -> float:
    """Money spent on alcohol. Days without a logged cost use the typical spend per occasion."""
    return round(sum(spend_per_occasion if c is None else c for c in drinking_day_costs.values()), 2)


def alcohol_savings(days_per_week: float, spend_per_occasion: float, days: float,
                    drinking_day_costs: dict[date, float | None]) -> float:
    """Expected spend at the old drinking pattern minus estimated actual spend."""
    expected = days * (days_per_week / 7) * spend_per_occasion
    return round(max(0.0, expected - alcohol_spent(drinking_day_costs, spend_per_occasion)), 2)


def avoided_drinking_occasions(days_per_week: float, days: float, actual_occasions: int) -> float:
    return max(0.0, days * days_per_week / 7 - actual_occasions)


def savings_projection(total_saved: float, days: float) -> dict[str, float]:
    """Average daily saving so far, projected forward."""
    daily = total_saved / days if days >= 1 else total_saved
    return {"daily": daily, "weekly": daily * 7, "monthly": daily * 30, "yearly": daily * 365}


def current_streak(tracking_start: datetime, last_consumption: datetime | None, now: datetime) -> timedelta:
    """Time since the later of tracking start and the most recent logged consumption."""
    anchor = max(tracking_start, last_consumption) if last_consumption else tracking_start
    return max(timedelta(0), now - anchor)


def free_days(start: date, today: date, consumption_dates: set[date]) -> int:
    """Completed days (start .. yesterday) with no logged consumption."""
    if start >= today:
        return 0
    total = (today - start).days
    return total - sum(1 for d in consumption_dates if start <= d < today)


def summarize_hours(statuses: list[str]) -> dict[str, int]:
    counts = Counter(statuses)
    free = counts[SUCCESS] + counts[CRAVING_RESISTED]
    return {
        "success": counts[SUCCESS],
        "craving_resisted": counts[CRAVING_RESISTED],
        "consumed": counts[CONSUMED],
        "free": free,
        "tracked": free + counts[CONSUMED],
    }


def percent(part: float, whole: float) -> int:
    return round(100 * part / whole) if whole > 0 else 0


def milestone_progress(hours: float) -> dict:
    """Which milestones are reached, the next one, and % progress toward it."""
    reached = [(h, label) for h, label in MILESTONES if hours >= h]
    upcoming = [(h, label) for h, label in MILESTONES if hours < h]
    nxt = upcoming[0] if upcoming else None
    prev_h = reached[-1][0] if reached else 0
    pct = 100 if nxt is None else round(100 * (hours - prev_h) / (nxt[0] - prev_h))
    return {"reached": reached, "next": nxt, "pct": max(0, min(100, pct))}


# ---------------------------------------------------------------------------
# Phase 2: streaks, achievements, savings goals, cravings
# ---------------------------------------------------------------------------

def longest_streak(tracking_start: datetime, consumption_times: list[datetime], now: datetime) -> timedelta:
    """Longest gap without logged consumption since tracking started (includes the current streak)."""
    anchors = [tracking_start] + sorted(t for t in consumption_times if tracking_start <= t <= now) + [now]
    return max((b - a for a, b in zip(anchors, anchors[1:])), default=timedelta(0))


def consecutive_days(days: set[date], today: date) -> dict[str, int]:
    """Current and best run of consecutive days. The current run may end today or yesterday."""
    best = run = 0
    previous = None
    for d in sorted(days):
        run = run + 1 if previous and d - previous == timedelta(days=1) else 1
        best = max(best, run)
        previous = d
    current = 0
    cursor = today if today in days else today - timedelta(days=1)
    while cursor in days:
        current += 1
        cursor -= timedelta(days=1)
    return {"current": current, "best": best}


def _window_total(daily: dict[date, float], first: date) -> float:
    return sum(daily.get(first + timedelta(days=i), 0.0) for i in range(7))


def _window_tracked(tracked_days: set[date], first: date) -> int:
    return sum(1 for i in range(7) if first + timedelta(days=i) in tracked_days)


def reduced_week(daily: dict[date, float], tracked_days: set[date], start: date, today: date,
                 baseline_per_day: float, min_tracked_days: int = 5) -> bool:
    """Any 7 completed days (start..yesterday) below baseline, with real tracking on most of them."""
    if baseline_per_day <= 0:
        return False
    first = start
    while first + timedelta(days=6) < today:
        if (_window_total(daily, first) < baseline_per_day * 7
                and _window_tracked(tracked_days, first) >= min_tracked_days):
            return True
        first += timedelta(days=1)
    return False


def best_week(daily: dict[date, float], tracked_days: set[date], start: date, today: date,
              min_tracked_days: int = 5) -> bool:
    """The most recent complete week has lower consumption than every earlier complete week."""
    blocks = []
    last = today - timedelta(days=7)  # first day of the most recent complete week
    while last >= start:
        blocks.append(last)
        last -= timedelta(days=7)
    if len(blocks) < 2 or _window_tracked(tracked_days, blocks[0]) < min_tracked_days:
        return False
    latest = _window_total(daily, blocks[0])
    return all(latest < _window_total(daily, b) for b in blocks[1:])


def allocate_savings(targets: list[float], total_saved: float) -> list[float]:
    """Fill savings goals in order: the first goal fills up before the next one starts."""
    remaining, out = max(0.0, total_saved), []
    for target in targets:
        portion = min(remaining, target)
        out.append(portion)
        remaining -= portion
    return out


def craving_stats(cravings: list[dict]) -> dict:
    total = len(cravings)
    resisted = sum(1 for c in cravings if c.get("resisted"))
    intensities = [c["intensity"] for c in cravings if c.get("intensity") is not None]
    triggers = Counter(c["trigger"] for c in cravings if c.get("trigger"))
    return {
        "total": total,
        "resisted": resisted,
        "consumed": total - resisted,
        "resisted_pct": percent(resisted, total),
        "avg_intensity": round(sum(intensities) / len(intensities), 1) if intensities else 0.0,
        "top_triggers": triggers.most_common(),
    }


def waking_fraction(local_now: datetime, wake_hour: int, sleep_hour: int) -> float:
    """How much of today's waking window has passed (0 before waking, 1 after bedtime)."""
    hours = local_now.hour + local_now.minute / 60 + local_now.second / 3600
    return min(1.0, max(0.0, (hours - wake_hour) / (sleep_hour - wake_hour)))


def effective_days(start: date, today: date, today_fraction: float) -> float:
    """Full days since `start` plus the part of today that counts (see waking_fraction)."""
    if start > today:
        return 0.0
    return (today - start).days + today_fraction


# ---------------------------------------------------------------------------
# Phase 3: analytics ranges
# ---------------------------------------------------------------------------

def observed_days(first: date, last: date, start: date, today: date, today_fraction: float) -> float:
    """Days of a date range that have actually been tracked (after tracking start, up to now)."""
    first = max(first, start)
    if first > today or first > last:
        return 0.0
    if last < today:
        return float((last - first).days + 1)
    return (today - first).days + today_fraction


def change_pct(current: float, previous: float) -> float | None:
    """Percentage change, or None when there's nothing to compare against."""
    if previous == 0:
        return None
    return round(100 * (current - previous) / previous)

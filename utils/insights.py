"""Behavioural insights generated ONLY from the user's own records.

Every rule has a minimum amount of data before it says anything, and every
sentence carries the counts it is based on – so an insight can always be
traced back to real entries and is never invented.
"""

from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime

from utils.datetime_utils import hour_label

WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]

MIN_EVENTS_FOR_TIME_PATTERN = 5
MIN_EVENTS_FOR_WEEKDAY_PATTERN = 8
MIN_CRAVINGS_FOR_TRIGGER = 5
MIN_DAYS_FOR_BASELINE = 3
MIN_USES_FOR_COPING = 3
MIN_TRACKED_HOURS_FOR_SHARE = 10


@dataclass
class Insight:
    icon: str
    text: str
    kind: str  # "progress" | "pattern" | "tip"


@dataclass
class InsightInput:
    habit: str                       # "smoking" / "drinking"
    units: str                       # "cigarettes" / "drinks"
    free_label: str                  # "smoke-free" / "alcohol-free"
    consumption_hours: list[int] = field(default_factory=list)     # one entry per event (local hour)
    consumption_weekdays: list[int] = field(default_factory=list)  # 0 = Monday
    craving_hours: list[int] = field(default_factory=list)
    craving_weekdays: list[int] = field(default_factory=list)
    craving_triggers: list[str] = field(default_factory=list)
    coping: list[tuple[str, bool]] = field(default_factory=list)   # (strategy, resisted)
    avg_per_day: float = 0.0
    baseline_per_day: float = 0.0
    observed_days: float = 0.0
    tracked_hours: int = 0
    free_hours: int = 0
    tracked_days_this_week: int | None = None
    tracked_days_last_week: int | None = None
    free_days: int | None = None      # alcohol: completed alcohol-free days in range
    completed_days: int | None = None


def peak_window(hours: list[int], width: int = 2) -> tuple[int, int] | None:
    """Start hour and count of the busiest `width`-hour window (wrapping past midnight)."""
    if not hours:
        return None
    counts = Counter(h % 24 for h in hours)
    best = max(range(24), key=lambda s: (sum(counts[(s + i) % 24] for i in range(width)), -s))
    return best, sum(counts[(best + i) % 24] for i in range(width))


def window_label(start: int, width: int = 2) -> str:
    a = hour_label(datetime(2000, 1, 1, start))
    b = hour_label(datetime(2000, 1, 1, (start + width) % 24))
    return f"{a} and {b}"


def _unique_top(counter: Counter) -> tuple[str, int] | None:
    top = counter.most_common(2)
    if not top or (len(top) > 1 and top[0][1] == top[1][1]):
        return None  # no data, or a tie – don't pretend there's a single answer
    return top[0]


def time_pattern(hours: list[int], lead: str) -> Insight | None:
    """lead: e.g. "You experience most smoking cravings" / "Most of your smoking happens"."""
    if len(hours) < MIN_EVENTS_FOR_TIME_PATTERN:
        return None
    start, count = peak_window(hours)
    if count < 3 or count / len(hours) < 0.3:
        return None
    return Insight("🕓", f"{lead} between {window_label(start)} ({count} of {len(hours)}).", "pattern")


def weekday_pattern(weekdays: list[int], what: str) -> Insight | None:
    if len(weekdays) < MIN_EVENTS_FOR_WEEKDAY_PATTERN:
        return None
    top = _unique_top(Counter(weekdays))
    if not top or top[1] < 3 or top[1] / len(weekdays) < 0.25:
        return None
    return Insight("📅", f"{WEEKDAYS[top[0]]}s stand out: {top[1]} of your {len(weekdays)} {what} "
                         f"in this period happened on a {WEEKDAYS[top[0]]}.", "pattern")


def trigger_pattern(triggers: list[str]) -> Insight | None:
    triggers = [t for t in triggers if t]
    if len(triggers) < MIN_CRAVINGS_FOR_TRIGGER:
        return None
    top = _unique_top(Counter(triggers))
    if not top or top[1] < 3 or top[1] / len(triggers) < 0.25:
        return None
    return Insight("🎯", f"“{top[0]}” is your most common craving trigger ({top[1]} of {len(triggers)} "
                         "cravings with a trigger). Planning one alternative for that moment can help.", "pattern")


def baseline_comparison(d: InsightInput) -> Insight | None:
    if d.observed_days < MIN_DAYS_FOR_BASELINE or d.baseline_per_day <= 0:
        return None
    change = round(100 * (d.avg_per_day - d.baseline_per_day) / d.baseline_per_day)
    avg, base = f"{d.avg_per_day:.1f}", f"{d.baseline_per_day:g}"
    if change <= -10:
        return Insight("📉", f"Your {d.habit} has decreased by {abs(change)}% compared with your original "
                             f"baseline ({avg} vs {base} {d.units} a day).", "progress")
    if change >= 10:
        return Insight("🤍", f"Your {d.habit} has been {change}% above your original baseline in this period "
                             f"({avg} vs {base} {d.units} a day). Noticing it is the first step – "
                             "the next hour is a fresh start.", "tip")
    return Insight("➖", f"Your {d.habit} is close to your original baseline ({avg} vs {base} {d.units} a day). "
                         "Small, steady reductions add up.", "tip")


def free_share(d: InsightInput) -> Insight | None:
    if d.tracked_hours < MIN_TRACKED_HOURS_FOR_SHARE:
        return None
    pct = round(100 * d.free_hours / d.tracked_hours)
    return Insight("✅", f"{pct}% of the hours you tracked were {d.free_label} "
                         f"({d.free_hours} of {d.tracked_hours}).", "progress")


def tracking_trend(d: InsightInput) -> Insight | None:
    this, last = d.tracked_days_this_week, d.tracked_days_last_week
    if this is None or last is None or (this == 0 and last == 0):
        return None
    if this > last and last > 0:
        return Insight("📈", f"Your tracking consistency has improved this week: {this} days tracked "
                             f"vs {last} the week before.", "progress")
    if this < last:
        return Insight("🌱", f"You tracked on {this} day{'s' if this != 1 else ''} this week vs {last} the week "
                             "before. Even one logged hour a day keeps your picture accurate.", "tip")
    return None


def coping_pattern(coping: list[tuple[str, bool]]) -> Insight | None:
    stats: dict[str, list[int]] = {}
    for strategy, resisted in coping:
        if strategy:
            s = stats.setdefault(strategy, [0, 0])
            s[0] += 1
            s[1] += int(resisted)
    candidates = [(name, used, won) for name, (used, won) in stats.items() if used >= MIN_USES_FOR_COPING]
    if not candidates:
        return None
    name, used, won = max(candidates, key=lambda c: (c[2] / c[1], c[1]))
    if won / used < 0.6:
        return None
    return Insight("🧰", f"“{name}” works well for you – you resisted {won} of {used} cravings when you used it.",
                   "pattern")


def alcohol_free_days(d: InsightInput) -> Insight | None:
    if d.free_days is None or not d.completed_days or d.completed_days < 3:
        return None
    return Insight("🌙", f"You had {d.free_days} alcohol-free day{'s' if d.free_days != 1 else ''} out of "
                         f"{d.completed_days} completed days in this period.", "progress")


def build_insights(d: InsightInput, limit: int = 6) -> list[Insight]:
    candidates = [
        baseline_comparison(d),
        alcohol_free_days(d),
        free_share(d),
        tracking_trend(d),
        time_pattern(d.craving_hours, f"You experience most {d.habit} cravings"),
        time_pattern(d.consumption_hours, f"Most of your {d.habit} happens"),
        trigger_pattern(d.craving_triggers),
        coping_pattern(d.coping),
        weekday_pattern(d.consumption_weekdays, f"{d.habit} entries"),
        weekday_pattern(d.craving_weekdays, "cravings"),
    ]
    found = [c for c in candidates if c]
    order = {"progress": 0, "pattern": 1, "tip": 2}
    return sorted(found, key=lambda i: order[i.kind])[:limit]

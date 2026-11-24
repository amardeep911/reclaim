"""Achievements: work out what has been earned from real records and unlock it.

Unlocked achievements are stored in user_achievements and are never removed –
a relapse resets the current streak, not the history.
Milestones need at least one hour actually tracked for that habit, so an
untouched account never earns anything just by waiting.
"""

from datetime import date

from services.analytics_service import addiction_overview, alcohol_days_per_week, tracking_start
from services.craving_service import count_resisted, get_cravings
from services.database_service import UserContext, db, iso, select_all, uid
from utils import calculations as calc
from utils.constants import CRAVING_RESISTED, SMOKING
from utils.datetime_utils import day_bounds_utc, local_today, now_utc, parse_ts


def get_catalogue(ctx: UserContext) -> list[dict]:
    rows = db().table("achievements").select("*").order("sort_order").execute().data
    return [r for r in rows if r.get("addiction_type") in (None, *ctx.addictions)]


def get_unlocked() -> dict[str, dict]:
    rows = db().table("user_achievements").select("*").eq("user_id", uid()).execute().data
    return {r["achievement_id"]: r for r in rows}


def compute_metrics(ctx: UserContext, overviews: dict | None = None) -> dict:
    tz, today = ctx.tz, local_today(ctx.tz)
    overviews = overviews or {a: addiction_overview(ctx, a) for a in ctx.addictions}
    first_start = min(tracking_start(ctx, a) for a in ctx.addictions)
    since = day_bounds_utc(first_start, tz)[0]

    hourly = select_all("hourly_logs", lambda q: q.eq("user_id", uid()).gte("slot_start", iso(since))
                        .lte("slot_end", iso(now_utc())), columns="addiction_type,slot_start,status")
    cravings = get_cravings(since, None)

    def local_day(ts) -> date:
        return parse_ts(ts).astimezone(tz).date()

    per = {}
    for a in ctx.addictions:
        o = overviews[a]
        ap = ctx.addiction_profiles[a]
        tracked = ({local_day(h["slot_start"]) for h in hourly if h["addiction_type"] == a}
                   | set(o["consumption_dates"])
                   | {c["occurred_at"].astimezone(tz).date() for c in cravings if c["addiction_type"] == a})
        if a == SMOKING:
            baseline = float(ap.get("baseline_per_day") or 0)
        else:  # usual drinks per day, averaged over the week
            baseline = alcohol_days_per_week(ap) * float(ap.get("drinks_per_occasion") or 0) / 7
        per[a] = {
            "tracked_free_hours": o["tracked_free_hours"],
            "best_streak_hours": o["best_streak_hours"],
            "streak_hours": o["streak_hours"],
            "free_days": o["free_days"],
            "reduced_week": calc.reduced_week(o["daily_totals"], tracked, o["start_day"], today, baseline),
            "best_week": calc.best_week(o["daily_totals"], tracked, o["start_day"], today),
        }

    hourly_days = {local_day(h["slot_start"]) for h in hourly}
    craving_hours = sum(1 for h in hourly if h["status"] == CRAVING_RESISTED)
    return {
        "per_addiction": per,
        # Credit cravings logged in the Craving Manager or marked in the Hourly Tracker (no double counting).
        "cravings_resisted": max(count_resisted(), craving_hours),
        "tracking_days": calc.consecutive_days(hourly_days, today),
    }


def progress(achievement: dict, metrics: dict) -> float:
    """0..1 progress toward an achievement (1 = earned)."""
    code, threshold = achievement["code"], float(achievement["threshold"] or 0)
    a = achievement.get("addiction_type")
    if a:
        m = metrics["per_addiction"].get(a)
        if not m or m["tracked_free_hours"] < 1:
            return 0.0
        if code.endswith("_1h"):
            value, target = m["tracked_free_hours"], 1
        elif code == "alcohol_free_1d":
            value, target = m["free_days"], 1
        else:
            value, target = m["best_streak_hours"], threshold
        return min(1.0, value / target) if target else 0.0
    if code.startswith("cravings_"):
        return min(1.0, metrics["cravings_resisted"] / threshold) if threshold else 0.0
    if code == "reduced_week":
        return 1.0 if any(m["reduced_week"] for m in metrics["per_addiction"].values()) else 0.0
    if code == "best_week":
        return 1.0 if any(m["best_week"] for m in metrics["per_addiction"].values()) else 0.0
    if code == "tracking_7d":
        return min(1.0, metrics["tracking_days"]["best"] / 7)
    return 0.0


def check_and_unlock(ctx: UserContext, overviews: dict | None = None, metrics: dict | None = None) -> list[dict]:
    """Unlock everything newly earned. Returns the newly unlocked catalogue rows."""
    catalogue = get_catalogue(ctx)
    unlocked = get_unlocked()
    metrics = metrics or compute_metrics(ctx, overviews)
    new = [a for a in catalogue if a["id"] not in unlocked and progress(a, metrics) >= 1.0]
    if new:
        db().table("user_achievements").upsert(
            [{"user_id": uid(), "achievement_id": a["id"]} for a in new],
            on_conflict="user_id,achievement_id", ignore_duplicates=True,
        ).execute()
    return new


def mark_seen(achievement_ids: list[str]) -> None:
    if achievement_ids:
        (db().table("user_achievements").update({"seen": True}).eq("user_id", uid())
         .in_("achievement_id", achievement_ids).execute())


def unseen() -> list[str]:
    return [r["achievement_id"] for r in get_unlocked().values() if not r.get("seen")]

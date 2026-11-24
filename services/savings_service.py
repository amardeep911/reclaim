"""Money saved + savings goals.

Savings come from addiction_overview (baseline vs. logged consumption).
Goals are filled in the order they were created, so the first goal fills up
before the next one starts.
"""

from services.analytics_service import addiction_overview, alcohol_days_per_week
from services.database_service import UserContext, db, uid
from utils import calculations as calc
from utils.constants import SMOKING


def get_goals() -> list[dict]:
    return (db().table("savings_goals").select("*").eq("user_id", uid())
            .order("created_at").execute().data)


def add_goal(title: str, target_amount: float, icon: str) -> None:
    db().table("savings_goals").insert({"user_id": uid(), "title": title, "target_amount": target_amount,
                                        "icon": icon}).execute()


def update_goal(goal_id: str, fields: dict) -> None:
    db().table("savings_goals").update(fields).eq("id", goal_id).eq("user_id", uid()).execute()


def delete_goal(goal_id: str) -> None:
    db().table("savings_goals").delete().eq("id", goal_id).eq("user_id", uid()).execute()


def goals_with_progress(goals: list[dict], total_saved: float) -> list[dict]:
    """Adds 'allocated' and 'pct' to each open goal.

    Completed goals were bought with savings, so their cost is taken out first.
    """
    open_goals = [g for g in goals if not g.get("is_completed")]
    spent_on_goals = sum(float(g["target_amount"]) for g in goals if g.get("is_completed"))
    allocated = calc.allocate_savings([float(g["target_amount"]) for g in open_goals], total_saved - spent_on_goals)
    return [{**g, "allocated": a, "pct": calc.percent(a, float(g["target_amount"]))}
            for g, a in zip(open_goals, allocated)]


def breakdown(ctx: UserContext, overviews: dict | None = None) -> dict:
    """Per-habit savings plus the 'potential' saving rate if the baseline habit stopped completely."""
    overviews = overviews or {a: addiction_overview(ctx, a) for a in ctx.addictions}
    rows = {}
    for a, o in overviews.items():
        ap = ctx.addiction_profiles[a]
        if a == SMOKING:
            potential_daily = float(ap.get("baseline_per_day") or 0) * float(ap.get("cost_per_unit") or 0)
        else:
            potential_daily = alcohol_days_per_week(ap) * float(ap.get("spend_per_occasion") or 0) / 7
        rows[a] = {"saved": o["saved"], "spent": o["spent"], "days": o["days"],
                   "projection": o["projection"], "potential_daily": potential_daily}
    total = sum(r["saved"] for r in rows.values())
    days = max((r["days"] for r in rows.values()), default=0)
    return {"by_addiction": rows, "total": total, "projection": calc.savings_projection(total, days),
            "potential_daily": sum(r["potential_daily"] for r in rows.values())}

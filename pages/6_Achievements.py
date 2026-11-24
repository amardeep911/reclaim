"""Achievements & Streaks – current streaks and lifetime progress, shown separately."""

import streamlit as st

from components.cards import achievement_cards, number, page_header, section, stat_cards
from components.navigation import require_context
from services import achievement_service as ach
from services.analytics_service import addiction_overview
from utils.constants import ADDICTIONS, ALCOHOL, SMOKING
from utils.datetime_utils import format_duration, format_local, parse_ts

ctx = require_context()

page_header("Achievements", "Every milestone you reach is yours to keep – a slip never takes it away.",
            eyebrow="Progress")

try:
    overviews = {a: addiction_overview(ctx, a) for a in ctx.addictions}
    metrics = ach.compute_metrics(ctx, overviews)
    ach.check_and_unlock(ctx, metrics=metrics)
    catalogue = ach.get_catalogue(ctx)
    unlocked = ach.get_unlocked()
except Exception:
    st.error("Couldn't load your achievements. Check your connection and try again.")
    st.stop()

fresh = {aid for aid, row in unlocked.items() if not row.get("seen")}
if fresh:
    st.balloons()
    names = [a["title"] for a in catalogue if a["id"] in fresh]
    st.success(f"🎉 **New achievement{'s' if len(names) > 1 else ''} unlocked:** {', '.join(names)}")
    ach.mark_seen(list(fresh))

# ---------------------------------------------------------------- current streaks
section("Current streaks", "How long since your last logged use, and how consistently you're tracking.")
cards = []
for a in ctx.addictions:
    meta, o = ADDICTIONS[a], overviews[a]
    cards += [
        {"label": f"{meta['icon']} Current {meta['free'].lower()} streak", "value": format_duration(o["streak"]),
         "accent": "teal", "sub": f"since last logged {meta['unit']}"},
        {"label": f"{meta['icon']} Best streak", "value": format_duration(o["best_streak"]), "accent": "green",
         "sub": "your record so far"},
    ]
tracking = metrics["tracking_days"]
cards.append({"label": "Tracking streak", "value": f"{tracking['current']} day{'s' if tracking['current'] != 1 else ''}",
              "accent": "blue", "sub": f"best: {tracking['best']} days with hours logged"})
stat_cards(cards)

# ---------------------------------------------------------------- lifetime
section("Lifetime progress", "These numbers only ever grow.")
life = []
for a in ctx.addictions:
    meta, o = ADDICTIONS[a], overviews[a]
    life.append({"label": f"Tracked {meta['free'].lower()} hours", "value": o["tracked_free_hours"], "accent": "green"})
    if a == SMOKING:
        life.append({"label": "Cigarettes avoided", "value": number(o["avoided"]), "sub": "estimate"})
    if a == ALCOHOL:
        life.append({"label": "Alcohol-free days", "value": o["free_days"]})
life.append({"label": "Cravings resisted", "value": metrics["cravings_resisted"], "accent": "yellow"})
life.append({"label": "Achievements", "value": f"{len(unlocked)} / {len(catalogue)}", "accent": "teal"})
stat_cards(life)


# ---------------------------------------------------------------- badges
def to_card(a: dict) -> dict:
    row = unlocked.get(a["id"])
    if row:
        meta = f"Unlocked {format_local(parse_ts(row['unlocked_at']), ctx.tz, '%d %b %Y')}"
    else:
        p = ach.progress(a, metrics)
        meta = f"{round(100 * p)}% there" if p else "Locked"
    return {"icon": a["icon"], "title": a["title"], "description": a["description"], "unlocked": bool(row),
            "new": a["id"] in fresh, "meta": meta, "progress": 0 if row else ach.progress(a, metrics)}


groups = [(f"{ADDICTIONS[a]['icon']} {ADDICTIONS[a]['label']} milestones",
           [x for x in catalogue if x.get("addiction_type") == a]) for a in ctx.addictions]
groups += [("💪 Cravings", [x for x in catalogue if x["category"] == "craving"]),
           ("📈 Progress & consistency", [x for x in catalogue if x["category"] in ("progress", "consistency")])]
for title, items in groups:
    if items:
        section(title)
        achievement_cards([to_card(x) for x in items])

st.caption("Milestones count time since your last logged use, and unlock once you've tracked at least one hour "
           "for that habit. “Reduced week” and “Best week” need hours or entries logged on at least 5 of the 7 days.")

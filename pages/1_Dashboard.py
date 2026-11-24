"""Dashboard – answers "How am I doing today?" from real records only."""

from datetime import timedelta

import streamlit as st

from components import charts
from components.cards import money, number, page_header, progress_bar, quote_card, section, stat_cards
from components.forms import daily_checkin_form
from components.hourly_timeline import sleep_card
from components.navigation import require_context
from services import achievement_service as ach
from services import analytics_service as an
from services import database_service as dbs
from services import savings_service as ss
from utils import calculations as calc
from utils.constants import ADDICTIONS, ALCOHOL, MILESTONES, MOOD_EMOJI, SMOKING
from utils.datetime_utils import format_duration, local_now

ctx = require_context()
tz = ctx.tz
now_local = local_now(tz)
today = now_local.date()

greeting = "Good morning" if now_local.hour < 12 else "Good afternoon" if now_local.hour < 17 else "Good evening"
page_header(f"{greeting}, {ctx.name}", "One hour at a time. One day at a time.",
            eyebrow=now_local.strftime("%A, %d %B"))

if flash := st.session_state.pop("flash", None):
    st.success(flash)
if ctx.addiction_profiles.get(ALCOHOL, {}).get("dependence_risk") and ALCOHOL in ctx.addictions:
    st.warning("**Safety first:** you mentioned signs of physical dependence on alcohol. Please cut down with a "
               "doctor's guidance rather than stopping suddenly. Seizures, hallucinations or severe confusion "
               "need emergency care – see *Health & Safety*.")

try:
    overviews = {a: an.addiction_overview(ctx, a) for a in ctx.addictions}
    todays = {a: an.day_summary(ctx, a, today) for a in ctx.addictions}
    checkin = dbs.get_daily_log(today)
except Exception:
    st.error("Couldn't load your dashboard. Check your connection and try again.")
    st.stop()

# Achievements are a bonus – never let them break the dashboard.
try:
    metrics = ach.compute_metrics(ctx, overviews)
    newly_unlocked = ach.check_and_unlock(ctx, metrics=metrics)
except Exception:
    metrics, newly_unlocked = None, []
if newly_unlocked:
    st.balloons()
    st.success("🎉 **Achievement unlocked:** " + ", ".join(f"{a['icon']} {a['title']}" for a in newly_unlocked))
    st.page_link("pages/6_Achievements.py", label="See your achievements", icon=":material/emoji_events:")

# ---------------------------------------------------------------- today
section("Today", "Only finished hours you've logged count – untracked hours are never failures.")
for a in ctx.addictions:
    meta, t = ADDICTIONS[a], todays[a]
    ap = ctx.addiction_profiles[a]
    cards = [
        {"label": f"{meta['free']} hours", "value": t["free"], "accent": "green",
         "sub": f"of {t['tracked']} logged today"},
        {"label": "Cravings resisted", "value": t["craving_resisted"], "accent": "yellow", "sub": "hours"},
        {"label": meta["units"].capitalize(), "value": number(t["quantity"]), "accent": "red",
         "sub": (f"first at {t['first_time'].strftime('%I:%M %p').lstrip('0')}" if t["first_time"] is not None
                 else "none logged today") if a == SMOKING else f"≈ {t['standard_drinks']:.1f} standard drinks"},
    ]
    if a == SMOKING:
        saved_today = calc.smoking_savings(float(ap.get("baseline_per_day") or 0), float(ap.get("cost_per_unit") or 0),
                                           an.today_fraction(ctx), t["quantity"])
        cards.append({"label": "Saved today", "value": money(saved_today, ctx.currency), "accent": "teal",
                      "sub": "estimate vs. baseline, waking hours"})
    st.markdown(f"**{meta['icon']} {meta['label']}**")
    stat_cards(cards)
    progress_bar(t["completion_pct"], "Hourly tracking today",
                 f"{t['window_tracked']} of {t['completed_hours']} finished waking hours logged")

# Plain-language daily summary
parts = []
for a in ctx.addictions:
    meta, t = ADDICTIONS[a], todays[a]
    parts.append(f"{t['free']} {meta['free'].lower()} hours")
    parts.append(f"{t['quantity']:g} {meta['units'] if t['quantity'] != 1 else meta['unit']}")
cravings_today = sum(todays[a]["craving_resisted"] for a in ctx.addictions)
parts.append(f"{cravings_today} craving hour{'s' if cravings_today != 1 else ''} resisted")
if checkin and checkin.get("mood"):
    parts.append(f"mood: {MOOD_EMOJI.get(checkin['mood'], '')} {checkin['mood']}")
st.caption("**Today's summary:** " + " · ".join(parts))

# What to focus on next – last night's sleep first, then today's hours
for a in ctx.addictions:
    sleep_card(ctx, a, key="dash")
untracked_now = {a: todays[a]["completed_hours"] - todays[a]["window_tracked"] for a in ctx.addictions}
if any(v > 0 for v in untracked_now.values()):
    pending = ", ".join(f"{v} {ADDICTIONS[a]['label'].lower()}" for a, v in untracked_now.items() if v > 0)
    st.info(f"**Next step:** you have finished hours to log ({pending}). It only takes a tap.", icon="⏱️")
else:
    st.info("**Next step:** you're up to date. Log the current hour when it ends – and be kind to yourself.", icon="🌿")

# ---------------------------------------------------------------- quick actions
section("Quick actions")
with st.container(horizontal=True, gap="small"):
    st.page_link("pages/2_Hourly_Tracker.py", label="Log an hour", icon=":material/schedule:")
    if SMOKING in ctx.addictions:
        st.page_link("pages/3_Consumption_Tracker.py", label="Record smoking", icon=":material/smoking_rooms:")
    if ALCOHOL in ctx.addictions:
        st.page_link("pages/3_Consumption_Tracker.py", label="Record a drink", icon=":material/local_bar:")
    st.page_link("pages/4_Craving_Manager.py", label="Log a craving", icon=":material/waves:")
    st.page_link("pages/8_Journal.py", label="Write in journal", icon=":material/menu_book:")
    st.page_link("pages/9_Resources.py", label="I need support", icon=":material/support:")

# ---------------------------------------------------------------- overview
section("Your recovery", "Lifetime progress is never erased – a slip only resets the current streak.")
total_saved = sum(o["saved"] for o in overviews.values())
cards = []
for a in ctx.addictions:
    meta, o = ADDICTIONS[a], overviews[a]
    cards.append({"label": f"{meta['free']} streak", "value": format_duration(o["streak"]), "accent": "teal",
                  "sub": f"best: {format_duration(o['best_streak'])}"})
    cards.append({"label": f"Tracked {meta['free'].lower()} hours", "value": o["tracked_free_hours"],
                  "accent": "green", "sub": "all time"})
    if a == SMOKING:
        cards.append({"label": "Cigarettes avoided", "value": number(o["avoided"]), "sub": "estimate vs. baseline"})
    else:
        cards.append({"label": "Alcohol-free days", "value": o["free_days"], "sub": "completed days, from your logs"})
cravings_resisted = metrics["cravings_resisted"] if metrics else sum(o["craving_hours"] for o in overviews.values())
cards.append({"label": "Cravings resisted", "value": cravings_resisted, "accent": "yellow", "sub": "all time"})
cards.append({"label": "Money saved", "value": money(total_saved, ctx.currency), "accent": "green",
              "sub": "estimated"})
stat_cards(cards)

# ---------------------------------------------------------------- motivation
reasons = [(label, ctx.profile.get(field)) for label, field in
           [("Why I'm doing this", "why_quit"), ("What I want to achieve", "aspirations"),
            ("What keeps me going", "motivators")] if ctx.profile.get(field)]
if reasons:
    section("Remember why")
    cols = st.columns(len(reasons))
    for col, (label, text) in zip(cols, reasons):
        with col:
            quote_card(label, text)

# ---------------------------------------------------------------- milestones
section("Recovery timeline", "Milestones are based on time since your last logged consumption.")
for a in ctx.addictions:
    meta, o = ADDICTIONS[a], overviews[a]
    m = o["milestones"]
    with st.container(border=True):
        st.markdown(f"**{meta['icon']} {meta['label']}**")
        if m["next"]:
            hours_left = m["next"][0] - o["streak_hours"]
            progress_bar(m["pct"], f"Next: {m['next'][1]} {meta['free'].lower()}",
                         f"{format_duration(timedelta(hours=hours_left))} to go")
        reached = {h for h, _ in m["reached"]}
        badges = " ".join(f"{'✅' if h in reached else '○'} {label}" for h, label in MILESTONES)
        st.caption(badges)

# ---------------------------------------------------------------- savings
section("Money saved", "Based on your original baseline and what you've actually logged.")
days_tracked = max(o["days"] for o in overviews.values()) if overviews else 0
proj = calc.savings_projection(total_saved, days_tracked)
stat_cards([
    {"label": "Total so far", "value": money(total_saved, ctx.currency), "accent": "green"},
    {"label": "Per day", "value": money(proj["daily"], ctx.currency)},
    {"label": "Per week", "value": money(proj["weekly"], ctx.currency)},
    {"label": "Per month", "value": money(proj["monthly"], ctx.currency)},
    {"label": "Per year (projected)", "value": money(proj["yearly"], ctx.currency), "accent": "teal"},
])
try:
    open_goals = ss.goals_with_progress(ss.get_goals(), total_saved)
except Exception:
    open_goals = []
if open_goals:
    g = open_goals[0]
    progress_bar(g["pct"], f"{g['icon']} {g['title']}",
                 f"{money(g['allocated'], ctx.currency)} of {money(float(g['target_amount']), ctx.currency)}")
st.page_link("pages/11_Savings.py", label="Savings goals & calculator", icon=":material/savings:")

# ---------------------------------------------------------------- trends
section("This week")
cols = st.columns(len(ctx.addictions))
for col, a in zip(cols, ctx.addictions):
    meta, ap = ADDICTIONS[a], ctx.addiction_profiles[a]
    baseline = float(ap.get("baseline_per_day") or 0) if a == SMOKING else \
        an.alcohol_days_per_week(ap) * float(ap.get("drinks_per_occasion") or 0) / 7
    with col:
        st.markdown(f"**{meta['icon']} {meta['units'].capitalize()} per day**")
        try:
            st.plotly_chart(charts.daily_bars(an.daily_series(ctx, a, 7), baseline, meta["units"]),
                            width="stretch", config={"displayModeBar": False})
        except Exception:
            st.caption("Chart unavailable right now.")

# ---------------------------------------------------------------- daily check-in
section("Daily check-in", "Mood, sleep and movement all affect cravings.")
with st.expander("✏️ Today's check-in" + (" – saved" if checkin else ""), expanded=not checkin):
    values = daily_checkin_form("checkin", checkin)
    if values:
        try:
            dbs.upsert_daily_log(today, values)
        except Exception:
            st.error("Couldn't save your check-in. Please try again.")
        else:
            st.session_state.flash = "Check-in saved. Thank you for taking a moment for yourself."
            st.rerun()

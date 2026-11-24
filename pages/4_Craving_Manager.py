"""Craving Manager – log a craving in seconds, then get help riding it out."""

from datetime import timedelta

import pandas as pd
import streamlit as st

from components import charts
from components.cards import empty_state, page_header, section, stat_cards
from components.coping import toolkit, withdrawal_warning
from components.navigation import addiction_picker, require_context
from services import craving_service as cs
from services.tracking_service import TrackingError
from utils import calculations as calc
from utils.constants import (
    ADDICTIONS, ALCOHOL, BEVERAGES, COPING_STRATEGIES, EMERGENCY_NOTE, MOODS, MOOD_EMOJI, SMOKING, TRIGGERS,
)
from utils.datetime_utils import format_local, local_today, now_utc, range_bounds_utc
from utils.validators import clean_text

ctx = require_context()
tz = ctx.tz

page_header("Craving Manager", "Cravings rise, peak and pass. Let's get you through this one.", eyebrow="Cope")
if flash := st.session_state.pop("craving_flash", None):
    st.toast(flash, icon="💚")

# ---------------------------------------------------------------- the big button
if not st.session_state.get("craving_form_open") and not st.session_state.get("craving_logged"):
    if st.button("🌊  I'm having a craving", key="craving-open", width="stretch"):
        st.session_state.craving_form_open = True
        st.rerun()

# ---------------------------------------------------------------- log form
if st.session_state.get("craving_form_open"):
    with st.container(border=True):
        st.markdown("#### Let's note it down – it takes 10 seconds")
        addiction = addiction_picker(ctx, key="craving_addiction")
        meta = ADDICTIONS[addiction]
        symptoms = False
        if addiction == ALCOHOL:
            symptoms = st.toggle("I also have physical symptoms (shaking, sweating, nausea, racing heart, "
                                 "feeling very unwell)", key="craving-symptoms")
            if symptoms:
                st.error("**Please get medical help now rather than managing this alone.** These can be signs of "
                         "alcohol withdrawal, which can become dangerous. Contact a doctor or urgent care today. "
                         f"\n\n{EMERGENCY_NOTE}", icon="🚑")
        outcome = st.radio("What happened?", ["resisting", "consumed"], horizontal=True, key="craving-outcome",
                           format_func=lambda o: "💪 I'm riding it out / I resisted" if o == "resisting"
                           else f"● I {meta['verb'].lower()}")
        with st.form("craving-form", border=False):
            intensity = st.slider("How strong is it?", 1, 10, 5, help="1 = barely there · 10 = overwhelming")
            c1, c2 = st.columns(2)
            trigger = c1.selectbox("What triggered it?", TRIGGERS, index=None, placeholder="Choose a trigger")
            mood = c2.selectbox("How are you feeling?", MOODS, index=None, placeholder="Choose a mood",
                                format_func=lambda m: f"{MOOD_EMOJI[m]} {m}")
            c3, c4 = st.columns(2)
            coping = c3.selectbox("What are you trying? (optional)", COPING_STRATEGIES, index=None,
                                  placeholder="Optional")
            location = c4.text_input("Where are you? (optional)", max_chars=120)
            quantity = 0
            if outcome == "consumed":
                quantity = st.number_input(f"How many {meta['units']}?", min_value=0, max_value=50, value=1,
                                           help="This also adds it to your consumption log. Use 0 to skip.")
            notes = st.text_area("Anything else? (optional)", max_chars=1000, height=70)
            s1, s2 = st.columns(2)
            submitted = s1.form_submit_button("Log craving", type="primary", width="stretch")
            cancelled = s2.form_submit_button("Cancel", width="stretch")

        if cancelled:
            st.session_state.craving_form_open = False
            st.rerun()
        if submitted:
            resisted = outcome == "resisting"
            consumption_fields = {}
            if not resisted and quantity and addiction == ALCOHOL:
                ap = ctx.addiction_profiles[ALCOHOL]
                bev = ap.get("beverage_type") if ap.get("beverage_type") in BEVERAGES else "Other"
                volume, abv = BEVERAGES[bev]
                consumption_fields = {"beverage_type": bev, "volume_ml": volume, "abv_percent": abv,
                                      "standard_drinks": calc.standard_drinks(quantity, volume, abv,
                                                                              ctx.grams_per_drink)}
            elif not resisted and quantity and addiction == SMOKING:
                cost = float(ctx.addiction_profiles[SMOKING].get("cost_per_unit") or 0)
                consumption_fields = {"cost": round(cost * quantity, 2) if cost else None}
            try:
                cs.log_craving(addiction, now_utc(), intensity, resisted, tz, quantity=float(quantity),
                               consumption_fields=consumption_fields, trigger=trigger, mood=mood,
                               location=clean_text(location, 120), coping_strategy=coping,
                               notes=clean_text(notes, 1000))
            except TrackingError as exc:
                st.error(str(exc))
            except Exception:
                st.error("Couldn't save that. Please try again – and keep going, you're doing the right thing.")
            else:
                st.session_state.craving_form_open = False
                st.session_state.craving_logged = {"addiction": addiction, "resisted": resisted,
                                                   "symptoms": symptoms}
                st.rerun()

# ---------------------------------------------------------------- after logging: support
logged = st.session_state.get("craving_logged")
if logged:
    meta = ADDICTIONS[logged["addiction"]]
    with st.container(border=True):
        if logged["resisted"]:
            st.markdown("#### You noticed it, and you're riding it out. That takes real strength. 💪")
            st.caption("Pick something below for the next few minutes. The urge will pass.")
        else:
            st.markdown("#### Thank you for logging it honestly.")
            st.caption("One moment doesn't erase your progress. What could make the next hour a little easier? "
                       "Try one of these – the next hour is a fresh start.")
        if logged.get("symptoms"):
            withdrawal_warning(True)
        toolkit(ctx, logged["addiction"], key="after")
        if st.button("I'm feeling steadier – close", type="primary"):
            st.session_state.pop("craving_logged", None)
            st.session_state.pop("after-breathing", None)
            st.session_state.craving_flash = "Well done for taking care of yourself."
            st.rerun()
elif not st.session_state.get("craving_form_open"):
    with st.expander("🧰 Open the coping toolkit without logging"):
        toolkit(ctx, ctx.addictions[0] if len(ctx.addictions) == 1 else
                st.session_state.get("active_addiction", ctx.addictions[0]), key="free")

# ---------------------------------------------------------------- stats
section("Your craving patterns", "Every craving you log helps you understand – and outsmart – your triggers.")
periods = {"7": "7 days", "30": "30 days", "90": "90 days", "all": "All time"}
period = st.segmented_control("Period", list(periods), default="30", format_func=periods.get,
                              label_visibility="collapsed", key="craving-period") or "30"
today = local_today(tz)
start = None if period == "all" else range_bounds_utc(today - timedelta(days=int(period) - 1), today, tz)[0]
try:
    cravings = cs.get_cravings(start, None)
except Exception:
    st.error("Couldn't load your craving history.")
    st.stop()

if not cravings:
    empty_state("🌊", "No cravings logged in this period",
                "When a craving hits, tap the button above. Logging it is already a step toward handling it.")
    st.stop()

stats = calc.craving_stats(cravings)
stat_cards([
    {"label": "Cravings logged", "value": stats["total"], "accent": "teal"},
    {"label": "Resisted", "value": stats["resisted"], "accent": "green", "sub": f"{stats['resisted_pct']}% of cravings"},
    {"label": "Followed by use", "value": stats["consumed"], "accent": "red", "sub": "no judgement – just data"},
    {"label": "Average intensity", "value": f"{stats['avg_intensity']:g}/10", "accent": "yellow"},
])

if stats["top_triggers"]:
    c1, c2 = st.columns([3, 2])
    with c1:
        st.markdown("**Most common triggers**")
        st.plotly_chart(charts.trigger_bars(stats["top_triggers"][:6]), width="stretch",
                        config={"displayModeBar": False})
    with c2:
        top, count = stats["top_triggers"][0]
        if stats["total"] >= 3:
            st.info(f"**{top}** is your most common trigger ({count} of {stats['total']} cravings in this period). "
                    "Planning one alternative for that situation can make a big difference.", icon="🔎")
        resisted_by_trigger = pd.DataFrame(cravings).groupby("trigger")["resisted"].mean() \
            if any(c.get("trigger") for c in cravings) else pd.Series(dtype=float)
        if len(resisted_by_trigger) >= 2 and stats["total"] >= 5:
            hardest = resisted_by_trigger.idxmin()
            st.caption(f"Cravings triggered by **{hardest}** are the ones you resist least often "
                       f"({round(100 * resisted_by_trigger.min())}%). Be extra kind to yourself in those moments.")

# ---------------------------------------------------------------- history
section("History")
table = pd.DataFrame([{
    "When": format_local(c["occurred_at"], tz, "%a %d %b, %I:%M %p"),
    "Habit": ADDICTIONS[c["addiction_type"]]["label"],
    "Intensity": c["intensity"],
    "Trigger": c.get("trigger"),
    "Mood": c.get("mood"),
    "Outcome": "Resisted" if c["resisted"] else "Used",
    "Coping": c.get("coping_strategy"),
    "Notes": c.get("notes"),
} for c in cravings[:200]])
st.dataframe(table, hide_index=True, width="stretch")

with st.expander("Edit or delete a craving"):
    by_id = {c["id"]: c for c in cravings[:200]}
    chosen = st.selectbox("Craving", list(by_id), index=None, placeholder="Choose a craving…",
                          format_func=lambda i: f"{format_local(by_id[i]['occurred_at'], tz, '%a %d %b, %I:%M %p')}"
                                                f" · intensity {by_id[i]['intensity']}", key="craving-edit-pick")
    if chosen:
        c = by_id[chosen]
        with st.form(f"edit-craving-{chosen}"):
            intensity = st.slider("Intensity", 1, 10, int(c["intensity"]))
            e1, e2 = st.columns(2)
            trigger = e1.selectbox("Trigger", TRIGGERS, index=TRIGGERS.index(c["trigger"]) if c.get("trigger") in TRIGGERS else None)
            mood = e2.selectbox("Mood", MOODS, index=MOODS.index(c["mood"]) if c.get("mood") in MOODS else None)
            resisted = st.toggle("I resisted this craving", value=bool(c["resisted"]))
            coping = st.selectbox("Coping strategy", COPING_STRATEGIES,
                                  index=COPING_STRATEGIES.index(c["coping_strategy"])
                                  if c.get("coping_strategy") in COPING_STRATEGIES else None)
            notes = st.text_area("Notes", value=c.get("notes") or "", max_chars=1000)
            st.caption("Editing a craving doesn't change your hourly tracker or consumption log.")
            if st.form_submit_button("Update craving", type="primary"):
                try:
                    cs.update_craving(chosen, {"intensity": intensity, "trigger": trigger, "mood": mood,
                                               "resisted": resisted, "coping_strategy": coping,
                                               "notes": clean_text(notes, 1000)})
                except Exception:
                    st.error("Couldn't update that craving.")
                else:
                    st.session_state.craving_flash = "Craving updated."
                    st.rerun()
        confirm = st.checkbox("Yes, delete this craving", key=f"confirm-del-craving-{chosen}")
        if st.button("Delete craving", disabled=not confirm, key=f"del-craving-{chosen}"):
            try:
                cs.delete_craving(chosen)
            except Exception:
                st.error("Couldn't delete that craving.")
            else:
                st.session_state.craving_flash = "Craving deleted."
                st.rerun()

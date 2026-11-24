"""Consumption Tracker – log cigarettes or drinks with context, review and edit history."""

import pandas as pd
import streamlit as st

from components import charts
from components.cards import empty_state, money, number, page_header, section, stat_cards
from components.forms import alcohol_form, smoking_form
from components.navigation import addiction_picker, require_context
from services import analytics_service as an
from services import tracking_service as ts
from services.tracking_service import TrackingError
from utils.constants import ADDICTIONS, ALCOHOL, SMOKING, STANDARD_DRINK_GRAMS
from utils.datetime_utils import format_local, local_today, now_utc

ctx = require_context()
tz = ctx.tz

page_header("Consumption Tracker", "Honest logging is progress too. Every entry helps you understand your patterns.",
            eyebrow="Track")
if flash := st.session_state.pop("cons_flash", None):
    st.toast(flash, icon="✅")

addiction = addiction_picker(ctx, key="cons_addiction")
meta = ADDICTIONS[addiction]
ap = ctx.addiction_profiles[addiction]

try:
    totals = an.period_totals(ctx, addiction)
    overview = an.addiction_overview(ctx, addiction)
    series = an.daily_series(ctx, addiction, days=14)
except Exception:
    st.error("Couldn't load your data. Check your connection and try again.")
    st.stop()

# ---------------------------------------------------------------- stats
if addiction == SMOKING:
    baseline = float(ap.get("baseline_per_day") or 0)
    today_df = totals["frame"]
    today_rows = today_df[today_df["local_date"] == local_today(tz)] if not today_df.empty else today_df
    first_today = today_rows["local_time"].min() if not today_rows.empty else None
    change = (1 - totals["avg_per_day"] / baseline) * 100 if baseline else 0
    stat_cards([
        {"label": "Today", "value": number(totals["today"]), "accent": "teal",
         "sub": f"first at {first_today.strftime('%I:%M %p').lstrip('0')}" if first_today is not None else "none logged today"},
        {"label": "Last 7 days", "value": number(totals["week"]), "sub": "cigarettes"},
        {"label": "Last 30 days", "value": number(totals["month"]), "sub": "cigarettes"},
        {"label": "Daily average", "value": number(totals["avg_per_day"]),
         "sub": f"{abs(change):.0f}% {'below' if change >= 0 else 'above'} your baseline of {baseline:g}"},
        {"label": "Cigarettes avoided", "value": number(overview["avoided"]), "accent": "green",
         "sub": f"since {overview['start_day'].strftime('%d %b')}"},
        {"label": "Money spent", "value": money(overview["spent"], ctx.currency), "accent": "red",
         "sub": f"saved ≈ {money(overview['saved'], ctx.currency)}"},
    ])
    chart_baseline = baseline
else:
    per_week = an.alcohol_days_per_week(ap)
    drinks_per_occasion = float(ap.get("drinks_per_occasion") or 0)
    baseline_week = per_week * drinks_per_occasion
    grams, region_label = STANDARD_DRINK_GRAMS.get(ctx.profile.get("standard_drink_region") or "WHO",
                                                   STANDARD_DRINK_GRAMS["WHO"])
    stat_cards([
        {"label": "Today", "value": number(totals["today"]), "accent": "teal", "sub": "drinks"},
        {"label": "Last 7 days", "value": number(totals["week"]),
         "sub": f"≈ {totals['week_std']:.1f} std drinks · baseline ≈ {baseline_week:g} drinks"},
        {"label": "Last 30 days", "value": number(totals["month"]), "sub": f"≈ {totals['month_std']:.1f} std drinks"},
        {"label": "Alcohol-free days", "value": overview["free_days"], "accent": "green",
         "sub": f"since {overview['start_day'].strftime('%d %b')}"},
        {"label": "Drinking occasions", "value": overview["occasions"],
         "sub": f"≈ {number(overview['avoided'])} avoided vs. your usual pattern"},
        {"label": "Estimated spend", "value": money(overview["spent"], ctx.currency), "accent": "red",
         "sub": f"saved ≈ {money(overview['saved'], ctx.currency)}"},
    ])
    st.caption(f"Standard drinks are **estimates** using the {region_label} definition "
               f"({grams:g} g of pure alcohol), your serving size and alcohol %. Change the region in Settings.")
    chart_baseline = baseline_week / 7 if baseline_week else None

if ap.get("dependence_risk") and addiction == ALCOHOL:
    st.warning("You mentioned signs that your body may depend on alcohol. Please cut down with a doctor's "
               "guidance rather than stopping suddenly. See *Health & Safety* for warning signs.")

section("Last 14 days", f"{meta['units'].capitalize()} per day, compared with your starting baseline.")
st.plotly_chart(charts.daily_bars(series, chart_baseline, meta["units"]), width="stretch",
                config={"displayModeBar": False})

# ---------------------------------------------------------------- log / history
log_tab, history_tab = st.tabs([f"➕ Log {meta['units']}", "🗂️ History & edit"])

with log_tab:
    st.caption("No judgement here – logging helps you see what's really going on.")
    values = (smoking_form if addiction == SMOKING else alcohol_form)(f"new-{addiction}", ctx, submit_label="Save entry")
    if values:
        occurred_at = values.pop("occurred_at")
        quantity = values.pop("quantity")
        try:
            ts.log_consumption(addiction, occurred_at, quantity, tz, **values)
        except TrackingError as exc:
            st.error(str(exc))
        except Exception:
            st.error("Couldn't save that entry. Please try again.")
        else:
            extra = f" (≈ {values['standard_drinks']:g} standard drinks)" if addiction == ALCOHOL else ""
            st.session_state.cons_flash = f"Saved {quantity:g} {meta['units']}{extra}. Thank you for being honest."
            st.rerun()

with history_tab:
    try:
        rows = ts.get_consumption(None, now_utc(), addiction)[:300]
    except Exception:
        st.error("Couldn't load your history.")
        rows = []
    if not rows:
        empty_state("🌱", "Nothing logged yet", "Entries you add will show up here.")
    else:
        table = pd.DataFrame([{
            "When": format_local(r["occurred_at"], tz, "%a %d %b, %I:%M %p"),
            "Qty": float(r["quantity"]),
            **({"Drink": r.get("beverage_type"), "Std drinks": r.get("standard_drinks"), "Occasion": r.get("occasion")}
               if addiction == ALCOHOL else {}),
            "Trigger": r.get("trigger"),
            "Mood": r.get("mood"),
            "Notes": r.get("notes"),
        } for r in rows])
        st.dataframe(table, hide_index=True, width="stretch")

        st.markdown("##### Edit or delete an entry")
        by_id = {r["id"]: r for r in rows}
        chosen_id = st.selectbox(
            "Entry", list(by_id), index=None, placeholder="Choose an entry…", label_visibility="collapsed",
            format_func=lambda i: f"{format_local(by_id[i]['occurred_at'], tz, '%a %d %b, %I:%M %p')} · "
                                  f"{float(by_id[i]['quantity']):g} {meta['units']}",
        )
        if chosen_id:
            entry = by_id[chosen_id]
            form = smoking_form if addiction == SMOKING else alcohol_form
            edited = form(f"edit-{chosen_id}", ctx, defaults=entry, submit_label="Update entry")
            if edited:
                try:
                    ts.update_consumption(chosen_id, edited.pop("occurred_at"), edited.pop("quantity"), tz, **edited)
                except TrackingError as exc:
                    st.error(str(exc))
                except Exception:
                    st.error("Couldn't update that entry.")
                else:
                    st.session_state.cons_flash = "Entry updated."
                    st.rerun()
            confirm = st.checkbox("Yes, delete this entry", key=f"confirm-del-{chosen_id}")
            if st.button("Delete entry", disabled=not confirm, key=f"del-entry-{chosen_id}"):
                try:
                    ts.delete_consumption(chosen_id, tz)
                except Exception:
                    st.error("Couldn't delete that entry.")
                else:
                    st.session_state.cons_flash = "Entry deleted."
                    st.rerun()

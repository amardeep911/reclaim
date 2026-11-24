"""Settings & Profile – personal details, recovery plan, tracking, notifications, privacy, account."""

import json
from datetime import date, datetime

import streamlit as st

from components.cards import page_header
from components.navigation import require_context
from services import auth_service
from services import database_service as dbs
from utils.constants import (
    ALCOHOL, BEVERAGES, CURRENCIES, DRINKING_FREQUENCY, SMOKING, STANDARD_DRINK_GRAMS,
)
from utils.datetime_utils import UTC, local_today, timezone_choices
from utils.validators import (
    clean_text, validate_email, validate_password, validate_phone, validate_tracking_window,
)

ctx = require_context()
profile = ctx.profile

page_header("Settings & Profile", "Make Reclaim fit your life. Changes save to your account.", eyebrow="You")
if flash := st.session_state.pop("settings_flash", None):
    st.toast(flash, icon="✅")


def saved(message: str = "Saved.") -> None:
    st.session_state.settings_flash = message
    dbs.load_context(force=True)
    st.rerun()


hour_fmt = lambda h: "Midnight" if h in (0, 24) else f"{h % 12 or 12} {'AM' if h < 12 else 'PM'}"  # noqa: E731

tabs = st.tabs(["Profile", "Recovery plan", "Tracking & units", "Reminders", "Privacy & data", "Account"])

# ---------------------------------------------------------------- profile
with tabs[0]:
    with st.form("profile"):
        name = st.text_input("Name", value=profile.get("display_name", ""), max_chars=80)
        age = st.number_input("Age (optional)", 13, 120, value=profile.get("age"), step=1)
        why = st.text_area("Why do you want to change?", value=profile.get("why_quit") or "", max_chars=2000)
        aspirations = st.text_area("What do you want to achieve?", value=profile.get("aspirations") or "", max_chars=2000)
        motivators = st.text_area("What keeps you motivated?", value=profile.get("motivators") or "", max_chars=2000)
        st.markdown("**Trusted contact** – a one-tap call or message from the Craving Manager.")
        t1, t2 = st.columns(2)
        contact_name = t1.text_input("Name", value=profile.get("trusted_contact_name") or "", max_chars=80,
                                     key="contact-name")
        contact_phone = t2.text_input("Phone number", value=profile.get("trusted_contact_phone") or "",
                                      max_chars=30, key="contact-phone", placeholder="+91 98765 43210")
        if st.form_submit_button("Save profile", type="primary"):
            if not name.strip():
                st.error("Name can't be empty.")
            elif error := validate_phone(contact_phone):
                st.error(error)
            else:
                try:
                    dbs.update_profile({"display_name": name.strip(), "age": age,
                                        "why_quit": clean_text(why, 2000), "aspirations": clean_text(aspirations, 2000),
                                        "motivators": clean_text(motivators, 2000),
                                        "trusted_contact_name": clean_text(contact_name, 80),
                                        "trusted_contact_phone": clean_text(contact_phone, 30)})
                except Exception:
                    st.error("Couldn't save your profile.")
                else:
                    saved("Profile saved.")

# ---------------------------------------------------------------- recovery plan
with tabs[1]:
    st.caption("Baselines describe your habits *before* you started – they power the savings and "
               "“avoided” estimates. Changing them recalculates those estimates.")
    for a in (SMOKING, ALCOHOL):
        ap = ctx.addiction_profiles.get(a, {})
        goal = ctx.goals.get(a, {})
        icon, label = ("🚬", "Smoking") if a == SMOKING else ("🍷", "Alcohol")
        with st.expander(f"{icon} {label}", expanded=a in ctx.addictions):
            with st.form(f"plan-{a}"):
                active = st.toggle(f"Track {label.lower()}", value=a in ctx.addictions)
                c1, c2 = st.columns(2)
                start = c1.date_input("Tracking start date", value=date.fromisoformat(ap["tracking_start_date"])
                                      if ap.get("tracking_start_date") else local_today(ctx.tz),
                                      max_value=local_today(ctx.tz),
                                      help="Savings and free days are counted from this date.")
                quit_date = c2.date_input("Quit date", value=date.fromisoformat(ap["quit_date"])
                                          if ap.get("quit_date") else local_today(ctx.tz))
                if a == SMOKING:
                    c3, c4 = st.columns(2)
                    baseline = c3.number_input("Baseline cigarettes per day", 0.0, 200.0,
                                               value=float(ap.get("baseline_per_day") or 10), step=1.0)
                    cost = c4.number_input(f"Cost per cigarette ({ctx.currency})", 0.0,
                                           value=float(ap.get("cost_per_unit") or 0), step=0.5)
                    fields = {"baseline_per_day": baseline, "cost_per_unit": cost}
                else:
                    freq_keys = list(DRINKING_FREQUENCY)
                    freq = st.selectbox("Usual drinking frequency", freq_keys,
                                        format_func=lambda k: DRINKING_FREQUENCY[k][0],
                                        index=freq_keys.index(ap.get("drinking_frequency") or "few_per_week"))
                    c3, c4, c5 = st.columns(3)
                    per_occasion = c3.number_input("Drinks per occasion", 0.0, 100.0,
                                                   value=float(ap.get("drinks_per_occasion") or 3), step=0.5)
                    bevs = list(BEVERAGES)
                    bev = c4.selectbox("Usual drink", bevs, index=bevs.index(ap["beverage_type"])
                                       if ap.get("beverage_type") in bevs else 0)
                    spend = c5.number_input(f"Spend per occasion ({ctx.currency})", 0.0,
                                            value=float(ap.get("spend_per_occasion") or 0), step=50.0)
                    risk = st.toggle("I may be physically dependent on alcohol (safety reminders on)",
                                     value=bool(ap.get("dependence_risk")))
                    fields = {"drinking_frequency": freq, "drinking_days_per_week": DRINKING_FREQUENCY[freq][1],
                              "drinks_per_occasion": per_occasion, "beverage_type": bev,
                              "spend_per_occasion": spend, "dependence_risk": risk}

                goal_types = {"quit": "Quit completely", "reduce": "Cut down"}
                goal_type = st.radio("Goal", list(goal_types), format_func=goal_types.get, horizontal=True,
                                     index=list(goal_types).index(goal.get("goal_type", "quit"))
                                     if goal.get("goal_type") in goal_types else 0)
                target = st.number_input("Target per day (when cutting down)", 0.0, 100.0,
                                         value=float(goal.get("target_per_day") or 0), step=1.0)
                if st.form_submit_button("Save", type="primary"):
                    if not active and len([x for x in ctx.addictions if x != a]) == 0:
                        st.error("You need to track at least one habit.")
                    else:
                        try:
                            dbs.upsert_addiction_profile(a, {**fields, "is_active": active,
                                                             "tracking_start_date": start.isoformat(),
                                                             "quit_date": quit_date.isoformat()})
                            title = (f"Cut down to {target:g} a day" if goal_type == "reduce"
                                     else f"Quit {label.lower()} completely")
                            if (goal.get("goal_type"), float(goal.get("target_per_day") or 0)) != (goal_type, target):
                                dbs.set_goal(a, goal_type, title, target if goal_type == "reduce" else 0, quit_date)
                            kinds = set(ctx.addictions) - {a} | ({a} if active else set())
                            dbs.update_profile({"addiction_type": "both" if len(kinds) == 2 else next(iter(kinds))})
                        except Exception:
                            st.error("Couldn't save your plan.")
                        else:
                            saved(f"{label} plan saved.")

# ---------------------------------------------------------------- tracking & units
with tabs[2]:
    with st.form("tracking"):
        zones = timezone_choices()
        tz_name = st.selectbox("Timezone", zones, index=zones.index(profile["timezone"])
                               if profile.get("timezone") in zones else zones.index("UTC"),
                               help="Changing timezone shifts how hours and days are grouped. Hours you logged "
                                    "in another timezone stay stored but may not line up with the new hour grid.")
        c1, c2 = st.columns(2)
        wake = c1.selectbox("Tracking starts (wake up)", list(range(24)), index=ctx.wake_hour, format_func=hour_fmt)
        sleep = c2.selectbox("Tracking ends (sleep)", list(range(1, 25)), index=ctx.sleep_hour - 1, format_func=hour_fmt)
        c3, c4, c5 = st.columns(3)
        currency = c3.selectbox("Currency", CURRENCIES, index=CURRENCIES.index(ctx.currency)
                                if ctx.currency in CURRENCIES else 0)
        regions = list(STANDARD_DRINK_GRAMS)
        region = c4.selectbox("Standard drink definition", regions,
                              index=regions.index(profile.get("standard_drink_region") or "WHO"),
                              format_func=lambda r: STANDARD_DRINK_GRAMS[r][1])
        unit = c5.selectbox("Drink volume unit", ["ml", "oz"], index=0 if profile.get("volume_unit") != "oz" else 1)
        if st.form_submit_button("Save tracking settings", type="primary"):
            if error := validate_tracking_window(wake, sleep):
                st.error(error)
            else:
                try:
                    dbs.update_profile({"timezone": tz_name, "wake_hour": wake, "sleep_hour": sleep,
                                        "currency_symbol": currency, "standard_drink_region": region,
                                        "volume_unit": unit})
                except Exception:
                    st.error("Couldn't save tracking settings.")
                else:
                    saved("Tracking settings saved.")
    st.caption("🌗 **Theme:** Reclaim follows your device's light/dark setting. To switch manually, open the "
               "⋮ menu (top right) → *Settings* → *Theme*.")

# ---------------------------------------------------------------- reminders
with tabs[3]:
    st.caption("Reminders currently appear inside the app. Email and browser notifications are planned – "
               "your choices here will carry over.")
    try:
        prefs = dbs.get_notification_prefs()
    except Exception:
        prefs = None
        st.error("Couldn't load reminder preferences.")
    if prefs:
        with st.form("reminders"):
            hourly = st.toggle("Hourly tracking nudges", value=prefs["hourly_reminder"])
            c1, c2 = st.columns(2)
            morning = c1.toggle("Morning check-in", value=prefs["morning_checkin"])
            morning_time = c2.time_input("Morning time", value=datetime.strptime(prefs["morning_time"][:5], "%H:%M").time())
            c3, c4 = st.columns(2)
            evening = c3.toggle("Evening reflection", value=prefs["evening_reflection"])
            evening_time = c4.time_input("Evening time", value=datetime.strptime(prefs["evening_time"][:5], "%H:%M").time())
            motivation = st.toggle("Daily motivation", value=prefs["daily_motivation"])
            weekly = st.toggle("Weekly report", value=prefs["weekly_report"])
            milestones = st.toggle("Milestone celebrations", value=prefs["milestone_alerts"])
            if st.form_submit_button("Save reminders", type="primary"):
                try:
                    dbs.update_notification_prefs({
                        "hourly_reminder": hourly, "morning_checkin": morning,
                        "morning_time": morning_time.strftime("%H:%M"), "evening_reflection": evening,
                        "evening_time": evening_time.strftime("%H:%M"), "daily_motivation": motivation,
                        "weekly_report": weekly, "milestone_alerts": milestones,
                    })
                except Exception:
                    st.error("Couldn't save reminders.")
                else:
                    saved("Reminder preferences saved.")

# ---------------------------------------------------------------- privacy & data
with tabs[4]:
    st.markdown("#### Where your data lives")
    st.write("Your records are stored in a **Supabase** PostgreSQL database and the app is served by "
             "**Streamlit Community Cloud** (or wherever this copy is deployed). Both are third-party services "
             "that process data on their servers. Row-level security means only your signed-in account can "
             "read your records. Reclaim does not sell or share your data, and the optional AI companion "
             "(coming later) will only receive the minimum information you allow.")

    st.markdown("#### Export your data")
    if st.button("Prepare my data export", icon=":material/download:"):
        try:
            st.session_state.export_blob = json.dumps(
                {"exported_at": datetime.now(UTC).isoformat(), **dbs.export_all_data()}, indent=2, default=str)
        except Exception:
            st.error("Couldn't prepare the export.")
    if blob := st.session_state.get("export_blob"):
        st.download_button("Download reclaim-export.json", blob, file_name="reclaim-export.json",
                           mime="application/json", type="primary", on_click="ignore")

    st.markdown("#### Delete journal entries")
    confirm_journal = st.checkbox("I understand all my journal entries will be permanently deleted.")
    if st.button("Delete all journal entries", disabled=not confirm_journal):
        try:
            dbs.delete_all_journal_entries()
        except Exception:
            st.error("Couldn't delete journal entries.")
        else:
            saved("All journal entries deleted.")

    st.markdown("#### Delete account")
    st.caption("This permanently deletes your account and **all** of your recovery data. It cannot be undone. "
               "Consider exporting your data first.")
    typed = st.text_input("Type DELETE to confirm", key="delete_confirm")
    if st.button("Delete my account permanently", type="primary", disabled=typed != "DELETE"):
        ok, message = auth_service.delete_account()
        if ok:
            st.session_state.auth_flash = message
            st.rerun()
        st.error(message)

# ---------------------------------------------------------------- account
with tabs[5]:
    st.caption(f"Signed in as **{st.session_state.get('user_email', '')}**")
    with st.form("email"):
        new_email = st.text_input("New email address")
        if st.form_submit_button("Change email"):
            if error := validate_email(new_email):
                st.error(error)
            else:
                ok, message = auth_service.update_email(new_email)
                (st.success if ok else st.error)(message)
    with st.form("password"):
        pw = st.text_input("New password", type="password", autocomplete="new-password")
        pw2 = st.text_input("Confirm new password", type="password", autocomplete="new-password")
        if st.form_submit_button("Update password"):
            error = validate_password(pw) or (None if pw == pw2 else "Passwords don't match.")
            if error:
                st.error(error)
            else:
                ok, message = auth_service.update_password(pw)
                (st.success if ok else st.error)(message)

"""Onboarding wizard shown once after registration.

Answers are collected in st.session_state["onb"] across steps and saved
to Supabase only when the user finishes.
"""

from datetime import date, datetime, timedelta

import streamlit as st

from components.cards import page_header, progress_bar
from components.navigation import require_context
from services import database_service as dbs
from utils.constants import (
    ALCOHOL, BEVERAGES, CURRENCIES, DRINKING_FREQUENCY, EMERGENCY_NOTE, SMOKING,
)
from utils.datetime_utils import UTC, get_tz, timezone_choices
from utils.validators import clean_text, validate_tracking_window

ctx = require_context()
onb: dict = st.session_state.setdefault("onb", {})
step: int = st.session_state.setdefault("onb_step", 0)


def chosen() -> list[str]:
    kind = onb.get("addiction_type", "smoking")
    return [SMOKING, ALCOHOL] if kind == "both" else [kind]


def steps() -> list[str]:
    names = ["about"]
    if SMOKING in chosen():
        names.append("smoking")
    if ALCOHOL in chosen():
        names.append("alcohol")
    return names + ["motivation"]


def go(delta: int) -> None:
    st.session_state.onb_step = max(0, min(len(steps()) - 1, step + delta))
    st.rerun()


def nav_buttons(valid: bool = True, error: str | None = None, last: bool = False) -> bool:
    """Back / Next buttons. Returns True when 'Finish' is pressed on the last step."""
    left, right = st.columns(2)
    if step > 0 and left.button("← Back", width="stretch"):
        go(-1)
    if right.button("Finish setup ✓" if last else "Continue →", type="primary", width="stretch"):
        if not valid:
            st.error(error or "Please complete the required fields.")
            return False
        if last:
            return True
        go(1)
    return False


current = steps()[min(step, len(steps()) - 1)]
_, center, _ = st.columns([1, 2.6, 1])

with center:
    page_header(f"Let's set up Reclaim{', ' + onb['name'] if onb.get('name') else ''}",
                "A few questions so your tracking, savings and milestones are personal to you. "
                "You can change any of this later in Settings.", eyebrow="Getting started")
    progress_bar(100 * (step + 1) / len(steps()), f"Step {step + 1} of {len(steps())}", "")

    # ------------------------------------------------------------------ about
    if current == "about":
        st.subheader("About you")
        onb["name"] = st.text_input("What should we call you?", value=onb.get("name", ""), max_chars=80)
        c1, c2 = st.columns(2)
        onb["age"] = c1.number_input("Age (optional)", min_value=13, max_value=120, value=onb.get("age"), step=1)
        zones = timezone_choices()
        detected = onb.get("timezone") or st.context.timezone or "UTC"
        onb["timezone"] = c2.selectbox("Your timezone", zones,
                                       index=zones.index(detected) if detected in zones else zones.index("UTC"),
                                       help="Hourly slots and days follow this timezone.")
        st.subheader("What would you like to work on?")
        options = {"smoking": "🚬 Smoking", "alcohol": "🍷 Alcohol", "both": "🚬🍷 Both"}
        onb["addiction_type"] = st.radio("Focus", list(options), format_func=options.get, horizontal=True,
                                         index=list(options).index(onb.get("addiction_type", "smoking")),
                                         label_visibility="collapsed")
        name_ok = bool(onb["name"].strip())
        nav_buttons(valid=name_ok, error="Please tell us what to call you.")

    # ---------------------------------------------------------------- smoking
    elif current == "smoking":
        st.subheader("🚬 Your smoking")
        st.caption("These numbers are your *baseline* – we use them to estimate cigarettes avoided and money saved.")
        c1, c2 = st.columns(2)
        onb["cigs_per_day"] = c1.number_input("Cigarettes per day (on average)", min_value=1, max_value=100,
                                              value=onb.get("cigs_per_day", 10), step=1)
        onb["currency"] = c2.selectbox("Currency", CURRENCIES,
                                       index=CURRENCIES.index(onb.get("currency", "₹")))
        c3, c4 = st.columns(2)
        onb["cost_per_cig"] = c3.number_input(f"Cost per cigarette ({onb['currency']})", min_value=0.0,
                                              value=float(onb.get("cost_per_cig", 18.0)), step=0.5,
                                              help="Pack price ÷ cigarettes per pack.")
        onb["smoking_quit_date"] = c4.date_input("Preferred quit date", value=onb.get("smoking_quit_date", date.today()),
                                                 min_value=date.today() - timedelta(days=365 * 5))
        goals = {"quit": "Quit completely", "reduce": "Cut down first"}
        onb["smoking_goal"] = st.radio("Your goal", list(goals), format_func=goals.get, horizontal=True,
                                       index=list(goals).index(onb.get("smoking_goal", "quit")))
        if onb["smoking_goal"] == "reduce":
            onb["smoking_target"] = st.number_input("Target cigarettes per day", min_value=0,
                                                    max_value=int(onb["cigs_per_day"]),
                                                    value=min(onb.get("smoking_target", 5), int(onb["cigs_per_day"])))
        nav_buttons()

    # ---------------------------------------------------------------- alcohol
    elif current == "alcohol":
        st.subheader("🍷 Your drinking")
        freq_keys = list(DRINKING_FREQUENCY)
        onb["drink_freq"] = st.selectbox("How often do you usually drink?", freq_keys,
                                         format_func=lambda k: DRINKING_FREQUENCY[k][0],
                                         index=freq_keys.index(onb.get("drink_freq", "few_per_week")))
        c1, c2 = st.columns(2)
        onb["drinks_per_occasion"] = c1.number_input("Drinks on a typical occasion", min_value=0.5, max_value=50.0,
                                                     value=float(onb.get("drinks_per_occasion", 3.0)), step=0.5)
        bevs = list(BEVERAGES)
        onb["beverage"] = c2.selectbox("Usual drink", bevs, index=bevs.index(onb.get("beverage", "Beer")))
        if "currency" not in onb or SMOKING not in chosen():
            onb["currency"] = st.selectbox("Currency", CURRENCIES, index=CURRENCIES.index(onb.get("currency", "₹")))
        c3, c4 = st.columns(2)
        onb["spend_per_occasion"] = c3.number_input(f"Approx. spend per occasion ({onb['currency']})",
                                                    min_value=0.0, value=float(onb.get("spend_per_occasion", 500.0)),
                                                    step=50.0)
        onb["alcohol_quit_date"] = c4.date_input("Preferred quit date", value=onb.get("alcohol_quit_date", date.today()),
                                                 min_value=date.today() - timedelta(days=365 * 5), key="aqd")

        st.subheader("A quick safety check")
        st.caption("Your answers stay private. They help us give you safe guidance.")
        questions = {
            "q_daily": "Do you drink every day or almost every day, or have you been drinking heavily for weeks or longer?",
            "q_withdrawal": "When you cut down or stop, have you had shaking, sweating, nausea, a racing heart, "
                            "anxiety or trouble sleeping?",
            "q_morning": "Do you sometimes need a drink in the morning to feel steady or normal?",
            "q_severe": "Have you ever had a seizure, hallucinations or severe confusion after stopping drinking?",
        }
        for key, text in questions.items():
            onb[key] = st.toggle(text, value=onb.get(key, False), key=f"tg_{key}")
        risk = any(onb[k] for k in questions)
        onb["dependence_risk"] = risk
        if onb["q_severe"]:
            st.error("**Please talk to a doctor before you stop or cut down.** You've had serious withdrawal "
                     "symptoms before, so stopping on your own could be dangerous. A doctor can help you withdraw "
                     f"safely, often with medical supervision.\n\n{EMERGENCY_NOTE}")
        elif risk:
            st.warning("**Your body may be physically dependent on alcohol.** Stopping suddenly can cause "
                       "withdrawal, which can be dangerous. Please get a medical assessment before you stop or "
                       "sharply cut down – a doctor can help you do it safely. Reclaim can still help you track "
                       "and reduce in the meantime.")

        goals = {"quit": "Stop drinking", "reduce": "Cut down"}
        if risk:
            goals = {"reduce": "Cut down safely, with medical guidance", "quit": "Stop – with my doctor's support"}
        default_goal = onb.get("alcohol_goal", next(iter(goals)))
        onb["alcohol_goal"] = st.radio("Your goal", list(goals), format_func=goals.get, horizontal=True,
                                       index=list(goals).index(default_goal) if default_goal in goals else 0)
        nav_buttons()

    # ------------------------------------------------------------- motivation
    elif current == "motivation":
        st.subheader("Your reasons")
        st.caption("These appear on your dashboard on the hard days. Write them in your own words.")
        onb["why_quit"] = st.text_area("Why do you want to change?", value=onb.get("why_quit", ""), max_chars=2000,
                                       placeholder="e.g. I want to breathe easily when I play with my kids.")
        onb["aspirations"] = st.text_area("What do you want to achieve?", value=onb.get("aspirations", ""),
                                          max_chars=2000, placeholder="e.g. Run 5 km by summer. Save for a trip.")
        onb["motivators"] = st.text_area("What keeps you motivated?", value=onb.get("motivators", ""),
                                         max_chars=2000, placeholder="e.g. My family, my health, feeling in control.")

        st.subheader("Your tracking hours")
        st.caption("Hourly slots are created for these waking hours. You can change this anytime.")
        c1, c2 = st.columns(2)
        hours = list(range(0, 25))
        fmt = lambda h: "Midnight" if h in (0, 24) else f"{h % 12 or 12} {'AM' if h < 12 else 'PM'}"  # noqa: E731
        onb["wake_hour"] = c1.selectbox("I usually wake up at", hours[:24], index=onb.get("wake_hour", 7), format_func=fmt)
        onb["sleep_hour"] = c2.selectbox("I usually sleep at", hours[1:], index=onb.get("sleep_hour", 23) - 1,
                                         format_func=fmt)
        window_error = validate_tracking_window(onb["wake_hour"], onb["sleep_hour"])
        has_reason = bool(onb["why_quit"].strip())

        if nav_buttons(valid=has_reason and not window_error,
                       error=window_error or "Please share at least one reason for wanting to change.", last=True):
            try:
                with st.spinner("Setting up your space…"):
                    today = datetime.now(UTC).astimezone(get_tz(onb["timezone"])).date()
                    dbs.update_profile({
                        "display_name": onb["name"].strip(),
                        "age": onb.get("age"),
                        "timezone": onb["timezone"],
                        "addiction_type": onb["addiction_type"],
                        "currency_symbol": onb.get("currency", "₹"),
                        "why_quit": clean_text(onb.get("why_quit"), 2000),
                        "aspirations": clean_text(onb.get("aspirations"), 2000),
                        "motivators": clean_text(onb.get("motivators"), 2000),
                        "wake_hour": onb["wake_hour"],
                        "sleep_hour": onb["sleep_hour"],
                    })
                    if SMOKING in chosen():
                        dbs.upsert_addiction_profile(SMOKING, {
                            "is_active": True,
                            "tracking_start_date": today.isoformat(),
                            "quit_date": onb["smoking_quit_date"].isoformat(),
                            "baseline_per_day": onb["cigs_per_day"],
                            "cost_per_unit": onb["cost_per_cig"],
                        })
                        reduce = onb["smoking_goal"] == "reduce"
                        dbs.set_goal(SMOKING, onb["smoking_goal"],
                                     f"Cut down to {onb['smoking_target']} cigarettes a day" if reduce
                                     else "Quit smoking completely",
                                     target_per_day=onb.get("smoking_target") if reduce else 0,
                                     target_date=onb["smoking_quit_date"])
                    if ALCOHOL in chosen():
                        dbs.upsert_addiction_profile(ALCOHOL, {
                            "is_active": True,
                            "tracking_start_date": today.isoformat(),
                            "quit_date": onb["alcohol_quit_date"].isoformat(),
                            "drinking_frequency": onb["drink_freq"],
                            "drinking_days_per_week": DRINKING_FREQUENCY[onb["drink_freq"]][1],
                            "drinks_per_occasion": onb["drinks_per_occasion"],
                            "beverage_type": onb["beverage"],
                            "spend_per_occasion": onb["spend_per_occasion"],
                            "dependence_risk": onb.get("dependence_risk", False),
                        })
                        dbs.set_goal(ALCOHOL, onb["alcohol_goal"],
                                     "Stop drinking" if onb["alcohol_goal"] == "quit" else "Cut down on drinking",
                                     target_date=onb["alcohol_quit_date"])
                    # Completing onboarding last means a failure above simply leaves the wizard open.
                    dbs.update_profile({"onboarding_completed_at": datetime.now(UTC).isoformat()})
            except Exception:
                st.error("We couldn't save your answers. Please check your connection and try again.")
            else:
                st.session_state.pop("onb", None)
                st.session_state.pop("onb_step", None)
                st.session_state.flash = "You're all set. One hour at a time – let's begin. 🌱"
                dbs.load_context(force=True)
                st.rerun()

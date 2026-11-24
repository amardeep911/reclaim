"""Forms shared by several pages. Each returns cleaned values on submit, else None."""

from datetime import datetime

import streamlit as st

from services.database_service import UserContext
from utils.calculations import standard_drinks
from utils.constants import BEVERAGES, DRINK_OCCASIONS, MOODS, MOOD_EMOJI, TRIGGERS
from utils.datetime_utils import UTC, local_now
from utils.validators import clean_text

ML_PER_OZ = 29.5735


def _when_inputs(key: str, ctx: UserContext, default: datetime | None) -> datetime:
    """Local date + time pickers, returned as an aware UTC datetime."""
    local = (default or datetime.now(UTC)).astimezone(ctx.tz)
    c1, c2 = st.columns(2)
    day = c1.date_input("Date", value=local.date(), max_value=local_now(ctx.tz).date(), key=f"{key}-date")
    at = c2.time_input("Time", value=local.time().replace(second=0, microsecond=0), step=300, key=f"{key}-time")
    return datetime.combine(day, at, tzinfo=ctx.tz).astimezone(UTC)


def _index(options: list, value, fallback: int | None = None) -> int | None:
    return options.index(value) if value in options else fallback


def smoking_form(key: str, ctx: UserContext, defaults: dict | None = None, submit_label: str = "Save") -> dict | None:
    d = defaults or {}
    ap = ctx.addiction_profiles.get("smoking", {})
    cost_each = float(ap.get("cost_per_unit") or 0)
    with st.form(key, clear_on_submit=not defaults, border=True):
        occurred_at = _when_inputs(key, ctx, d.get("occurred_at"))
        c1, c2 = st.columns(2)
        quantity = c1.number_input("Cigarettes", min_value=1, max_value=100, step=1,
                                   value=int(float(d.get("quantity") or 1)), key=f"{key}-qty")
        trigger = c2.selectbox("Trigger", TRIGGERS, index=_index(TRIGGERS, d.get("trigger")),
                               placeholder="What triggered it?", key=f"{key}-trigger")
        c3, c4 = st.columns(2)
        mood = c3.selectbox("Mood", MOODS, index=_index(MOODS, d.get("mood")), placeholder="How did you feel?",
                            format_func=lambda m: f"{MOOD_EMOJI[m]} {m}", key=f"{key}-mood")
        location = c4.text_input("Location (optional)", value=d.get("location") or "", max_chars=120,
                                 key=f"{key}-loc")
        notes = st.text_area("Notes (optional)", value=d.get("notes") or "", max_chars=1000, height=80,
                             key=f"{key}-notes")
        if not st.form_submit_button(submit_label, type="primary", width="stretch"):
            return None
    return {
        "occurred_at": occurred_at,
        "quantity": float(quantity),
        "cost": round(quantity * cost_each, 2) if cost_each else None,
        "trigger": trigger,
        "mood": mood,
        "location": clean_text(location, 120),
        "notes": clean_text(notes, 1000),
    }


def alcohol_form(key: str, ctx: UserContext, defaults: dict | None = None, submit_label: str = "Save") -> dict | None:
    d = defaults or {}
    use_oz = ctx.profile.get("volume_unit") == "oz"
    beverage_names = list(BEVERAGES)
    # Outside the form so changing it immediately refreshes the serving defaults below.
    beverage = st.selectbox("Beverage", beverage_names,
                            index=_index(beverage_names, d.get("beverage_type"), 0), key=f"{key}-bev")
    serving_ml, typical_abv = BEVERAGES[beverage]
    if d.get("beverage_type") == beverage and d.get("volume_ml"):
        serving_ml = float(d["volume_ml"])
        typical_abv = float(d["abv_percent"]) if d.get("abv_percent") is not None else typical_abv

    with st.form(f"{key}-{beverage}", clear_on_submit=not defaults, border=True):
        occurred_at = _when_inputs(f"{key}-{beverage}", ctx, d.get("occurred_at"))
        c1, c2, c3 = st.columns(3)
        quantity = c1.number_input("Number of drinks", min_value=0.5, max_value=50.0, step=0.5,
                                   value=float(d.get("quantity") or 1), key=f"{key}-{beverage}-qty")
        if use_oz:
            size = c2.number_input("Serving size (oz)", min_value=0.5, max_value=100.0, step=0.5,
                                   value=round(serving_ml / ML_PER_OZ, 1), key=f"{key}-{beverage}-oz")
            volume_ml = size * ML_PER_OZ
        else:
            volume_ml = c2.number_input("Serving size (ml)", min_value=10.0, max_value=2000.0, step=10.0,
                                        value=float(serving_ml), key=f"{key}-{beverage}-ml")
        abv = c3.number_input("Alcohol % (optional)", min_value=0.0, max_value=96.0, step=0.5,
                              value=float(typical_abv), key=f"{key}-{beverage}-abv",
                              help="Pre-filled with a typical value for this drink. Check the label if you can.")
        c4, c5 = st.columns(2)
        occasion = c4.selectbox("Occasion", DRINK_OCCASIONS, index=_index(DRINK_OCCASIONS, d.get("occasion")),
                                placeholder="Where / why?", key=f"{key}-{beverage}-occ")
        cost = c5.number_input(f"Amount spent ({ctx.currency}, optional)", min_value=0.0, step=10.0,
                               value=float(d["cost"]) if d.get("cost") is not None else None,
                               key=f"{key}-{beverage}-cost")
        c6, c7 = st.columns(2)
        trigger = c6.selectbox("Trigger", TRIGGERS, index=_index(TRIGGERS, d.get("trigger")),
                               placeholder="What triggered it?", key=f"{key}-{beverage}-trigger")
        mood = c7.selectbox("Mood", MOODS, index=_index(MOODS, d.get("mood")), placeholder="How did you feel?",
                            format_func=lambda m: f"{MOOD_EMOJI[m]} {m}", key=f"{key}-{beverage}-mood")
        notes = st.text_area("Notes (optional)", value=d.get("notes") or "", max_chars=1000, height=80,
                             key=f"{key}-{beverage}-notes")
        submitted = st.form_submit_button(submit_label, type="primary", width="stretch")

    if not submitted:
        return None
    std = standard_drinks(quantity, volume_ml, abv, ctx.grams_per_drink)
    return {
        "occurred_at": occurred_at,
        "quantity": float(quantity),
        "beverage_type": beverage,
        "volume_ml": round(volume_ml, 1),
        "abv_percent": abv,
        "standard_drinks": std,
        "occasion": occasion,
        "cost": cost,
        "trigger": trigger,
        "mood": mood,
        "notes": clean_text(notes, 1000),
    }


def daily_checkin_form(key: str, existing: dict | None) -> dict | None:
    e = existing or {}
    with st.form(key, border=True):
        mood = st.segmented_control("Mood", MOODS, default=e.get("mood"), key=f"{key}-mood",
                                    format_func=lambda m: f"{MOOD_EMOJI[m]} {m}")
        c1, c2 = st.columns(2)
        sleep_hours = c1.number_input("Sleep (hours)", 0.0, 24.0, step=0.5,
                                      value=float(e["sleep_hours"]) if e.get("sleep_hours") is not None else None,
                                      key=f"{key}-sleep")
        sleep_quality = c2.select_slider("Sleep quality", options=[1, 2, 3, 4, 5], value=e.get("sleep_quality") or 3,
                                         format_func=lambda v: ["Very poor", "Poor", "Okay", "Good", "Great"][v - 1],
                                         key=f"{key}-sq")
        c3, c4 = st.columns(2)
        exercise = c3.number_input("Exercise (minutes)", 0, 1440, step=5,
                                   value=int(e["exercise_minutes"]) if e.get("exercise_minutes") is not None else None,
                                   key=f"{key}-ex")
        water = c4.number_input("Water (glasses)", 0, 50, step=1,
                                value=int(e["water_glasses"]) if e.get("water_glasses") is not None else None,
                                key=f"{key}-water")
        reflection = st.text_area("A quick reflection (optional)", value=e.get("reflection") or "",
                                  max_chars=2000, height=80, key=f"{key}-refl",
                                  placeholder="What helped today? What was hard?")
        if not st.form_submit_button("Save check-in", type="primary", width="stretch"):
            return None
    return {
        "mood": mood,
        "sleep_hours": sleep_hours,
        "sleep_quality": sleep_quality,
        "exercise_minutes": exercise,
        "water_glasses": water,
        "reflection": clean_text(reflection, 2000),
    }

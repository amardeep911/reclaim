"""Hourly Recovery Tracker – the heart of Reclaim.

Fast path: the "quick log" card asks about the most recent finished hour you
haven't logged yet – one tap and it's saved.  Everything else (editing past
hours, notes, multiple consumption, bulk marking, other dates) lives below.
"""

from datetime import timedelta

import streamlit as st

from components.cards import page_header, section, stat_cards
from components.hourly_timeline import legend, sleep_card, slot_grid, slot_status, timeline_strip
from components.navigation import addiction_picker, require_context
from services import tracking_service as ts
from services.tracking_service import TrackingError
from utils import calculations as calc
from utils.constants import (
    ADDICTIONS, ALCOHOL, BEVERAGES, CONSUMED, CRAVING_RESISTED, STATUS_META, SUCCESS,
)
from utils.datetime_utils import day_bounds_utc, format_local, generate_day_slots, local_today, now_utc
from utils.validators import clean_text

ctx = require_context()
tz = ctx.tz

page_header("Hourly Recovery Tracker", "One hour at a time. Log how each hour went – it takes a second.",
            eyebrow="Track")

if flash := st.session_state.pop("hourly_flash", None):
    st.toast(flash, icon="✅")

addiction = addiction_picker(ctx, key="hourly_addiction")
meta = ADDICTIONS[addiction]

# ---------------------------------------------------------------- date picker
today = local_today(tz)
day = st.session_state.get("hourly_day", today)
c_prev, c_date, c_next, c_today = st.columns([1, 3, 1, 1.4], vertical_alignment="bottom")
if c_prev.button("◀", help="Previous day", width="stretch"):
    day -= timedelta(days=1)
if c_next.button("▶", help="Next day", width="stretch", disabled=day >= today):
    day += timedelta(days=1)
if c_today.button("Today", width="stretch", disabled=day == today):
    day = today
day = c_date.date_input("Day", value=day, max_value=today, label_visibility="collapsed")
st.session_state.hourly_day = day

# ---------------------------------------------------------------- data
now = now_utc()
slots = generate_day_slots(day, tz, ctx.wake_hour, ctx.sleep_hour)
day_start, day_end = day_bounds_utc(day, tz)
try:
    logs = ts.get_hourly_logs(day_start, day_end, addiction)
    day_consumption = ts.get_consumption(day_start, day_end, addiction)
except Exception:
    st.error("Couldn't load your hours. Check your connection and try again.")
    st.stop()
logs_by_start = {row["slot_start"]: row for row in logs}
sel_key = f"hourly_sel_{addiction}_{day.isoformat()}"


def default_consumption_fields() -> dict:
    """Sensible defaults for a one-tap consumption entry."""
    ap = ctx.addiction_profiles[addiction]
    if addiction == ALCOHOL:
        beverage = ap.get("beverage_type") if ap.get("beverage_type") in BEVERAGES else "Other"
        volume, abv = BEVERAGES[beverage]
        return {"beverage_type": beverage, "volume_ml": volume, "abv_percent": abv,
                "standard_drinks": calc.standard_drinks(1, volume, abv, ctx.grams_per_drink)}
    cost = float(ap.get("cost_per_unit") or 0)
    return {"cost": cost or None}


def log_quick_consumption(slot_start, quantity: float = 1) -> None:
    occurred = min(slot_start + timedelta(minutes=30), now_utc())
    fields = default_consumption_fields()
    if addiction == ALCOHOL:
        fields["standard_drinks"] = round(fields["standard_drinks"] * quantity, 2)
    elif fields.get("cost"):
        fields["cost"] = round(fields["cost"] * quantity, 2)
    ts.log_consumption(addiction, occurred, quantity, tz, **fields)


def save(action, message: str) -> None:
    """Run a write, show friendly errors, rerun on success."""
    try:
        action()
    except TrackingError as exc:
        st.error(str(exc))
        return
    except Exception:
        st.error("Couldn't save that. Please try again.")
        return
    st.session_state.hourly_flash = message
    st.rerun()


# ---------------------------------------------------------------- last night + quick log
if day == today:
    sleep_card(ctx, addiction, key="hourly")

    finished = [s for s in slots if s.end <= now and s.start not in logs_by_start]
    current = next((s for s in slots if s.start <= now < s.end), None)
    target = finished[-1] if finished else None
    with st.container(border=True):
        if target:
            st.markdown(f"#### How was **{target.range_label}**?")
            q1, q2, q3 = st.columns(3)
            if q1.button(f"✅ {meta['free']}", key="quick-success", width="stretch"):
                save(lambda: ts.set_hour_status(addiction, target.start, SUCCESS),
                     f"{target.range_label} logged as {meta['free'].lower()}. Well done.")
            if q2.button("💪 Craving, but resisted", key="quick-craving", width="stretch"):
                save(lambda: ts.set_hour_status(addiction, target.start, CRAVING_RESISTED),
                     "Craving resisted – that's real strength.")
            if q3.button(f"● I {meta['verb'].lower()}", key="quick-consumed", width="stretch"):
                st.session_state[sel_key] = target.start.isoformat()
                save(lambda: log_quick_consumption(target.start),
                     f"Logged 1 {meta['unit']}. You can adjust it below. Every hour is a fresh start.")
            if len(finished) > 1:
                st.caption(f"{len(finished) - 1} earlier hour(s) today are still untracked – tap them below "
                           "or use “Mark several hours at once”.")
        elif current:
            st.markdown("#### You're all caught up 🌿")
            st.caption(f"The current hour ({current.range_label}) can be logged once it's over – or tap it "
                       "below if something happens now.")
        else:
            st.markdown("#### Outside your tracking hours")
            st.caption("You can still review and edit earlier hours below.")

# ---------------------------------------------------------------- timeline
section(f"{meta['icon']} {day.strftime('%A, %d %B')}",
        "Grey hours aren't tracked yet – they never count as success or failure.")
if not slots:
    st.info("No hours in your tracking window for this day. Adjust your waking hours in Settings.")
    st.stop()

timeline_strip(slots, logs_by_start, now)
legend()

selected_iso = st.session_state.get(sel_key)
selected = next((s for s in slots if s.start.isoformat() == selected_iso), None)
clicked = slot_grid(slots, logs_by_start, now, f"{addiction}-{day.isoformat()}", selected.start if selected else None)
if clicked is not None:
    st.session_state[sel_key] = clicked.isoformat()
    st.rerun()

# ---------------------------------------------------------------- editor
if selected:
    status = slot_status(selected, logs_by_start, now)
    row = logs_by_start.get(selected.start)
    in_slot = [c for c in day_consumption if selected.start <= c["occurred_at"] < selected.end]
    with st.container(border=True):
        st.markdown(f"#### {selected.range_label} · {STATUS_META[status]['label']}")
        options = [SUCCESS, CRAVING_RESISTED, CONSUMED]
        labels = {SUCCESS: f"✅ {meta['free']}", CRAVING_RESISTED: "💪 Craving resisted",
                  CONSUMED: f"● {meta['verb']}"}
        new_status = st.segmented_control("Status", options, default=status if status in options else None,
                                          format_func=labels.get, key=f"edit-status-{sel_key}-{status}")
        notes = st.text_input("Note (optional)", value=(row or {}).get("notes") or "", max_chars=1000,
                              key=f"edit-notes-{sel_key}-{selected.start.isoformat()}",
                              placeholder="What was happening this hour?")

        quantity = None
        if new_status == CONSUMED:
            if in_slot:
                total = sum(float(c["quantity"]) for c in in_slot)
                st.caption(f"Logged this hour: **{total:g} {meta['units']}**")
                for c in in_slot:
                    a, b = st.columns([4, 1], vertical_alignment="center")
                    detail = c.get("beverage_type") or meta["unit"]
                    a.write(f"{format_local(c['occurred_at'], tz, '%I:%M %p')} · {float(c['quantity']):g} × {detail}")
                    if b.button("Delete", key=f"del-{c['id']}", width="stretch"):
                        save(lambda cid=c["id"]: ts.delete_consumption(cid, tz), "Entry deleted.")
            quantity = st.number_input(f"Add {meta['units']}" if in_slot else f"How many {meta['units']}?",
                                       min_value=0 if in_slot else 1, max_value=50,
                                       value=0 if in_slot else 1, step=1, key=f"edit-qty-{sel_key}")
            st.caption("Need trigger, mood or drink details? Use the Consumption page.")
        elif in_slot:
            st.warning(f"This hour has {len(in_slot)} logged {meta['unit']} entr{'y' if len(in_slot) == 1 else 'ies'}. "
                       "Delete them (choose the consumed status) before marking it as free.")

        s1, s2 = st.columns(2)
        if s1.button("Save", type="primary", width="stretch", disabled=new_status is None or
                     (new_status != CONSUMED and bool(in_slot))):
            def apply():
                if new_status == CONSUMED and quantity:
                    log_quick_consumption(selected.start, quantity)
                ts.set_hour_status(addiction, selected.start, new_status, clean_text(notes, 1000), update_notes=True)
            save(apply, f"{selected.range_label} saved.")
        if s2.button("Clear (not tracked)", width="stretch", disabled=row is None):
            save(lambda: ts.clear_hour(addiction, selected.start), f"{selected.range_label} cleared.")

# ---------------------------------------------------------------- bulk
with st.expander("Mark several hours at once"):
    started = [s for s in slots if s.start <= now]
    if len(started) < 2:
        st.caption("Bulk marking becomes available once at least two hours of this day have started.")
    else:
        labels_by_iso = {s.start.isoformat(): s.label for s in started}
        isos = list(labels_by_iso)
        b1, b2 = st.columns(2)
        first = b1.selectbox("From", isos, format_func=labels_by_iso.get, key="bulk-from")
        last = b2.selectbox("To (inclusive)", isos, index=len(isos) - 1, format_func=labels_by_iso.get, key="bulk-to")
        bulk_status = st.radio("Mark as", [SUCCESS, CRAVING_RESISTED], horizontal=True,
                               format_func=lambda s: f"{STATUS_META[s]['icon']} {meta['free'] if s == SUCCESS else 'Craving resisted'}")
        st.caption("Hours already marked as consumed are left unchanged.")
        if st.button("Apply to these hours", type="primary"):
            lo, hi = sorted([isos.index(first), isos.index(last)])
            chosen = [started[i].start for i in range(lo, hi + 1)
                      if logs_by_start.get(started[i].start, {}).get("status") != CONSUMED]
            if not chosen:
                st.info("Nothing to update in that range.")
            else:
                save(lambda: ts.set_hours_bulk(addiction, chosen, bulk_status), f"{len(chosen)} hours updated.")

# ---------------------------------------------------------------- day summary
completed = [s for s in slots if s.end <= now]
# Every finished, logged hour of the day counts – including sleep hours outside the grid.
finished_logs = [row for row in logs if row["slot_start"] + timedelta(hours=1) <= now]
summary = calc.summarize_hours([row["status"] for row in finished_logs])
window_tracked = sum(1 for s in completed if s.start in logs_by_start)
quantity_today = sum(float(c["quantity"]) for c in day_consumption)
untracked = len(completed) - window_tracked
window_starts = {s.start for s in slots}
outside = sum(1 for row in finished_logs if row["slot_start"] not in window_starts)

section("Day summary", "Only finished hours you've logged are counted."
        + (f" Includes {outside} sleep hour{'s' if outside != 1 else ''} logged outside your tracking hours."
           if outside else ""))
stat_cards([
    {"label": f"{meta['free']} hours", "value": summary["free"], "accent": "green",
     "sub": f"of {summary['tracked']} tracked"},
    {"label": "Cravings resisted", "value": summary["craving_resisted"], "accent": "yellow", "sub": "hours"},
    {"label": f"{meta['units'].capitalize()}", "value": f"{quantity_today:g}", "accent": "red",
     "sub": f"in {summary['consumed']} hour(s)"},
    {"label": "Tracking", "value": f"{calc.percent(window_tracked, len(completed))}%", "accent": "teal",
     "sub": f"{untracked} finished waking hour(s) untracked"},
])

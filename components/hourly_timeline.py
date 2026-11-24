"""Visual hourly timeline, clickable slot grid and the morning sleep card."""

from datetime import datetime, timedelta
from html import escape

import streamlit as st

from services import analytics_service as an
from services import tracking_service as ts
from utils.constants import ADDICTIONS, STATUS_META, SUCCESS, UNTRACKED, UPCOMING
from utils.datetime_utils import Slot, hour_label, local_today, sleep_slots


def slot_status(slot: Slot, logs_by_start: dict, now: datetime) -> str:
    """Stored status if logged; otherwise 'upcoming' for future hours, 'untracked' for past ones."""
    if slot.start in logs_by_start:
        return logs_by_start[slot.start]["status"]
    return UPCOMING if slot.start > now else UNTRACKED


def legend() -> None:
    items = "".join(
        f'<span><i class="{key}"></i>{escape(meta["label"])}</span>' for key, meta in STATUS_META.items()
    )
    st.markdown(f'<div class="rc-legend">{items}</div>', unsafe_allow_html=True)


def timeline_strip(slots: list[Slot], logs_by_start: dict, now: datetime) -> None:
    """A compact coloured bar showing the whole day at a glance."""
    if not slots:
        return
    cells, labels = [], []
    for i, slot in enumerate(slots):
        status = slot_status(slot, logs_by_start, now)
        current = " current" if slot.start <= now < slot.end else ""
        title = f"{slot.range_label}: {STATUS_META[status]['label']}"
        cells.append(f'<div class="rc-cell {status}{current}" title="{escape(title)}"></div>')
        labels.append(f"<span>{escape(slot.label) if i % 3 == 0 else ''}</span>")
    st.markdown(
        f'<div class="rc-timeline">{"".join(cells)}</div>'
        f'<div class="rc-timeline-labels">{"".join(labels)}</div>',
        unsafe_allow_html=True,
    )


def slot_grid(slots: list[Slot], logs_by_start: dict, now: datetime, key_prefix: str,
              selected: datetime | None) -> datetime | None:
    """Wrapping grid of hour buttons coloured by status. Returns the clicked slot start."""
    clicked = None
    with st.container(horizontal=True, gap="small"):
        for i, slot in enumerate(slots):
            status = slot_status(slot, logs_by_start, now)
            sel = "-sel" if selected == slot.start else ""
            label = f"{slot.label} {STATUS_META[status]['icon']}" if status != UPCOMING else slot.label
            if st.button(label, key=f"slot-{status}{sel}-{key_prefix}-{i}", width=96,
                         disabled=status == UPCOMING, help=f"{slot.range_label} · {STATUS_META[status]['label']}"):
                clicked = slot.start
    return clicked


def sleep_card(ctx, addiction: str, key: str) -> None:
    """Morning prompt: log last night's untracked hours as free with one tap.

    Only hours with no status yet are filled, so an hour where consumption was
    recorded overnight keeps its red status.
    """
    if msg := st.session_state.pop("sleep_flash", None):
        st.toast(msg, icon="🌙")
    today = local_today(ctx.tz)
    skip_key = f"sleep-skipped-{addiction}-{today.isoformat()}"
    if st.session_state.get(skip_key):
        return
    try:
        pending = an.sleep_hours_to_log(ctx, addiction)
    except Exception:
        return
    if not pending:
        return

    meta = ADDICTIONS[addiction]
    night = sleep_slots(today, ctx.tz, ctx.wake_hour, ctx.sleep_hour)
    span = f"{night[0].label} – {hour_label(night[-1].local_start + timedelta(hours=1))}"
    with st.container(border=True):
        st.markdown(f"#### 🌙 {meta['free']} while you slept?")
        st.caption(f"Last night, {span}: {len(pending)} hour{'s' if len(pending) != 1 else ''} not logged yet. "
                   f"If you {meta['verb'].lower()} during the night, record it on the Consumption page first – "
                   "that hour keeps its status.")
        c1, c2 = st.columns([2, 1])
        if c1.button(f"✅ Yes – log {len(pending)} sleep hour{'s' if len(pending) != 1 else ''}",
                     key=f"{key}-sleep-log-{addiction}", width="stretch"):
            try:
                saved = ts.set_hours_bulk(addiction, pending, SUCCESS)
            except Exception:
                st.error("Couldn't save your sleep hours. Please try again.")
            else:
                st.session_state.sleep_flash = f"{saved} {meta['free'].lower()} sleep hours logged. Good morning!"
                st.rerun()
        if c2.button("Skip for today", key=f"{key}-sleep-skip-{addiction}", width="stretch"):
            st.session_state[skip_key] = True
            st.rerun()

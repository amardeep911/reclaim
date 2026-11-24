"""Daily Journal – private reflections, one entry per day, with a calendar view."""

from datetime import date, timedelta

import streamlit as st

from components.cards import empty_state, month_calendar, page_header, section
from components.navigation import require_context
from services import journal_service as js
from utils.constants import MOODS, MOOD_EMOJI
from utils.datetime_utils import local_today
from utils.validators import clean_text

ctx = require_context()
today = local_today(ctx.tz)

page_header("Daily Journal", "A few honest lines a day. Patterns become clear when you write them down.",
            eyebrow="Reflect")
st.caption("🔒 Your journal is private to your account. It is never shared with the AI companion unless you "
           "explicitly turn that on later.")
if flash := st.session_state.pop("journal_flash", None):
    st.toast(flash, icon="📝")

QUESTIONS = [
    ("day_summary", "How was your day?", "A sentence or two is plenty."),
    ("difficult_situations", "What situations were difficult?", "When did cravings or stress show up?"),
    ("went_well", "What went well?", "Small wins count."),
    ("lessons", "What did you learn today?", "About yourself, your triggers, what helps."),
    ("tomorrow_focus", "What do you want to improve tomorrow?", "One small, specific thing."),
]

selected: date = st.session_state.get("journal_day", today)
month_first: date = st.session_state.get("journal_month", selected.replace(day=1))

try:
    entries = js.list_entries()
except Exception:
    st.error("Couldn't load your journal. Check your connection and try again.")
    st.stop()
by_date = {date.fromisoformat(e["entry_date"]): e for e in entries}

cal_col, form_col = st.columns([2, 3], gap="large")

# ---------------------------------------------------------------- calendar
with cal_col:
    n1, n2, n3 = st.columns([1, 3, 1], vertical_alignment="center")
    if n1.button("◀", key="cal-prev", width="stretch"):
        month_first = (month_first - timedelta(days=1)).replace(day=1)
    next_month = (month_first + timedelta(days=32)).replace(day=1)
    if n3.button("▶", key="cal-next", width="stretch", disabled=next_month > today):
        month_first = next_month
    st.session_state.journal_month = month_first
    n2.markdown(f"<div style='text-align:center;font-weight:650'>{month_first.strftime('%B %Y')}</div>",
                unsafe_allow_html=True)
    marks = {d: MOOD_EMOJI.get(e.get("mood") or "", "📝") for d, e in by_date.items()}
    month_calendar(month_first.year, month_first.month, marks, today, selected)
    picked = st.date_input("Open a day", value=selected, max_value=today, key=f"journal-pick-{selected}")
    if picked != selected:
        st.session_state.journal_day = picked
        st.session_state.journal_month = picked.replace(day=1)
        st.rerun()
    month_count = sum(1 for d in by_date if d.year == month_first.year and d.month == month_first.month)
    st.caption(f"{month_count} entr{'y' if month_count == 1 else 'ies'} this month · {len(by_date)} in total")

# ---------------------------------------------------------------- entry
with form_col:
    entry = by_date.get(selected)
    st.markdown(f"#### {'Today' if selected == today else selected.strftime('%A, %d %B %Y')}")
    with st.form(f"journal-{selected.isoformat()}"):
        mood = st.segmented_control("Mood", MOODS, default=(entry or {}).get("mood"),
                                    format_func=lambda m: f"{MOOD_EMOJI[m]} {m}")
        answers = {}
        for field, label, placeholder in QUESTIONS:
            answers[field] = st.text_area(label, value=(entry or {}).get(field) or "", max_chars=5000,
                                          placeholder=placeholder, height=90)
        strength = st.slider("How strong were your cravings today?", 0, 10,
                             int((entry or {}).get("craving_strength") or 0),
                             help="0 = none · 10 = overwhelming")
        if st.form_submit_button("Save entry" if not entry else "Update entry", type="primary", width="stretch"):
            fields = {k: clean_text(v, 5000) for k, v in answers.items()}
            fields.update(mood=mood, craving_strength=strength)
            if not js.has_content(fields):
                st.error("Write at least a few words or choose a mood before saving.")
            else:
                try:
                    js.save_entry(selected, fields)
                except Exception:
                    st.error("Couldn't save your entry. Please try again.")
                else:
                    st.session_state.journal_flash = "Journal saved. Thank you for taking the time."
                    st.rerun()

    if entry:
        with st.expander("Delete this entry"):
            confirm = st.checkbox("Yes, permanently delete this entry", key=f"journal-del-confirm-{selected}")
            if st.button("Delete entry", disabled=not confirm, key=f"journal-del-{selected}"):
                try:
                    js.delete_entry(entry["id"])
                except Exception:
                    st.error("Couldn't delete the entry.")
                else:
                    st.session_state.journal_flash = "Entry deleted."
                    st.rerun()

# ---------------------------------------------------------------- history
section("Past entries")
past = [e for e in entries if date.fromisoformat(e["entry_date"]) != selected][:30]
if not past:
    empty_state("📝", "Your journal is just beginning", "Past entries will appear here.")
for e in past:
    d = date.fromisoformat(e["entry_date"])
    mood = f"{MOOD_EMOJI.get(e.get('mood') or '', '')} {e.get('mood') or ''}".strip()
    with st.expander(f"{d.strftime('%a %d %b %Y')}{' · ' + mood if mood else ''}"):
        for field, label, _ in QUESTIONS:
            if e.get(field):
                st.markdown(f"**{label}**")
                st.text(e[field])
        if e.get("craving_strength") is not None:
            st.caption(f"Craving strength: {e['craving_strength']}/10")
        if st.button("Open to edit", key=f"open-{e['id']}"):
            st.session_state.journal_day = d
            st.session_state.journal_month = d.replace(day=1)
            st.rerun()

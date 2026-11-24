"""Money Saved – personalised savings calculator and savings goals."""

from html import escape

import streamlit as st

from components.cards import empty_state, money, page_header, progress_bar, section, stat_cards
from components.navigation import require_context
from services import savings_service as ss
from utils.constants import ADDICTIONS, SAVINGS_ICONS

ctx = require_context()
cur = ctx.currency

page_header("Money Saved", "Every hour without it is money back in your pocket.", eyebrow="Progress")
if flash := st.session_state.pop("savings_flash", None):
    st.toast(flash, icon="💰")

try:
    data = ss.breakdown(ctx)
    goals = ss.get_goals()
except Exception:
    st.error("Couldn't load your savings. Check your connection and try again.")
    st.stop()

total = data["total"]
proj = data["projection"]

# ---------------------------------------------------------------- calculator
stat_cards([
    {"label": "Total saved", "value": money(total, cur), "accent": "green", "sub": "estimated, since you started"},
    {"label": "Average per day", "value": money(proj["daily"], cur), "accent": "teal"},
    {"label": "Per week", "value": money(proj["weekly"], cur)},
    {"label": "Per month", "value": money(proj["monthly"], cur)},
    {"label": "Per year (projected)", "value": money(proj["yearly"], cur), "accent": "teal"},
])

section("Breakdown", "Saved = what your old habit would have cost (your baseline) minus what you've logged.")
cards = []
for a, row in data["by_addiction"].items():
    meta = ADDICTIONS[a]
    cards += [
        {"label": f"{meta['icon']} Saved on {meta['label'].lower()}", "value": money(row["saved"], cur),
         "accent": "green", "sub": f"over {row['days']:.0f} day(s)"},
        {"label": f"{meta['icon']} Spent on {meta['label'].lower()}", "value": money(row["spent"], cur),
         "accent": "red", "sub": "from your logs"},
    ]
stat_cards(cards)
if data["potential_daily"]:
    p = data["potential_daily"]
    st.info(f"**If you stopped completely**, you'd save about **{money(p, cur)} a day** – "
            f"{money(p * 30, cur)} a month or **{money(p * 365, cur)} a year**.", icon="✨")
st.caption("All figures are estimates based on the baselines in Settings → Recovery plan and what you've logged.")

# ---------------------------------------------------------------- goals
section("Savings goals", "Goals fill up in order. When you mark a goal as bought, its cost comes out of your savings.")
with_progress = ss.goals_with_progress(goals, total)
completed = [g for g in goals if g.get("is_completed")]

if not with_progress and not completed:
    empty_state("🎯", "No goals yet", "Give your savings a purpose – a new phone, a trip, a safety net.")

for g in with_progress:
    with st.container(border=True):
        target = float(g["target_amount"])
        st.markdown(
            f'<div class="rc-goal"><div class="rc-goal-icon">{escape(g["icon"])}</div><div class="rc-goal-body">'
            f'<strong>{escape(g["title"])}</strong></div></div>', unsafe_allow_html=True)
        progress_bar(g["pct"], f"{money(g['allocated'], cur)} of {money(target, cur)}",
                     "Reached! 🎉" if g["pct"] >= 100 else f"{g['pct']}%")
        if g["pct"] < 100 and proj["daily"] > 0:
            days_left = (target - g["allocated"]) / proj["daily"]
            st.caption(f"At your current pace: about {days_left:.0f} more day(s).")
        with st.expander("Edit"):
            with st.form(f"goal-{g['id']}"):
                e1, e2, e3 = st.columns([1, 3, 2])
                icon = e1.selectbox("Icon", SAVINGS_ICONS, index=SAVINGS_ICONS.index(g["icon"])
                                    if g["icon"] in SAVINGS_ICONS else 0)
                title = e2.text_input("Goal", value=g["title"], max_chars=100)
                amount = e3.number_input(f"Target ({cur})", min_value=1.0, value=target, step=100.0)
                b1, b2, b3 = st.columns(3)
                save = b1.form_submit_button("Save", type="primary", width="stretch")
                done = b2.form_submit_button("Mark as bought ✓", width="stretch")
                delete = b3.form_submit_button("Delete", width="stretch")
            if save or done or delete:
                try:
                    if delete:
                        ss.delete_goal(g["id"])
                        msg = "Goal deleted."
                    elif not title.strip():
                        st.error("Give your goal a name.")
                        st.stop()
                    else:
                        ss.update_goal(g["id"], {"title": title.strip(), "target_amount": amount, "icon": icon,
                                                 "is_completed": bool(done)})
                        msg = "Enjoy it – you earned it! 🎉" if done else "Goal updated."
                except Exception:
                    st.error("Couldn't update that goal.")
                else:
                    st.session_state.savings_flash = msg
                    st.rerun()

with st.form("new-goal", clear_on_submit=True):
    st.markdown("**➕ Add a goal**")
    n1, n2, n3 = st.columns([1, 3, 2])
    icon = n1.selectbox("Icon", SAVINGS_ICONS)
    title = n2.text_input("What are you saving for?", max_chars=100, placeholder="e.g. New running shoes")
    amount = n3.number_input(f"Target ({cur})", min_value=1.0, value=5000.0, step=500.0)
    if st.form_submit_button("Add goal", type="primary"):
        if not title.strip():
            st.error("Give your goal a name.")
        else:
            try:
                ss.add_goal(title.strip(), amount, icon)
            except Exception:
                st.error("Couldn't add that goal.")
            else:
                st.session_state.savings_flash = "Goal added."
                st.rerun()

if completed:
    section("Completed goals")
    for g in completed:
        c1, c2 = st.columns([5, 1], vertical_alignment="center")
        c1.markdown(f"{g['icon']} **{g['title']}** · {money(float(g['target_amount']), cur)} ✓")
        if c2.button("Reopen", key=f"reopen-{g['id']}", width="stretch"):
            ss.update_goal(g["id"], {"is_completed": False})
            st.rerun()

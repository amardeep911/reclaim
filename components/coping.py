"""The craving toolkit: breathing, relaxation, walking, distractions, reasons, support."""

import random
from html import escape

import streamlit as st

from components.cards import quote_card
from services.database_service import UserContext
from utils.constants import (
    ALCOHOL, DISTRACTIONS, EMERGENCY_NOTE, ENCOURAGEMENTS, RELAXATION_STEPS, WALK_STEPS,
)


def steps(items: list[str]) -> None:
    st.markdown(f'<ol class="rc-steps">{"".join(f"<li>{escape(i)}</li>" for i in items)}</ol>',
                unsafe_allow_html=True)


def breathing_exercise() -> None:
    """Box breathing: in 4 · hold 4 · out 4 · hold 4, for about five minutes (pure CSS animation)."""
    st.markdown(
        '<div class="rc-breath"><div class="rc-breath-stage"><div class="rc-breath-circle"></div>'
        '<div class="rc-breath-label l1">Breathe in</div><div class="rc-breath-label l2">Hold</div>'
        '<div class="rc-breath-label l3">Breathe out</div><div class="rc-breath-label l4">Hold</div></div>'
        '<div class="rc-breath-done">Five minutes done. Notice how you feel now. 🌿</div></div>',
        unsafe_allow_html=True,
    )
    st.caption("Follow the circle: in for 4 · hold for 4 · out for 4 · hold for 4. It runs for about five minutes.")


def withdrawal_warning(dependence_risk: bool) -> None:
    """Shown for alcohol cravings: self-help is not treatment for withdrawal."""
    text = ("**If you have shaking, sweating, nausea, a racing heart, anxiety or can't sleep after cutting down, "
            "this may be alcohol withdrawal.** Breathing exercises and distractions are not a treatment for "
            "withdrawal. Please contact a doctor or health service today.\n\n" + EMERGENCY_NOTE)
    (st.error if dependence_risk else st.warning)(text, icon="🩺")


def toolkit(ctx: UserContext, addiction: str, key: str) -> None:
    if addiction == ALCOHOL:
        withdrawal_warning(bool(ctx.addiction_profiles.get(ALCOHOL, {}).get("dependence_risk")))

    st.info(random.choice(ENCOURAGEMENTS), icon="💚")
    tabs = st.tabs(["🫁 Breathe", "🧘 Relax", "🚶 Walk", "🎲 Distract", "💬 Your reasons", "🤝 Get support"])

    with tabs[0]:
        if st.button("Start 5-minute breathing", key=f"{key}-breathe", type="primary"):
            st.session_state[f"{key}-breathing"] = True
        if st.session_state.get(f"{key}-breathing"):
            breathing_exercise()
    with tabs[1]:
        st.markdown("**Progressive muscle relaxation** (about 5 minutes)")
        steps(RELAXATION_STEPS)
    with tabs[2]:
        st.markdown("**A short walk** changes your surroundings and gives the craving time to pass.")
        steps(WALK_STEPS)
    with tabs[3]:
        seed = st.session_state.get(f"{key}-seed", 0)
        for idea in random.Random(seed).sample(DISTRACTIONS, 3):
            st.markdown(f"- {idea}")
        if st.button("Show me other ideas", key=f"{key}-shuffle"):
            st.session_state[f"{key}-seed"] = seed + 1
            st.rerun()
    with tabs[4]:
        reasons = [(label, ctx.profile.get(f)) for label, f in
                   [("Why I'm doing this", "why_quit"), ("What I want to achieve", "aspirations"),
                    ("What keeps me going", "motivators")] if ctx.profile.get(f)]
        if reasons:
            for label, text in reasons:
                quote_card(label, text)
        else:
            st.caption("Add your reasons in Settings → Profile and they'll show up here.")
    with tabs[5]:
        name, phone = ctx.profile.get("trusted_contact_name"), ctx.profile.get("trusted_contact_phone")
        if phone:
            digits = "".join(ch for ch in phone if ch.isdigit() or ch == "+")
            c1, c2 = st.columns(2)
            c1.link_button(f"📞 Call {name or 'my trusted contact'}", f"tel:{digits}", width="stretch")
            c2.link_button("💬 Send a message", f"sms:{digits}", width="stretch")
        else:
            st.caption("Add a trusted contact in Settings → Profile for a one-tap call or message.")
        st.markdown("Talking to a professional really helps. Free, confidential support lines are listed on "
                    "the Health & Safety page.")
        st.page_link("pages/9_Resources.py", label="Support lines & safety information", icon=":material/support:")

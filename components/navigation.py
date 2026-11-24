"""App shell: global CSS, logo, sidebar, and shared page guards."""

from pathlib import Path

import streamlit as st

from services import auth_service
from services.database_service import UserContext, load_context
from utils.constants import ADDICTIONS, TAGLINE

ASSETS = Path(__file__).resolve().parent.parent / "assets"


def load_css() -> None:
    css = (ASSETS / "styles.css").read_text(encoding="utf-8")
    st.markdown(f"<style>{css}</style>", unsafe_allow_html=True)


def render_logo() -> None:
    st.logo(str(ASSETS / "logo.svg"), size="large", icon_image=str(ASSETS / "icon.svg"))


def render_sidebar(ctx: UserContext) -> None:
    with st.sidebar:
        st.markdown(f'<div class="rc-tagline">{TAGLINE}</div>', unsafe_allow_html=True)
        st.divider()
        st.caption(f"Signed in as **{ctx.name}**")
        tracking = " · ".join(f"{ADDICTIONS[a]['icon']} {ADDICTIONS[a]['label']}" for a in ctx.addictions)
        if tracking:
            st.caption(f"Tracking: {tracking}")
        if st.button("Log out", icon=":material/logout:", width="stretch"):
            auth_service.sign_out()
            st.rerun()


def require_context() -> UserContext:
    """Used at the top of every protected page."""
    if not st.session_state.get("user_id"):
        st.stop()
    return load_context()


def addiction_picker(ctx: UserContext, key: str) -> str:
    """Segmented switch between smoking/alcohol (hidden when only one is tracked)."""
    if len(ctx.addictions) == 1:
        return ctx.addictions[0]
    remembered = st.session_state.get("active_addiction")
    default = remembered if remembered in ctx.addictions else ctx.addictions[0]
    choice = st.segmented_control(
        "Tracking", ctx.addictions, default=default, key=key, label_visibility="collapsed",
        format_func=lambda a: f"{ADDICTIONS[a]['icon']} {ADDICTIONS[a]['label']}",
    ) or default
    st.session_state.active_addiction = choice
    return choice


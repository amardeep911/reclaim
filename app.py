"""Reclaim – entry point.  Run with:  streamlit run app.py

Routing:
  not signed in        -> Welcome (login / register / reset password)
  signed in, new user  -> Onboarding wizard
  signed in, onboarded -> full app
"""

import logging

import streamlit as st

st.set_page_config(page_title="Reclaim", page_icon="assets/icon.svg", layout="wide")

import config  # noqa: E402  (set_page_config must run first)
from components.navigation import load_css, render_logo, render_sidebar  # noqa: E402
from services import auth_service  # noqa: E402
from services.database_service import load_context  # noqa: E402

load_css()
render_logo()

if not config.supabase_configured():
    st.title("Reclaim isn't connected to Supabase yet")
    st.write("Add `SUPABASE_URL` and `SUPABASE_ANON_KEY` to a `.env` file (local) or to "
             "`.streamlit/secrets.toml` / the Streamlit Cloud secrets panel, then reload. "
             "See README.md → *Supabase setup*.")
    st.stop()

user = auth_service.current_user()

if user is None:
    page = st.navigation([st.Page("pages/auth.py", title="Welcome", icon=":material/spa:")], position="hidden")
else:
    try:
        ctx = load_context()
    except Exception as exc:
        code = getattr(exc, "code", None)
        logging.getLogger("reclaim").error("Profile load failed: %s %s", type(exc).__name__, code)
        if code == "PGRST205":  # table not found
            st.error("The Reclaim tables don't exist in this Supabase project yet. Open the Supabase "
                     "SQL Editor, run `database/schema.sql` and then `database/rls_policies.sql`, then reload.")
        else:
            st.error("We couldn't load your profile. Check your connection and that the database "
                     f"schema has been installed (database/schema.sql), then reload the page. (code: {code or type(exc).__name__})")
        if st.button("Log out"):
            auth_service.sign_out()
            st.rerun()
        st.stop()

    if not ctx.onboarded:
        page = st.navigation([st.Page("pages/onboarding.py", title="Get started", icon=":material/spa:")],
                             position="hidden")
    else:
        page = st.navigation({
            "Today": [
                st.Page("pages/1_Dashboard.py", title="Dashboard", icon=":material/space_dashboard:", default=True),
                st.Page("pages/2_Hourly_Tracker.py", title="Hourly Tracker", icon=":material/schedule:"),
                st.Page("pages/3_Consumption_Tracker.py", title="Consumption", icon=":material/edit_note:"),
                st.Page("pages/4_Craving_Manager.py", title="Craving Manager", icon=":material/waves:"),
            ],
            "Progress": [
                st.Page("pages/6_Achievements.py", title="Achievements", icon=":material/emoji_events:"),
                st.Page("pages/11_Savings.py", title="Money Saved", icon=":material/savings:"),
                st.Page("pages/8_Journal.py", title="Journal", icon=":material/menu_book:"),
            ],
            "Support": [
                st.Page("pages/9_Resources.py", title="Health & Safety", icon=":material/health_and_safety:"),
            ],
            "You": [
                st.Page("pages/10_Settings.py", title="Settings & Profile", icon=":material/settings:"),
            ],
        })
        render_sidebar(ctx)

page.run()

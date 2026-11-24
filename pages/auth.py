"""Welcome page: log in, create an account, or reset a forgotten password."""

import streamlit as st

from components.cards import page_header
from services import auth_service
from utils.constants import TAGLINE
from utils.validators import validate_email, validate_password

_, center, _ = st.columns([1, 2.2, 1])

with center:
    page_header("Welcome to Reclaim", TAGLINE, eyebrow="Your recovery companion")

    if msg := st.session_state.pop("auth_flash", None):
        st.success(msg)

    login_tab, signup_tab, reset_tab = st.tabs(["Log in", "Create account", "Forgot password"])

    with login_tab:
        with st.form("login"):
            email = st.text_input("Email", autocomplete="email")
            password = st.text_input("Password", type="password", autocomplete="current-password")
            if st.form_submit_button("Log in", type="primary", width="stretch"):
                if error := validate_email(email) or (None if password else "Please enter your password."):
                    st.error(error)
                else:
                    with st.spinner("Signing you in…"):
                        ok, message = auth_service.sign_in(email, password)
                    if ok:
                        st.rerun()
                    st.error(message)

    with signup_tab:
        with st.form("signup"):
            email = st.text_input("Email", key="su_email", autocomplete="email")
            password = st.text_input("Password", type="password", key="su_pw", autocomplete="new-password",
                                     help="At least 8 characters, with a letter and a number.")
            confirm = st.text_input("Confirm password", type="password", key="su_pw2", autocomplete="new-password")
            if st.form_submit_button("Create account", type="primary", width="stretch"):
                error = validate_email(email) or validate_password(password)
                if not error and password != confirm:
                    error = "Passwords don't match."
                if error:
                    st.error(error)
                else:
                    with st.spinner("Creating your account…"):
                        ok, message = auth_service.sign_up(email, password)
                    if ok and st.session_state.get("user_id"):
                        st.rerun()
                    (st.success if ok else st.error)(message)

    with reset_tab:
        st.caption("We'll email you a 6-digit code. Enter it below with your new password.")
        with st.form("reset_request"):
            email = st.text_input("Email", key="rs_email", autocomplete="email")
            if st.form_submit_button("Send reset code", width="stretch"):
                if error := validate_email(email):
                    st.error(error)
                else:
                    ok, message = auth_service.send_password_reset(email)
                    if ok:
                        st.session_state.reset_email = email.strip()
                    (st.success if ok else st.error)(message)

        with st.form("reset_confirm"):
            email = st.text_input("Email", value=st.session_state.get("reset_email", ""), key="rs_email2")
            code = st.text_input("6-digit code from the email", max_chars=10, key="rs_code")
            new_pw = st.text_input("New password", type="password", key="rs_pw", autocomplete="new-password")
            if st.form_submit_button("Set new password", type="primary", width="stretch"):
                error = validate_email(email) or validate_password(new_pw)
                if not error and not code.strip().isdigit():
                    error = "Enter the numeric code from the email."
                if error:
                    st.error(error)
                else:
                    ok, message = auth_service.reset_password_with_code(email, code, new_pw)
                    if ok:
                        st.rerun()
                    st.error(message)

    st.caption("🔒 Your recovery data is stored in a Supabase (PostgreSQL) database with row-level security, "
               "so only your account can read it. Never share your password.")

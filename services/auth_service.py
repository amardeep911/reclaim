"""Supabase Auth: sign up, sign in, sign out, password reset, account deletion.

Each browser session gets its OWN Supabase client stored in st.session_state.
Never cache the client with st.cache_resource – that would share one user's
login with every visitor of the app.
"""

import logging

import streamlit as st
from supabase import Client, ClientOptions, create_client

import config

log = logging.getLogger(__name__)

_FRIENDLY = {
    "invalid login credentials": "That email and password don't match. Please try again.",
    "email not confirmed": "Please confirm your email first – check your inbox for the link.",
    "user already registered": "An account with this email already exists. Try logging in.",
    "token has expired or is invalid": "That code is invalid or has expired. Request a new one.",
    "rate limit": "Too many attempts. Please wait a minute and try again.",
    "should be different from the old password": "Your new password must differ from the old one.",
}


def friendly_error(exc: Exception) -> str:
    message = str(getattr(exc, "message", exc)).lower()
    for needle, text in _FRIENDLY.items():
        if needle in message:
            return text
    # Log the type only – never credentials or user content.
    log.warning("Auth error: %s", type(exc).__name__)
    return "Something went wrong. Please try again in a moment."


def get_client() -> Client:
    if "sb" not in st.session_state:
        st.session_state.sb = create_client(
            config.SUPABASE_URL,
            config.SUPABASE_ANON_KEY,
            # Tokens are refreshed on demand in current_user(); no background threads.
            ClientOptions(auto_refresh_token=False),
        )
    return st.session_state.sb


def _remember(session) -> None:
    st.session_state.user_id = session.user.id
    st.session_state.user_email = session.user.email


def _forget() -> None:
    for key in list(st.session_state.keys()):
        del st.session_state[key]


def current_user():
    """The signed-in user, or None. Refreshes the access token when it is about to expire."""
    if not st.session_state.get("user_id"):
        return None
    try:
        session = get_client().auth.get_session()
    except Exception:
        session = None
    if session is None:
        _forget()
        return None
    return session.user


def sign_up(email: str, password: str) -> tuple[bool, str]:
    try:
        res = get_client().auth.sign_up({"email": email.strip(), "password": password})
    except Exception as exc:
        return False, friendly_error(exc)
    if res.user is not None and res.user.identities == []:
        # Supabase hides whether an email exists; an empty identity list means it does.
        return False, _FRIENDLY["user already registered"]
    if res.session:
        _remember(res.session)
        return True, "Welcome to Reclaim!"
    return True, "Almost there – check your email and click the confirmation link, then log in."


def sign_in(email: str, password: str) -> tuple[bool, str]:
    try:
        res = get_client().auth.sign_in_with_password({"email": email.strip(), "password": password})
    except Exception as exc:
        return False, friendly_error(exc)
    _remember(res.session)
    return True, "Welcome back."


def sign_out() -> None:
    try:
        get_client().auth.sign_out()
    except Exception:
        pass
    _forget()


def send_password_reset(email: str) -> tuple[bool, str]:
    try:
        get_client().auth.reset_password_for_email(email.strip())
    except Exception as exc:
        return False, friendly_error(exc)
    return True, "If an account exists for that email, a 6-digit reset code is on its way."


def reset_password_with_code(email: str, code: str, new_password: str) -> tuple[bool, str]:
    try:
        res = get_client().auth.verify_otp({"email": email.strip(), "token": code.strip(), "type": "recovery"})
        _remember(res.session)
        get_client().auth.update_user({"password": new_password})
    except Exception as exc:
        return False, friendly_error(exc)
    return True, "Password updated. You're signed in."


def update_password(new_password: str) -> tuple[bool, str]:
    try:
        get_client().auth.update_user({"password": new_password})
    except Exception as exc:
        return False, friendly_error(exc)
    return True, "Password updated."


def update_email(new_email: str) -> tuple[bool, str]:
    try:
        get_client().auth.update_user({"email": new_email.strip()})
    except Exception as exc:
        return False, friendly_error(exc)
    return True, "Check both your old and new inbox to confirm the change."


def delete_account() -> tuple[bool, str]:
    """Calls the delete_my_account() SQL function – it can only delete the caller."""
    try:
        get_client().rpc("delete_my_account").execute()
    except Exception as exc:
        return False, friendly_error(exc)
    _forget()
    return True, "Your account and all of your data have been deleted."

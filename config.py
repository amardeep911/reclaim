"""Application configuration.

Settings are read from Streamlit secrets first (used on Streamlit Community
Cloud, file: .streamlit/secrets.toml) and then from environment variables /
a local .env file (handy for local development).

Only the Supabase *anon* (public) key belongs here. The service-role key must
never be given to this app: Row Level Security + the user's own access token
are what protect the data.
"""

import os

import streamlit as st
from dotenv import load_dotenv

load_dotenv()


def get_setting(name: str, default: str = "") -> str:
    try:
        if name in st.secrets:
            return str(st.secrets[name])
    except Exception:
        # No secrets.toml present – fall back to environment variables.
        pass
    return os.getenv(name, default)


SUPABASE_URL = get_setting("SUPABASE_URL")
SUPABASE_ANON_KEY = get_setting("SUPABASE_ANON_KEY")
OPENAI_API_KEY = get_setting("OPENAI_API_KEY")
OPENAI_MODEL = get_setting("OPENAI_MODEL", "gpt-4o-mini")
APP_ENV = get_setting("APP_ENV", "production")  # "development" enables demo tools later


def supabase_configured() -> bool:
    return bool(SUPABASE_URL and SUPABASE_ANON_KEY)


def ai_enabled() -> bool:
    return bool(OPENAI_API_KEY)

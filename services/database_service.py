"""Profile, settings and generic data access.

All queries run with the signed-in user's access token, so Row Level Security
in Supabase guarantees they only ever touch that user's rows. We still filter
by user_id explicitly – it keeps queries fast and intent obvious.
"""

from dataclasses import dataclass, field
from datetime import date, datetime

import streamlit as st

from services.auth_service import get_client
from utils.constants import ALCOHOL, SMOKING, STANDARD_DRINK_GRAMS
from utils.datetime_utils import UTC, get_tz

PAGE_SIZE = 1000  # Supabase returns at most 1000 rows per request by default

EXPORT_TABLES = [
    "profiles", "addiction_profiles", "recovery_goals", "hourly_logs", "consumption_logs",
    "craving_logs", "daily_logs", "journal_entries", "user_achievements", "savings_goals",
    "notification_preferences", "ai_conversations", "ai_messages",
]


def db():
    return get_client()


def uid() -> str:
    return st.session_state["user_id"]


def iso(instant: datetime) -> str:
    """UTC ISO string with a Z suffix – safe to use inside query-string filters."""
    return instant.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def select_all(table: str, apply_filters, columns: str = "*") -> list[dict]:
    """Fetch every matching row, paging past the 1000-row API limit."""
    rows, offset = [], 0
    while True:
        query = apply_filters(db().table(table).select(columns))
        batch = query.range(offset, offset + PAGE_SIZE - 1).execute().data
        rows.extend(batch)
        if len(batch) < PAGE_SIZE:
            return rows
        offset += PAGE_SIZE


# ---------------------------------------------------------------------------
# User context – loaded once per script run and cached in session_state
# ---------------------------------------------------------------------------

@dataclass
class UserContext:
    profile: dict
    addiction_profiles: dict = field(default_factory=dict)  # {"smoking": row, "alcohol": row}
    goals: dict = field(default_factory=dict)               # {"smoking": row, ...}

    @property
    def tz(self):
        return get_tz(self.profile.get("timezone"))

    @property
    def name(self) -> str:
        return self.profile.get("display_name") or "friend"

    @property
    def onboarded(self) -> bool:
        return bool(self.profile.get("onboarding_completed_at"))

    @property
    def addictions(self) -> list[str]:
        return [a for a in (SMOKING, ALCOHOL)
                if a in self.addiction_profiles and self.addiction_profiles[a].get("is_active")]

    @property
    def currency(self) -> str:
        return self.profile.get("currency_symbol") or "₹"

    @property
    def grams_per_drink(self) -> float:
        return STANDARD_DRINK_GRAMS.get(self.profile.get("standard_drink_region") or "WHO",
                                        STANDARD_DRINK_GRAMS["WHO"])[0]

    @property
    def wake_hour(self) -> int:
        return int(self.profile.get("wake_hour", 7))

    @property
    def sleep_hour(self) -> int:
        return int(self.profile.get("sleep_hour", 23))


def load_context(force: bool = False) -> UserContext:
    if force or "ctx" not in st.session_state:
        st.session_state.ctx = UserContext(
            profile=get_or_create_profile(),
            addiction_profiles=get_addiction_profiles(),
            goals=get_active_goals(),
        )
    return st.session_state.ctx


def invalidate_context() -> None:
    st.session_state.pop("ctx", None)


# ---------------------------------------------------------------------------
# Profiles
# ---------------------------------------------------------------------------

def get_or_create_profile() -> dict:
    rows = db().table("profiles").select("*").eq("id", uid()).execute().data
    if rows:
        return rows[0]
    # Normally created by the on_auth_user_created trigger; this is a fallback.
    return db().table("profiles").insert({"id": uid()}).execute().data[0]


def update_profile(fields: dict) -> None:
    db().table("profiles").update(fields).eq("id", uid()).execute()
    invalidate_context()


def get_addiction_profiles() -> dict:
    rows = db().table("addiction_profiles").select("*").eq("user_id", uid()).execute().data
    return {row["addiction_type"]: row for row in rows}


def upsert_addiction_profile(addiction_type: str, fields: dict) -> None:
    payload = {**fields, "user_id": uid(), "addiction_type": addiction_type}
    db().table("addiction_profiles").upsert(payload, on_conflict="user_id,addiction_type").execute()
    invalidate_context()


def set_addiction_active(addiction_type: str, active: bool) -> None:
    (db().table("addiction_profiles").update({"is_active": active})
     .eq("user_id", uid()).eq("addiction_type", addiction_type).execute())
    invalidate_context()


# ---------------------------------------------------------------------------
# Recovery goals – one active goal per addiction type
# ---------------------------------------------------------------------------

def get_active_goals() -> dict:
    rows = (db().table("recovery_goals").select("*").eq("user_id", uid())
            .eq("is_active", True).order("created_at").execute().data)
    return {row["addiction_type"]: row for row in rows if row.get("addiction_type")}


def set_goal(addiction_type: str, goal_type: str, title: str,
             target_per_day: float | None = None, target_date: date | None = None) -> None:
    """Replace the active goal (old goals are kept as inactive history)."""
    (db().table("recovery_goals").update({"is_active": False})
     .eq("user_id", uid()).eq("addiction_type", addiction_type).eq("is_active", True).execute())
    db().table("recovery_goals").insert({
        "user_id": uid(),
        "addiction_type": addiction_type,
        "goal_type": goal_type,
        "title": title,
        "target_per_day": target_per_day,
        "target_date": target_date.isoformat() if target_date else None,
    }).execute()
    invalidate_context()


# ---------------------------------------------------------------------------
# Daily check-ins
# ---------------------------------------------------------------------------

def get_daily_log(day: date) -> dict | None:
    rows = (db().table("daily_logs").select("*").eq("user_id", uid())
            .eq("log_date", day.isoformat()).execute().data)
    return rows[0] if rows else None


def upsert_daily_log(day: date, fields: dict) -> None:
    payload = {**fields, "user_id": uid(), "log_date": day.isoformat()}
    db().table("daily_logs").upsert(payload, on_conflict="user_id,log_date").execute()


# ---------------------------------------------------------------------------
# Notification preferences
# ---------------------------------------------------------------------------

def get_notification_prefs() -> dict:
    rows = db().table("notification_preferences").select("*").eq("user_id", uid()).execute().data
    if rows:
        return rows[0]
    return db().table("notification_preferences").insert({"user_id": uid()}).execute().data[0]


def update_notification_prefs(fields: dict) -> None:
    payload = {**fields, "user_id": uid()}
    db().table("notification_preferences").upsert(payload, on_conflict="user_id").execute()


# ---------------------------------------------------------------------------
# Privacy: export
# ---------------------------------------------------------------------------

def export_all_data() -> dict:
    data = {}
    for table in EXPORT_TABLES:
        key = "id" if table == "profiles" else "user_id"
        data[table] = select_all(table, lambda q, k=key: q.eq(k, uid()))
    return data


def delete_all_journal_entries() -> None:
    db().table("journal_entries").delete().eq("user_id", uid()).execute()


# Everything a reset clears – children before parents. profiles and
# notification_preferences are kept so name, timezone and settings survive.
RESET_TABLES = [
    "ai_messages", "ai_conversations", "hourly_logs", "consumption_logs", "craving_logs", "daily_logs",
    "journal_entries", "user_achievements", "savings_goals", "recovery_goals", "addiction_profiles",
]


def reset_my_data() -> None:
    """Delete all of the signed-in user's recovery data and restart onboarding.

    Each delete is filtered by user_id AND protected by RLS, so it can only ever touch the caller's rows.
    Safe to retry: if it stops halfway, running it again finishes the job.
    """
    for table in RESET_TABLES:
        db().table(table).delete().eq("user_id", uid()).execute()
    db().table("profiles").update({"onboarding_completed_at": None}).eq("id", uid()).execute()


def clear_session_cache() -> None:
    """Forget everything cached for this browser session except the login itself."""
    keep = {"sb", "user_id", "user_email"}
    for key in list(st.session_state.keys()):
        if key not in keep:
            del st.session_state[key]

"""End-to-end page tests: real pages + real services, with an in-memory Supabase fake.

These drive the actual Streamlit scripts (onboarding -> dashboard -> hourly
tracker -> consumption -> settings) and assert on what reaches the database.
"""

import os
from datetime import datetime, timezone
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from tests.fake_supabase import FakeSupabase
from utils.datetime_utils import timezone_choices

os.environ.setdefault("SUPABASE_URL", "https://example.supabase.co")
os.environ.setdefault("SUPABASE_ANON_KEY", "test-anon-key")

APP = str(Path(__file__).resolve().parent.parent / "app.py")

PAGES = ["pages/1_Dashboard.py", "pages/2_Hourly_Tracker.py", "pages/3_Consumption_Tracker.py",
         "pages/4_Craving_Manager.py", "pages/6_Achievements.py", "pages/8_Journal.py", "pages/11_Savings.py",
         "pages/9_Resources.py", "pages/10_Settings.py"]


def midday_timezone() -> str:
    """A real timezone where it is currently between 11:00 and 20:00, so 'finished hours' exist today."""
    now = datetime.now(timezone.utc)
    from zoneinfo import ZoneInfo
    for name in timezone_choices():
        if 11 <= now.astimezone(ZoneInfo(name)).hour < 20:
            return name
    raise RuntimeError("no suitable timezone")


def new_app(fake: FakeSupabase) -> AppTest:
    at = AppTest.from_file(APP, default_timeout=30)
    at.session_state["sb"] = fake
    at.session_state["user_id"] = fake.user_id
    at.session_state["user_email"] = "test@example.com"
    return at


def click(at: AppTest, label: str | None = None, key: str | None = None) -> AppTest:
    if key:
        at.button(key=key).click()
    else:
        matches = [b for b in at.button if b.label == label]
        assert matches, f"button {label!r} not found; have {[b.label for b in at.button]}"
        matches[0].click()
    return at.run()


def assert_clean(at: AppTest) -> None:
    assert not at.exception, [e.value for e in at.exception]
    errors = [e.value for e in at.error if e.icon != "🚑"]  # the emergency notice is intentional
    assert not errors, errors


def onboard(fake: FakeSupabase, kind: str = "smoking") -> AppTest:
    at = new_app(fake).run()
    assert_clean(at)
    at.text_input[0].input("Sam")
    at.selectbox[0].set_value(midday_timezone())
    at.radio[0].set_value(kind)
    at = click(at, "Continue →")
    assert_clean(at)
    if kind in ("smoking", "both"):
        at = click(at, "Continue →")  # smoking defaults: 10/day at 18 each
        assert_clean(at)
    if kind in ("alcohol", "both"):
        at = click(at, "Continue →")
        assert_clean(at)
    at.text_area[0].input("Breathe easier and save money.")
    at = click(at, "Finish setup ✓")
    assert_clean(at)
    return at


def test_signed_out_shows_welcome():
    at = AppTest.from_file(APP, default_timeout=30).run()
    assert_clean(at)
    assert [t.label for t in at.tabs] == ["Log in", "Create account", "Forgot password"]


def test_onboarding_saves_profile_plan_and_goal():
    fake = FakeSupabase()
    at = onboard(fake, "both")
    profile = fake.store["profiles"][0]
    assert profile["display_name"] == "Sam"
    assert profile["onboarding_completed_at"]
    assert profile["addiction_type"] == "both"
    types = {r["addiction_type"] for r in fake.store["addiction_profiles"]}
    assert types == {"smoking", "alcohol"}
    assert {g["addiction_type"] for g in fake.store["recovery_goals"]} == {"smoking", "alcohol"}
    # After onboarding the dashboard renders
    assert any("Sam" in m.value for m in at.markdown)


def test_onboarding_requires_a_reason():
    fake = FakeSupabase()
    at = new_app(fake).run()
    at.text_input[0].input("Sam")
    at = click(at, "Continue →")
    at = click(at, "Continue →")
    at = click(at, "Finish setup ✓")
    assert any("reason" in e.value for e in at.error)
    assert not fake.store["profiles"][0]["onboarding_completed_at"]


@pytest.mark.parametrize("kind", ["smoking", "alcohol", "both"])
def test_every_page_renders(kind):
    fake = FakeSupabase()
    at = onboard(fake, kind)
    for page in PAGES:
        at.switch_page(page).run()
        assert_clean(at)


def test_quick_log_hour_and_consumption():
    fake = FakeSupabase()
    at = onboard(fake, "smoking")
    at.switch_page("pages/2_Hourly_Tracker.py").run()
    assert_clean(at)

    at = click(at, key="quick-success")
    assert_clean(at)
    logs = fake.store["hourly_logs"]
    assert len(logs) == 1 and logs[0]["status"] == "success"

    at = click(at, key="quick-consumed")
    assert_clean(at)
    assert len(fake.store["consumption_logs"]) == 1
    assert sorted(r["status"] for r in fake.store["hourly_logs"]) == ["consumed", "success"]

    at = click(at, key="quick-craving")
    assert_clean(at)
    assert sorted(r["status"] for r in fake.store["hourly_logs"]) == ["consumed", "craving_resisted", "success"]
    # The same hour is never stored twice
    assert len({(r["addiction_type"], r["slot_start"]) for r in fake.store["hourly_logs"]}) == 3


def test_bulk_marking_skips_consumed_hours():
    fake = FakeSupabase()
    at = onboard(fake, "smoking")
    at.switch_page("pages/2_Hourly_Tracker.py").run()
    at = click(at, key="quick-consumed")
    at = click(at, "Apply to these hours")
    assert_clean(at)
    statuses = [r["status"] for r in fake.store["hourly_logs"]]
    assert statuses.count("consumed") == 1
    assert statuses.count("success") >= 1


def test_log_consumption_from_form_and_delete_reverts_hour():
    fake = FakeSupabase()
    at = onboard(fake, "smoking")
    at.switch_page("pages/3_Consumption_Tracker.py").run()
    assert_clean(at)
    at.number_input(key="new-smoking-qty").set_value(3)
    at.selectbox(key="new-smoking-trigger").set_value("Stress")
    at = click(at, "Save entry")
    assert_clean(at)
    rows = fake.store["consumption_logs"]
    assert len(rows) == 1 and rows[0]["quantity"] == 3 and rows[0]["trigger"] == "Stress"
    assert rows[0]["cost"] == 54  # 3 * 18
    assert [r["status"] for r in fake.store["hourly_logs"]] == ["consumed"]

    # Delete through the history tab – the hour should revert to "not tracked"
    at.selectbox[-1].set_value(rows[0]["id"])
    at.run()
    at.checkbox(key=f"confirm-del-{rows[0]['id']}").check().run()
    at = click(at, key=f"del-entry-{rows[0]['id']}")
    assert_clean(at)
    assert fake.store["consumption_logs"] == []
    assert fake.store["hourly_logs"] == []  # back to "not tracked"


def test_settings_profile_update():
    fake = FakeSupabase()
    at = onboard(fake, "smoking")
    at.switch_page("pages/10_Settings.py").run()
    assert_clean(at)
    at.text_input[0].input("Samira")
    at = click(at, "Save profile")
    assert_clean(at)
    assert fake.store["profiles"][0]["display_name"] == "Samira"


def test_delete_account_calls_rpc_and_signs_out():
    fake = FakeSupabase()
    at = onboard(fake, "smoking")
    at.switch_page("pages/10_Settings.py").run()
    at.text_input(key="delete_confirm").input("DELETE").run()
    at = click(at, "Delete my account permanently")
    assert fake.rpc_calls == ["delete_my_account"]
    assert "user_id" not in at.session_state

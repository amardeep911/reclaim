"""End-to-end tests for Phase 2 pages: cravings, journal, savings, achievements, trusted contact."""

from tests.fake_supabase import FakeSupabase
from tests.test_app_flow import assert_clean, click, onboard


def open_page(fake: FakeSupabase, page: str, kind: str = "smoking"):
    at = onboard(fake, kind)
    return at.switch_page(page).run()


# ---------------------------------------------------------------- cravings

def test_resisted_craving_logs_and_marks_hour():
    fake = FakeSupabase()
    at = open_page(fake, "pages/4_Craving_Manager.py")
    assert_clean(at)
    at = click(at, key="craving-open")
    at.slider[0].set_value(8)
    at.selectbox[0].set_value("Stress")
    at = click(at, "Log craving")
    assert_clean(at)

    [craving] = fake.store["craving_logs"]
    assert craving["resisted"] is True and craving["intensity"] == 8 and craving["trigger"] == "Stress"
    assert [h["status"] for h in fake.store["hourly_logs"]] == ["craving_resisted"]
    assert not fake.store.get("consumption_logs")
    # The coping toolkit is shown right after logging
    assert any("riding it out" in m.value for m in at.markdown)
    at = click(at, "I'm feeling steadier – close")
    assert_clean(at)
    assert "craving_logged" not in at.session_state


def test_craving_followed_by_use_logs_consumption():
    fake = FakeSupabase()
    at = open_page(fake, "pages/4_Craving_Manager.py")
    at = click(at, key="craving-open")
    at.radio(key="craving-outcome").set_value("consumed").run()
    at.number_input[0].set_value(2)
    at = click(at, "Log craving")
    assert_clean(at)

    [craving] = fake.store["craving_logs"]
    assert craving["resisted"] is False
    [entry] = fake.store["consumption_logs"]
    assert entry["quantity"] == 2 and entry["cost"] == 36
    assert [h["status"] for h in fake.store["hourly_logs"]] == ["consumed"]
    assert any("honestly" in m.value for m in at.markdown)  # supportive, not shaming


def test_resisted_craving_never_overwrites_a_consumed_hour():
    fake = FakeSupabase()
    at = open_page(fake, "pages/4_Craving_Manager.py")
    at = click(at, key="craving-open")
    at.radio(key="craving-outcome").set_value("consumed").run()
    at = click(at, "Log craving")
    at = click(at, "I'm feeling steadier – close")
    at = click(at, key="craving-open")
    at = click(at, "Log craving")
    assert_clean(at)
    assert [h["status"] for h in fake.store["hourly_logs"]] == ["consumed"]
    assert len(fake.store["craving_logs"]) == 2


def test_alcohol_craving_shows_withdrawal_guidance():
    fake = FakeSupabase()
    at = open_page(fake, "pages/4_Craving_Manager.py", kind="alcohol")
    at = click(at, key="craving-open")
    at.toggle(key="craving-symptoms").set_value(True).run()
    assert any("medical help" in e.value for e in at.error)


def test_craving_stats_and_history_render():
    fake = FakeSupabase()
    at = open_page(fake, "pages/4_Craving_Manager.py")
    for _ in range(3):
        at = click(at, key="craving-open")
        at.selectbox[0].set_value("After eating")
        at = click(at, "Log craving")
        at = click(at, "I'm feeling steadier – close")
    assert_clean(at)
    assert any("most common trigger" in i.value for i in at.info)
    assert len(at.dataframe) == 1


# ---------------------------------------------------------------- journal

def test_journal_save_update_delete():
    fake = FakeSupabase()
    at = open_page(fake, "pages/8_Journal.py")
    assert_clean(at)
    at = click(at, "Save entry")
    assert any("few words" in e.value for e in at.error)  # empty entries are rejected
    assert not fake.store.get("journal_entries")

    at.text_area[0].input("Hard afternoon but I made it.")
    at = click(at, "Save entry")
    assert_clean(at)
    [entry] = fake.store["journal_entries"]
    assert entry["day_summary"] == "Hard afternoon but I made it."

    at.text_area[2].input("Went for a walk instead.")
    at = click(at, "Update entry")
    assert_clean(at)
    assert len(fake.store["journal_entries"]) == 1  # one entry per day
    assert fake.store["journal_entries"][0]["went_well"] == "Went for a walk instead."

    at.checkbox[0].check().run()
    at = click(at, "Delete entry")
    assert_clean(at)
    assert fake.store["journal_entries"] == []


# ---------------------------------------------------------------- savings

def test_savings_goal_add_and_complete():
    fake = FakeSupabase()
    at = open_page(fake, "pages/11_Savings.py")
    assert_clean(at)
    at.text_input[0].input("New bike")
    at.number_input[0].set_value(8000)
    at = click(at, "Add goal")
    assert_clean(at)
    [goal] = fake.store["savings_goals"]
    assert goal["title"] == "New bike" and goal["target_amount"] == 8000

    at = click(at, "Mark as bought ✓")
    assert_clean(at)
    assert fake.store["savings_goals"][0]["is_completed"] is True


# ---------------------------------------------------------------- achievements

def test_first_tracked_hour_unlocks_achievement_once():
    fake = FakeSupabase()
    at = open_page(fake, "pages/2_Hourly_Tracker.py")
    assert not fake.store.get("user_achievements")  # nothing earned just by signing up
    at = click(at, key="quick-success")
    at.switch_page("pages/1_Dashboard.py").run()
    assert_clean(at)

    codes = {a["id"]: a["code"] for a in fake.store["achievements"]}
    unlocked = [codes[u["achievement_id"]] for u in fake.store["user_achievements"]]
    assert unlocked == ["smoke_free_1h"]

    at.switch_page("pages/6_Achievements.py").run()
    assert_clean(at)
    assert any("unlocked" in s.value for s in at.success)
    assert all(u["seen"] for u in fake.store["user_achievements"])

    at.switch_page("pages/1_Dashboard.py").run()
    assert len(fake.store["user_achievements"]) == 1  # never duplicated


def test_resisted_cravings_count_toward_achievements():
    fake = FakeSupabase()
    at = open_page(fake, "pages/4_Craving_Manager.py")
    for _ in range(10):
        at = click(at, key="craving-open")
        at = click(at, "Log craving")
        at = click(at, "I'm feeling steadier – close")
    at.switch_page("pages/6_Achievements.py").run()
    assert_clean(at)
    codes = {a["id"]: a["code"] for a in fake.store["achievements"]}
    assert "cravings_10" in {codes[u["achievement_id"]] for u in fake.store["user_achievements"]}


# ---------------------------------------------------------------- settings

def test_trusted_contact_validation():
    fake = FakeSupabase()
    at = open_page(fake, "pages/10_Settings.py")
    at.text_input(key="contact-name").input("Priya")
    at.text_input(key="contact-phone").input("javascript:alert(1)")
    at = click(at, "Save profile")
    assert any("Phone numbers" in e.value for e in at.error)
    assert fake.store["profiles"][0]["trusted_contact_phone"] is None

    at.text_input(key="contact-phone").input("+91 98765 43210")
    at = click(at, "Save profile")
    assert_clean(at)
    assert fake.store["profiles"][0]["trusted_contact_phone"] == "+91 98765 43210"


# ---------------------------------------------------------------- sleep hours

def test_sleep_card_logs_last_night_in_one_tap():
    fake = FakeSupabase()
    at = open_page(fake, "pages/2_Hourly_Tracker.py")
    assert_clean(at)
    at = click(at, key="hourly-sleep-log-smoking")
    assert_clean(at)
    logs = fake.store["hourly_logs"]
    assert len(logs) == 8 and {r["status"] for r in logs} == {"success"}  # 11 PM – 7 AM
    assert not any(b.key == "hourly-sleep-log-smoking" for b in at.button)  # card is gone

    # Today's totals include the 7 sleep hours after midnight; completion still measures waking hours only
    at.switch_page("pages/1_Dashboard.py").run()
    assert_clean(at)
    assert any("of 7 logged today" in m.value for m in at.markdown)


def test_sleep_card_keeps_a_consumed_night_hour():
    from utils.datetime_utils import local_today, sleep_slots
    from services.database_service import iso

    fake = FakeSupabase()
    at = onboard(fake, "smoking")
    ctx = at.session_state["ctx"]
    three_am = [s for s in sleep_slots(local_today(ctx.tz), ctx.tz, 7, 23) if s.label == "3 AM"][0]
    fake.table("hourly_logs").insert({"user_id": fake.user_id, "addiction_type": "smoking", "status": "consumed",
                                      "slot_start": iso(three_am.start),
                                      "slot_end": iso(three_am.end)}).execute()
    at.switch_page("pages/1_Dashboard.py").run()
    at = click(at, key="dash-sleep-log-smoking")
    assert_clean(at)
    statuses = sorted(r["status"] for r in fake.store["hourly_logs"])
    assert statuses.count("consumed") == 1 and statuses.count("success") == 7


def test_sleep_card_can_be_skipped():
    fake = FakeSupabase()
    at = open_page(fake, "pages/2_Hourly_Tracker.py")
    at = click(at, key="hourly-sleep-skip-smoking")
    assert_clean(at)
    assert not fake.store.get("hourly_logs")
    assert not any(b.key == "hourly-sleep-log-smoking" for b in at.button)

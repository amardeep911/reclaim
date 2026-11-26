"""End-to-end tests for the Analytics page with several weeks of seeded history."""

from datetime import datetime, timedelta, timezone

import pytest

from services.database_service import iso
from tests.fake_supabase import FakeSupabase
from tests.test_app_flow import assert_clean, onboard
from utils.datetime_utils import generate_day_slots, local_today

DAYS = 21


def seed_history(fake: FakeSupabase, at, kind: str) -> None:
    """Three weeks of realistic data: fewer cigarettes over time, cravings after lunch, most hours tracked."""
    ctx = at.session_state["ctx"]
    tz, today = ctx.tz, local_today(ctx.tz)
    start = today - timedelta(days=DAYS)
    for row in fake.store["addiction_profiles"]:
        row["tracking_start_date"] = start.isoformat()
    now = datetime.now(timezone.utc)
    habits = ["smoking", "alcohol"] if kind == "both" else [kind]
    for i in range(DAYS):
        day = start + timedelta(days=i)
        slots = generate_day_slots(day, tz, 8, 22)
        for a in habits:
            per_day = max(1, 8 - i // 3) if a == "smoking" else (2 if i % 3 == 0 else 0)
            for n in range(per_day):
                slot = slots[(4 + n * 2) % len(slots)]
                fake.table("consumption_logs").insert({
                    "user_id": fake.user_id, "addiction_type": a, "occurred_at": iso(slot.start + timedelta(minutes=10)),
                    "quantity": 1.0, "cost": 18.0 if a == "smoking" else 300.0, "trigger": "After eating",
                    **({"beverage_type": "Beer", "volume_ml": 330, "abv_percent": 5, "standard_drinks": 1.3}
                       if a == "alcohol" else {}),
                }).execute()
            for s in slots[:10]:
                if s.end <= now:
                    fake.table("hourly_logs").insert({
                        "user_id": fake.user_id, "addiction_type": a, "slot_start": iso(s.start),
                        "slot_end": iso(s.end), "status": "craving_resisted" if s.local_start.hour == 14 else "success",
                    }).execute()
            fake.table("craving_logs").insert({
                "user_id": fake.user_id, "addiction_type": a, "occurred_at": iso(slots[6].start + timedelta(minutes=5)),
                "intensity": 6, "trigger": "After eating" if i % 2 else "Stress", "resisted": i % 4 != 0,
                "coping_strategy": "Short walk",
            }).execute()
    del at.session_state["ctx"]  # reload the profile with the new tracking start


@pytest.mark.parametrize("kind", ["smoking", "alcohol", "both"])
def test_analytics_renders_every_range_and_tab(kind):
    fake = FakeSupabase()
    at = onboard(fake, kind)
    seed_history(fake, at, kind)
    at.switch_page("pages/5_Analytics.py").run()
    assert_clean(at)
    for choice in ["7", "30", "90", "all"]:
        at.segmented_control(key="analytics-range").set_value(choice).run()
        assert_clean(at)
    at.segmented_control(key="report-kind").set_value("month").run()
    assert_clean(at)
    assert len(at.tabs) >= 5
    assert any("Metric" in df.value.columns for df in at.dataframe)


def test_insights_are_backed_by_the_seeded_data():
    fake = FakeSupabase()
    at = onboard(fake, "smoking")
    seed_history(fake, at, "smoking")
    at.switch_page("pages/5_Analytics.py").run()
    at.segmented_control(key="analytics-range").set_value("30").run()
    assert_clean(at)
    text = " ".join(m.value for m in at.markdown)
    assert "decreased by" in text                 # 8/day falling toward 1/day vs a baseline of 10
    assert "most common craving trigger" in text  # After eating vs Stress split 10/11 in favour of one
    assert "works well for you" in text           # Short walk: resisted 3 of every 4


def test_analytics_with_no_history_shows_friendly_state():
    fake = FakeSupabase()
    at = onboard(fake, "smoking")
    at.switch_page("pages/5_Analytics.py").run()
    assert_clean(at)
    assert any("Not enough data" in c.value for c in at.caption)

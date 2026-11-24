from datetime import date, datetime, timedelta, timezone

from utils.datetime_utils import (
    day_bounds_utc, format_duration, generate_day_slots, get_tz, hour_label, parse_ts, slot_start_for,
)
from utils.validators import (
    clean_text, validate_email, validate_password, validate_slot_not_future, validate_tracking_window,
)

UTC = timezone.utc
IST = get_tz("Asia/Kolkata")
NY = get_tz("America/New_York")


def test_day_bounds_in_ist():
    start, end = day_bounds_utc(date(2026, 11, 25), IST)
    assert start == datetime(2026, 11, 24, 18, 30, tzinfo=UTC)
    assert end - start == timedelta(hours=24)


def test_slots_follow_waking_window_and_half_hour_offset():
    slots = generate_day_slots(date(2026, 11, 25), IST, 8, 22)
    assert len(slots) == 14
    assert slots[0].label == "8 AM" and slots[-1].label == "9 PM"
    assert slots[0].range_label == "8 AM – 9 AM"
    # 8 AM IST == 02:30 UTC
    assert slots[0].start == datetime(2026, 11, 25, 2, 30, tzinfo=UTC)
    assert all(s.end - s.start == timedelta(hours=1) for s in slots)


def test_dst_days_have_23_and_25_hours():
    assert len(generate_day_slots(date(2026, 3, 8), NY)) == 23   # spring forward
    assert len(generate_day_slots(date(2026, 11, 1), NY)) == 25  # fall back
    assert len(generate_day_slots(date(2026, 6, 1), NY)) == 24


def test_slot_start_for_instant():
    instant = datetime(2026, 11, 25, 9, 47, tzinfo=UTC)  # 15:17 IST
    assert slot_start_for(instant, IST) == datetime(2026, 11, 25, 9, 30, tzinfo=UTC)
    assert slot_start_for(instant, UTC) == datetime(2026, 11, 25, 9, 0, tzinfo=UTC)


def test_slot_start_matches_generated_slots():
    slots = generate_day_slots(date(2026, 11, 25), IST)
    for s in slots:
        assert slot_start_for(s.start + timedelta(minutes=59), IST) == s.start


def test_parse_ts_variants():
    expected = datetime(2026, 11, 25, 3, 30, tzinfo=UTC)
    assert parse_ts("2026-11-25T03:30:00+00:00") == expected
    assert parse_ts("2026-11-25T03:30:00Z") == expected
    assert parse_ts("2026-11-25T09:00:00+05:30") == expected
    assert parse_ts("2026-11-25T03:30:00.12345+00:00").replace(microsecond=0) == expected
    assert parse_ts(None) is None


def test_hour_label():
    assert hour_label(datetime(2026, 1, 1, 0)) == "12 AM"
    assert hour_label(datetime(2026, 1, 1, 12)) == "12 PM"
    assert hour_label(datetime(2026, 1, 1, 15)) == "3 PM"


def test_format_duration():
    assert format_duration(timedelta(minutes=5)) == "5m"
    assert format_duration(timedelta(hours=3, minutes=10)) == "3h 10m"
    assert format_duration(timedelta(days=2, hours=4)) == "2d 4h"
    assert format_duration(timedelta(seconds=-5)) == "0m"


def test_future_slot_rejected():
    now = datetime(2026, 11, 25, 10, tzinfo=UTC)
    assert validate_slot_not_future(now + timedelta(hours=1), now)
    assert validate_slot_not_future(now, now) is None


def test_validators():
    assert validate_email("a@b.co") is None and validate_email("nope")
    assert validate_password("short1") and validate_password("longenough") and validate_password("abcdefg1") is None
    assert validate_tracking_window(7, 23) is None
    assert validate_tracking_window(22, 23)
    assert clean_text("  hi  ", 10) == "hi" and clean_text("   ", 10) is None and clean_text("abcdef", 3) == "abc"


def test_unknown_timezone_falls_back_to_utc():
    assert get_tz("Not/AZone").key == "UTC"


def test_validate_phone():
    from utils.validators import validate_phone
    assert validate_phone("") is None and validate_phone(None) is None
    assert validate_phone("+91 98765-43210") is None
    assert validate_phone("(020) 7946 0958") is None
    assert validate_phone("javascript:alert(1)")
    assert validate_phone("+-")


def test_sleep_slots_span_bedtime_to_wake():
    from utils.datetime_utils import sleep_slots
    night = sleep_slots(date(2026, 11, 25), IST, 7, 23)
    assert [s.label for s in night] == ["11 PM", "12 AM", "1 AM", "2 AM", "3 AM", "4 AM", "5 AM", "6 AM"]
    assert night[0].local_start.date() == date(2026, 11, 24)
    assert night[-1].end == datetime(2026, 11, 25, 1, 30, tzinfo=UTC)  # 7 AM IST
    assert sleep_slots(date(2026, 11, 25), IST, 0, 24) == []           # tracking all day: no sleep hours
    assert len(sleep_slots(date(2026, 11, 25), IST, 7, 24)) == 7       # bedtime at midnight

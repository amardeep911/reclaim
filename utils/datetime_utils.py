"""Timezone-aware date/time helpers.

Everything is stored in UTC. A user's "day" and "hour slots" are defined in
their own timezone, so all conversions go through ZoneInfo here.
"""

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from functools import lru_cache
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError, available_timezones

import pandas as pd

UTC = timezone.utc


@dataclass(frozen=True)
class Slot:
    start: datetime        # UTC
    end: datetime          # UTC
    local_start: datetime  # in the user's timezone

    @property
    def label(self) -> str:
        return hour_label(self.local_start)

    @property
    def range_label(self) -> str:
        return f"{hour_label(self.local_start)} – {hour_label(self.local_start + timedelta(hours=1))}"


def get_tz(name: str | None) -> ZoneInfo:
    try:
        return ZoneInfo(name or "UTC")
    except (ZoneInfoNotFoundError, ValueError):
        return ZoneInfo("UTC")


@lru_cache(maxsize=1)
def timezone_choices() -> list[str]:
    skip = ("Etc/", "posix/", "right/", "SystemV/")
    return sorted(tz for tz in available_timezones() if "/" in tz and not tz.startswith(skip)) + ["UTC"]


def now_utc() -> datetime:
    return datetime.now(UTC)


def local_now(tz: ZoneInfo) -> datetime:
    return now_utc().astimezone(tz)


def local_today(tz: ZoneInfo) -> date:
    return local_now(tz).date()


def day_bounds_utc(day: date, tz: ZoneInfo) -> tuple[datetime, datetime]:
    """UTC instants of local midnight at the start and end of `day`."""
    start = datetime.combine(day, time.min, tzinfo=tz)
    end = datetime.combine(day + timedelta(days=1), time.min, tzinfo=tz)
    return start.astimezone(UTC), end.astimezone(UTC)


def range_bounds_utc(first_day: date, last_day: date, tz: ZoneInfo) -> tuple[datetime, datetime]:
    return day_bounds_utc(first_day, tz)[0], day_bounds_utc(last_day, tz)[1]


def generate_day_slots(day: date, tz: ZoneInfo, wake_hour: int = 0, sleep_hour: int = 24) -> list[Slot]:
    """One-hour slots for a local calendar day, limited to the waking window.

    Walks real UTC hours between local midnights, so days with a daylight-saving
    change correctly have 23 or 25 hours.
    """
    start, end = day_bounds_utc(day, tz)
    slots = []
    cursor = start
    while cursor < end:
        local = cursor.astimezone(tz)
        if wake_hour <= local.hour < sleep_hour:
            slots.append(Slot(start=cursor, end=cursor + timedelta(hours=1), local_start=local))
        cursor += timedelta(hours=1)
    return slots


def sleep_slots(today: date, tz: ZoneInfo, wake_hour: int, sleep_hour: int) -> list[Slot]:
    """Last night's hours: from bedtime yesterday until wake-up time today."""
    return (generate_day_slots(today - timedelta(days=1), tz, sleep_hour, 24)
            + generate_day_slots(today, tz, 0, wake_hour))


def slot_start_for(instant: datetime, tz: ZoneInfo) -> datetime:
    """UTC start of the local hour containing `instant`."""
    local = instant.astimezone(tz).replace(minute=0, second=0, microsecond=0)
    return local.astimezone(UTC)


def hour_label(local_dt: datetime) -> str:
    h = local_dt.hour % 12 or 12
    return f"{h} {'AM' if local_dt.hour < 12 else 'PM'}"


def parse_ts(value) -> datetime | None:
    """Parse a Supabase timestamp string into an aware UTC datetime."""
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=UTC)
    ts = pd.Timestamp(value)
    if ts.tzinfo is None:
        ts = ts.tz_localize("UTC")
    return ts.tz_convert("UTC").to_pydatetime()


def parse_date(value) -> date | None:
    if value is None or value == "":
        return None
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value)[:10])


def format_duration(delta: timedelta) -> str:
    seconds = max(0, int(delta.total_seconds()))
    days, rem = divmod(seconds, 86400)
    hours, rem = divmod(rem, 3600)
    minutes = rem // 60
    if days:
        return f"{days}d {hours}h"
    if hours:
        return f"{hours}h {minutes}m"
    return f"{minutes}m"


def format_local(instant: datetime | None, tz: ZoneInfo, fmt: str = "%d %b, %I:%M %p") -> str:
    if instant is None:
        return "—"
    return instant.astimezone(tz).strftime(fmt).replace(" 0", " ")

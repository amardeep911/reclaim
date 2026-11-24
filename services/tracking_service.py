"""Hourly statuses and consumption events.

Business rules enforced here:
  * An hour is only ever stored when the user logs it – nothing is auto-marked.
  * Hours that have not started yet cannot be logged.
  * Consumption events live in consumption_logs, separate from hourly statuses.
    Logging consumption marks its hour as "consumed"; deleting the last
    consumption in an hour reverts that hour to "not tracked".
  * One row per (user, addiction, hour) – enforced by a unique constraint and upserts.
"""

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from services.database_service import db, iso, select_all, uid
from utils.constants import CONSUMED, STORED_STATUSES
from utils.datetime_utils import now_utc, parse_ts, slot_start_for
from utils.validators import validate_not_future, validate_quantity, validate_slot_not_future


class TrackingError(ValueError):
    """Raised for invalid user input; the message is safe to show in the UI."""


# ---------------------------------------------------------------------------
# Hourly logs
# ---------------------------------------------------------------------------

def get_hourly_logs(start: datetime, end: datetime, addiction_type: str | None = None) -> list[dict]:
    def filters(q):
        q = q.eq("user_id", uid()).gte("slot_start", iso(start)).lt("slot_start", iso(end))
        if addiction_type:
            q = q.eq("addiction_type", addiction_type)
        return q.order("slot_start")

    rows = select_all("hourly_logs", filters)
    for row in rows:
        row["slot_start"] = parse_ts(row["slot_start"])
    return rows


def count_hours(addiction_type: str, statuses: tuple[str, ...], since: datetime | None = None,
                until: datetime | None = None) -> int:
    """Count tracked hours with the given statuses. Only completed hours count when `until` is given."""
    q = (db().table("hourly_logs").select("id", count="exact", head=True)
         .eq("user_id", uid()).eq("addiction_type", addiction_type).in_("status", list(statuses)))
    if since:
        q = q.gte("slot_start", iso(since))
    if until:
        q = q.lte("slot_end", iso(until))
    return q.execute().count or 0


def get_hour_status(addiction_type: str, slot_start: datetime) -> str | None:
    rows = (db().table("hourly_logs").select("status").eq("user_id", uid())
            .eq("addiction_type", addiction_type).eq("slot_start", iso(slot_start)).execute().data)
    return rows[0]["status"] if rows else None


def _hour_payload(addiction_type: str, slot_start: datetime, status: str) -> dict:
    if status not in STORED_STATUSES:
        raise TrackingError("Unknown status.")
    error = validate_slot_not_future(slot_start, now_utc())
    if error:
        raise TrackingError(error)
    return {
        "user_id": uid(),
        "addiction_type": addiction_type,
        "slot_start": iso(slot_start),
        "slot_end": iso(slot_start + timedelta(hours=1)),
        "status": status,
    }


def set_hour_status(addiction_type: str, slot_start: datetime, status: str, notes: str | None = None,
                    update_notes: bool = False) -> None:
    payload = _hour_payload(addiction_type, slot_start, status)
    if update_notes:
        payload["notes"] = notes
    db().table("hourly_logs").upsert(payload, on_conflict="user_id,addiction_type,slot_start").execute()


def set_hours_bulk(addiction_type: str, slot_starts: list[datetime], status: str) -> int:
    """Mark several hours at once (future hours are skipped). Returns how many were saved."""
    now = now_utc()
    payload = [_hour_payload(addiction_type, s, status) for s in slot_starts if s <= now]
    if payload:
        db().table("hourly_logs").upsert(payload, on_conflict="user_id,addiction_type,slot_start").execute()
    return len(payload)


def clear_hour(addiction_type: str, slot_start: datetime) -> None:
    """Return an hour to 'not tracked'. Consumption events in that hour are kept."""
    (db().table("hourly_logs").delete().eq("user_id", uid())
     .eq("addiction_type", addiction_type).eq("slot_start", iso(slot_start)).execute())


# ---------------------------------------------------------------------------
# Consumption logs
# ---------------------------------------------------------------------------

def get_consumption(start: datetime | None, end: datetime | None, addiction_type: str | None = None) -> list[dict]:
    def filters(q):
        q = q.eq("user_id", uid())
        if start:
            q = q.gte("occurred_at", iso(start))
        if end:
            q = q.lt("occurred_at", iso(end))
        if addiction_type:
            q = q.eq("addiction_type", addiction_type)
        return q.order("occurred_at", desc=True)

    rows = select_all("consumption_logs", filters)
    for row in rows:
        row["occurred_at"] = parse_ts(row["occurred_at"])
    return rows


def get_last_consumption(addiction_type: str) -> datetime | None:
    rows = (db().table("consumption_logs").select("occurred_at").eq("user_id", uid())
            .eq("addiction_type", addiction_type).order("occurred_at", desc=True).limit(1).execute().data)
    return parse_ts(rows[0]["occurred_at"]) if rows else None


def _validate_consumption(occurred_at: datetime, quantity: float) -> None:
    error = validate_not_future(occurred_at, now_utc() + timedelta(minutes=1)) or validate_quantity(quantity)
    if error:
        raise TrackingError(error)


def log_consumption(addiction_type: str, occurred_at: datetime, quantity: float, tz: ZoneInfo,
                    **fields) -> dict:
    """Store a consumption event and mark its hour as consumed."""
    _validate_consumption(occurred_at, quantity)
    payload = {
        **{k: v for k, v in fields.items() if v is not None},
        "user_id": uid(),
        "addiction_type": addiction_type,
        "occurred_at": iso(occurred_at),
        "quantity": quantity,
    }
    row = db().table("consumption_logs").insert(payload).execute().data[0]
    set_hour_status(addiction_type, slot_start_for(occurred_at, tz), CONSUMED)
    return row


def update_consumption(row_id: str, occurred_at: datetime, quantity: float, tz: ZoneInfo, **fields) -> None:
    _validate_consumption(occurred_at, quantity)
    old = _get_consumption_row(row_id)
    payload = {**fields, "occurred_at": iso(occurred_at), "quantity": quantity}
    db().table("consumption_logs").update(payload).eq("id", row_id).eq("user_id", uid()).execute()
    if old:
        new_slot = slot_start_for(occurred_at, tz)
        set_hour_status(old["addiction_type"], new_slot, CONSUMED)
        old_slot = slot_start_for(parse_ts(old["occurred_at"]), tz)
        if old_slot != new_slot:
            _resync_hour(old["addiction_type"], old_slot)


def delete_consumption(row_id: str, tz: ZoneInfo) -> None:
    old = _get_consumption_row(row_id)
    db().table("consumption_logs").delete().eq("id", row_id).eq("user_id", uid()).execute()
    if old:
        _resync_hour(old["addiction_type"], slot_start_for(parse_ts(old["occurred_at"]), tz))


def _get_consumption_row(row_id: str) -> dict | None:
    rows = db().table("consumption_logs").select("*").eq("id", row_id).eq("user_id", uid()).execute().data
    return rows[0] if rows else None


def _resync_hour(addiction_type: str, slot_start: datetime) -> None:
    """If an hour is marked consumed but no consumption remains in it, mark it not tracked."""
    remaining = get_consumption(slot_start, slot_start + timedelta(hours=1), addiction_type)
    if remaining:
        return
    (db().table("hourly_logs").delete().eq("user_id", uid()).eq("addiction_type", addiction_type)
     .eq("slot_start", iso(slot_start)).eq("status", CONSUMED).execute())

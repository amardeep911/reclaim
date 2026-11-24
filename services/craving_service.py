"""Craving logs.

A resisted craving also marks its hour as "craving resisted" (unless consumption
was already logged in that hour). A craving the user acted on can log the
consumption at the same time, which marks the hour as consumed.
"""

from datetime import datetime
from zoneinfo import ZoneInfo

from services.database_service import db, iso, select_all, uid
from services.tracking_service import TrackingError, get_hour_status, log_consumption, set_hour_status
from utils.constants import CONSUMED, CRAVING_RESISTED
from utils.datetime_utils import now_utc, parse_ts, slot_start_for
from utils.validators import validate_not_future

EDITABLE = ("intensity", "trigger", "mood", "location", "resisted", "coping_strategy", "notes")


def get_cravings(start: datetime | None, end: datetime | None, addiction_type: str | None = None) -> list[dict]:
    def filters(q):
        q = q.eq("user_id", uid())
        if start:
            q = q.gte("occurred_at", iso(start))
        if end:
            q = q.lt("occurred_at", iso(end))
        if addiction_type:
            q = q.eq("addiction_type", addiction_type)
        return q.order("occurred_at", desc=True)

    rows = select_all("craving_logs", filters)
    for row in rows:
        row["occurred_at"] = parse_ts(row["occurred_at"])
    return rows


def count_resisted(addiction_type: str | None = None) -> int:
    q = (db().table("craving_logs").select("id", count="exact", head=True)
         .eq("user_id", uid()).eq("resisted", True))
    if addiction_type:
        q = q.eq("addiction_type", addiction_type)
    return q.execute().count or 0


def log_craving(addiction_type: str, occurred_at: datetime, intensity: int, resisted: bool, tz: ZoneInfo,
                quantity: float = 0, consumption_fields: dict | None = None, **fields) -> dict:
    if error := validate_not_future(occurred_at, now_utc()):
        raise TrackingError(error)
    if not 1 <= int(intensity) <= 10:
        raise TrackingError("Intensity must be between 1 and 10.")
    payload = {
        **{k: v for k, v in fields.items() if k in EDITABLE and v is not None},
        "user_id": uid(),
        "addiction_type": addiction_type,
        "occurred_at": iso(occurred_at),
        "intensity": int(intensity),
        "resisted": resisted,
    }
    row = db().table("craving_logs").insert(payload).execute().data[0]

    slot = slot_start_for(occurred_at, tz)
    if resisted:
        if get_hour_status(addiction_type, slot) != CONSUMED:
            set_hour_status(addiction_type, slot, CRAVING_RESISTED)
    elif quantity > 0:
        log_consumption(addiction_type, occurred_at, quantity, tz,
                        trigger=fields.get("trigger"), mood=fields.get("mood"), location=fields.get("location"),
                        **(consumption_fields or {}))
    return row


def update_craving(row_id: str, fields: dict) -> None:
    payload = {k: v for k, v in fields.items() if k in EDITABLE}
    if "intensity" in payload and not 1 <= int(payload["intensity"]) <= 10:
        raise TrackingError("Intensity must be between 1 and 10.")
    db().table("craving_logs").update(payload).eq("id", row_id).eq("user_id", uid()).execute()


def delete_craving(row_id: str) -> None:
    """Deletes only the craving record; hourly statuses and consumption entries are kept."""
    db().table("craving_logs").delete().eq("id", row_id).eq("user_id", uid()).execute()

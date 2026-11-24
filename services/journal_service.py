"""Private daily journal – one entry per local date."""

from datetime import date

from services.database_service import db, select_all, uid

FIELDS = ("mood", "day_summary", "difficult_situations", "went_well", "craving_strength", "lessons", "tomorrow_focus")


def get_entry(day: date) -> dict | None:
    rows = (db().table("journal_entries").select("*").eq("user_id", uid())
            .eq("entry_date", day.isoformat()).execute().data)
    return rows[0] if rows else None


def list_entries(first: date | None = None, last: date | None = None) -> list[dict]:
    def filters(q):
        q = q.eq("user_id", uid())
        if first:
            q = q.gte("entry_date", first.isoformat())
        if last:
            q = q.lte("entry_date", last.isoformat())
        return q.order("entry_date", desc=True)

    return select_all("journal_entries", filters)


def save_entry(day: date, fields: dict) -> None:
    payload = {**{k: fields.get(k) for k in FIELDS}, "user_id": uid(), "entry_date": day.isoformat()}
    db().table("journal_entries").upsert(payload, on_conflict="user_id,entry_date").execute()


def delete_entry(entry_id: str) -> None:
    db().table("journal_entries").delete().eq("id", entry_id).eq("user_id", uid()).execute()


def has_content(fields: dict) -> bool:
    return any(fields.get(k) for k in FIELDS if k not in ("mood", "craving_strength")) or bool(fields.get("mood"))

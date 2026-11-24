"""A tiny in-memory stand-in for the supabase-py client, for tests only.

Supports just the query-builder calls Reclaim uses. Column defaults mirror
database/schema.sql so pages behave as they would against the real database.
"""

import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

SCHEMA = Path(__file__).resolve().parent.parent / "database" / "schema.sql"


def achievement_catalogue() -> list[dict]:
    """Parse the seeded achievement rows straight out of schema.sql so tests use the real catalogue."""
    pattern = re.compile(r"\('(\w+)',\s*'([^']*)',\s*'([^']*)',\s*'(\w+)',\s*(null|'\w+'),\s*(\d+),\s*'([^']*)',\s*(\d+)\)")
    rows = []
    for code, title, desc, cat, addiction, threshold, icon, order in pattern.findall(SCHEMA.read_text()):
        rows.append({"id": str(uuid.uuid4()), "code": code, "title": title, "description": desc, "category": cat,
                     "addiction_type": None if addiction == "null" else addiction.strip("'"),
                     "threshold": float(threshold), "icon": icon, "sort_order": int(order)})
    return rows

DEFAULTS = {
    "profiles": {"trusted_contact_name": None, "trusted_contact_phone": None, "display_name": "", "age": None, "timezone": "UTC", "addiction_type": None, "why_quit": None,
                 "aspirations": None, "motivators": None, "wake_hour": 7, "sleep_hour": 23,
                 "currency_symbol": "₹", "standard_drink_region": "WHO", "volume_unit": "ml",
                 "share_journal_with_ai": False, "onboarding_completed_at": None},
    "addiction_profiles": {"is_active": True, "dependence_risk": False, "quit_date": None},
    "recovery_goals": {"is_active": True, "target_per_day": None, "target_date": None, "achieved_at": None},
    "hourly_logs": {"notes": None},
    "consumption_logs": {},
    "daily_logs": {},
    "craving_logs": {"trigger": None, "mood": None, "location": None, "coping_strategy": None, "notes": None},
    "savings_goals": {"icon": "🎯", "is_completed": False},
    "user_achievements": {"seen": False},
    "journal_entries": {},
    "notification_preferences": {"hourly_reminder": True, "morning_checkin": True, "morning_time": "08:00:00",
                                 "evening_reflection": True, "evening_time": "21:00:00", "daily_motivation": True,
                                 "weekly_report": True, "milestone_alerts": True, "email_enabled": False},
}


class Query:
    def __init__(self, store: dict, table: str):
        self.store, self.table = store, table
        self.op, self.payload, self.filters = "select", None, []
        self.order_by, self.limit_n, self.offset, self.count, self.head, self.on_conflict = None, None, 0, None, False, ""

    # --- operations
    def select(self, *_cols, count=None, head=None):
        self.op, self.count, self.head = "select", count, bool(head)
        return self

    def insert(self, payload):
        self.op, self.payload = "insert", payload
        return self

    def upsert(self, payload, on_conflict="", ignore_duplicates=False):
        self.op, self.payload, self.on_conflict = "upsert", payload, on_conflict
        self.ignore_duplicates = ignore_duplicates
        return self

    def update(self, payload):
        self.op, self.payload = "update", payload
        return self

    def delete(self):
        self.op = "delete"
        return self

    # --- filters / modifiers
    def eq(self, col, val):
        self.filters.append(lambda r: r.get(col) == val)
        return self

    def gte(self, col, val):
        self.filters.append(lambda r: r.get(col) is not None and r[col] >= val)
        return self

    def lt(self, col, val):
        self.filters.append(lambda r: r.get(col) is not None and r[col] < val)
        return self

    def lte(self, col, val):
        self.filters.append(lambda r: r.get(col) is not None and r[col] <= val)
        return self

    def in_(self, col, vals):
        self.filters.append(lambda r: r.get(col) in vals)
        return self

    def order(self, col, desc=False):
        self.order_by = (col, desc)
        return self

    def limit(self, n):
        self.limit_n = n
        return self

    def range(self, start, end):
        self.offset, self.limit_n = start, end - start + 1
        return self

    # --- execution
    def _rows(self):
        return self.store.setdefault(self.table, [])

    def _new_row(self, values: dict) -> dict:
        now = datetime.now(timezone.utc).isoformat()
        row = {"id": str(uuid.uuid4()), **DEFAULTS.get(self.table, {}), "created_at": now, "updated_at": now}
        if self.table == "user_achievements":
            row["unlocked_at"] = now
        row.update(values)
        return row

    def execute(self):
        rows = self._rows()
        if self.op == "insert":
            items = self.payload if isinstance(self.payload, list) else [self.payload]
            new = [self._new_row(i) for i in items]
            rows.extend(new)
            return SimpleNamespace(data=new, count=None)
        if self.op == "upsert":
            items = self.payload if isinstance(self.payload, list) else [self.payload]
            keys = [k.strip() for k in self.on_conflict.split(",")] if self.on_conflict else ["id"]
            out = []
            for item in items:
                match = next((r for r in rows if all(r.get(k) == item.get(k) for k in keys)), None)
                if match:
                    if not getattr(self, "ignore_duplicates", False):
                        match.update(item)
                        out.append(match)
                else:
                    row = self._new_row(item)
                    rows.append(row)
                    out.append(row)
            return SimpleNamespace(data=out, count=None)

        matched = [r for r in rows if all(f(r) for f in self.filters)]
        if self.op == "update":
            for r in matched:
                r.update(self.payload)
            return SimpleNamespace(data=matched, count=None)
        if self.op == "delete":
            self.store[self.table] = [r for r in rows if r not in matched]
            return SimpleNamespace(data=matched, count=None)

        if self.order_by:
            col, desc = self.order_by
            matched = sorted(matched, key=lambda r: (r.get(col) is None, r.get(col)), reverse=desc)
        total = len(matched)
        matched = matched[self.offset:]
        if self.limit_n is not None:
            matched = matched[: self.limit_n]
        return SimpleNamespace(data=[] if self.head else [dict(r) for r in matched],
                               count=total if self.count else None)


class FakeAuth:
    def __init__(self, user_id: str, email: str):
        self.user = SimpleNamespace(id=user_id, email=email)

    def get_session(self):
        return SimpleNamespace(user=self.user)

    def sign_out(self):
        pass


class FakeSupabase:
    def __init__(self, user_id: str = "00000000-0000-0000-0000-000000000001", email: str = "test@example.com"):
        self.store: dict[str, list] = {"profiles": [{"id": user_id, **DEFAULTS["profiles"]}],
                                       "achievements": achievement_catalogue()}
        self.auth = FakeAuth(user_id, email)
        self.user_id = user_id
        self.rpc_calls = []

    def table(self, name: str) -> Query:
        return Query(self.store, name)

    def rpc(self, name, params=None):
        self.rpc_calls.append(name)
        return SimpleNamespace(execute=lambda: SimpleNamespace(data=None))

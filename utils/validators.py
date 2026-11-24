"""Input validation. Each validator returns an error message, or None if valid."""

import re
from datetime import datetime

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
PHONE_RE = re.compile(r"^[0-9+() -]{3,30}$")


def validate_email(email: str) -> str | None:
    if not email or not EMAIL_RE.match(email.strip()):
        return "Please enter a valid email address."
    return None


def validate_password(password: str) -> str | None:
    if len(password or "") < 8:
        return "Password must be at least 8 characters."
    if not re.search(r"[A-Za-z]", password) or not re.search(r"\d", password):
        return "Password must contain at least one letter and one number."
    return None


def validate_phone(phone: str | None) -> str | None:
    """Optional phone number: digits, spaces, +, -, ( ). Mirrors the database check constraint."""
    if not phone or not phone.strip():
        return None
    if not PHONE_RE.match(phone.strip()) or sum(ch.isdigit() for ch in phone) < 3:
        return "Phone numbers can only contain digits, spaces, +, - and brackets."
    return None


def validate_tracking_window(wake_hour: int, sleep_hour: int) -> str | None:
    if not (0 <= wake_hour <= 23 and 1 <= sleep_hour <= 24):
        return "Hours must be between 0 and 24."
    if sleep_hour - wake_hour < 4:
        return "Your tracking window should cover at least 4 hours."
    return None


def validate_slot_not_future(slot_start: datetime, now: datetime) -> str | None:
    if slot_start > now:
        return "You can't log an hour that hasn't started yet."
    return None


def validate_not_future(instant: datetime, now: datetime) -> str | None:
    if instant > now:
        return "That time is in the future."
    return None


def validate_quantity(quantity: float, maximum: float = 200) -> str | None:
    if quantity is None or quantity <= 0:
        return "Quantity must be greater than zero."
    if quantity > maximum:
        return f"Quantity must be {maximum:g} or less."
    return None


def clean_text(value: str | None, max_len: int) -> str | None:
    """Strip whitespace, truncate to the column limit, and turn empty strings into None."""
    if value is None:
        return None
    value = value.strip()
    return value[:max_len] if value else None

"""Reusable visual building blocks rendered as small HTML snippets.

Every piece of user-provided text is escaped before it reaches the page.
"""

import calendar
from datetime import date
from html import escape

import streamlit as st


def _html(markup: str) -> None:
    st.markdown(markup, unsafe_allow_html=True)


def page_header(title: str, subtitle: str | None = None, eyebrow: str | None = None) -> None:
    eyebrow_html = f'<div class="rc-eyebrow">{escape(eyebrow)}</div>' if eyebrow else ""
    subtitle_html = f"<p>{escape(subtitle)}</p>" if subtitle else ""
    _html(f'<div class="rc-hero">{eyebrow_html}<h1>{escape(title)}</h1>{subtitle_html}</div>')


def section(title: str, caption: str | None = None) -> None:
    caption_html = f"<p>{escape(caption)}</p>" if caption else ""
    _html(f'<div class="rc-section"><h3>{escape(title)}</h3>{caption_html}</div>')


def stat_cards(items: list[dict]) -> None:
    """items: [{"label": ..., "value": ..., "sub": optional, "accent": teal|green|yellow|red|blue}]"""
    cards = []
    for item in items:
        accent = f" rc-{item['accent']}" if item.get("accent") else ""
        sub = f'<div class="rc-sub">{escape(str(item["sub"]))}</div>' if item.get("sub") else ""
        cards.append(
            f'<div class="rc-card{accent}"><div class="rc-label">{escape(str(item["label"]))}</div>'
            f'<div class="rc-value">{escape(str(item["value"]))}</div>{sub}</div>'
        )
    _html(f'<div class="rc-grid">{"".join(cards)}</div>')


def quote_card(label: str, text: str) -> None:
    _html(f'<div class="rc-quote"><div class="rc-label">{escape(label)}</div>'
          f'<div class="rc-text">{escape(text)}</div></div>')


def progress_bar(pct: float, label: str, right_text: str | None = None) -> None:
    pct = max(0, min(100, round(pct)))
    right = escape(right_text if right_text is not None else f"{pct}%")
    _html(f'<div class="rc-progress-wrap"><div class="rc-progress-head"><span>{escape(label)}</span>'
          f'<span>{right}</span></div><div class="rc-progress"><div style="width:{pct}%"></div></div></div>')


def empty_state(icon: str, title: str, text: str) -> None:
    _html(f'<div class="rc-empty"><div class="rc-empty-icon">{escape(icon)}</div>'
          f'<h4>{escape(title)}</h4><p>{escape(text)}</p></div>')


def money(amount: float, currency: str) -> str:
    return f"{currency}{amount:,.0f}" if abs(amount) >= 100 else f"{currency}{amount:,.2f}".rstrip("0").rstrip(".")


def number(value: float) -> str:
    return f"{value:,.0f}" if float(value).is_integer() or abs(value) >= 100 else f"{value:,.1f}"


def achievement_cards(items: list[dict]) -> None:
    """items: {"icon", "title", "description", "unlocked": bool, "new": bool, "meta": str, "progress": 0..1}"""
    cards = []
    for a in items:
        state = "unlocked" if a["unlocked"] else "locked"
        new = " new" if a.get("new") else ""
        bar = ""
        if not a["unlocked"] and a.get("progress"):
            bar = f'<div class="rc-progress"><div style="width:{round(100 * a["progress"])}%"></div></div>'
        cards.append(
            f'<div class="rc-ach {state}{new}"><div class="rc-ach-icon">{escape(a["icon"])}</div>'
            f'<div class="rc-ach-title">{escape(a["title"])}</div>'
            f'<div class="rc-ach-desc">{escape(a["description"])}</div>{bar}'
            f'<div class="rc-ach-meta">{escape(a.get("meta") or "")}</div></div>'
        )
    _html(f'<div class="rc-ach-grid">{"".join(cards)}</div>')


def month_calendar(year: int, month: int, marks: dict, today: date, selected: date | None = None) -> None:
    """A read-only month grid. marks: {date: emoji} for days that have an entry."""
    cells = [f'<div class="rc-cal-head">{d}</div>' for d in ("Mo", "Tu", "We", "Th", "Fr", "Sa", "Su")]
    for week in calendar.Calendar(firstweekday=0).monthdayscalendar(year, month):
        for day_num in week:
            if day_num == 0:
                cells.append('<div class="rc-cal-day empty"></div>')
                continue
            d = date(year, month, day_num)
            classes = ["rc-cal-day"]
            if d in marks:
                classes.append("has-entry")
            if d == today:
                classes.append("today")
            if d == selected:
                classes.append("selected")
            emoji = f"<span>{escape(marks[d])}</span>" if d in marks else ""
            cells.append(f'<div class="{" ".join(classes)}">{emoji}{day_num}</div>')
    _html(f'<div class="rc-cal">{"".join(cells)}</div>')

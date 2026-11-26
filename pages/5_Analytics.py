"""Analytics & Insights – trends, patterns and reports built only from your own records."""

from datetime import timedelta

import pandas as pd
import streamlit as st

from components import charts
from components.cards import empty_state, money, number, page_header, section, stat_cards
from components.navigation import addiction_picker, require_context
from services import analytics_service as an
from utils.calculations import change_pct
from utils.constants import ADDICTIONS, ALCOHOL, SMOKING
from utils.datetime_utils import local_today
from utils.insights import build_insights

ctx = require_context()
today = local_today(ctx.tz)
cur = ctx.currency

page_header("Analytics & Insights", "Your patterns, from your own logs – no guesses, no invented numbers.",
            eyebrow="Understand")

# ---------------------------------------------------------------- filters (one row, above everything)
f1, f2 = st.columns([1, 2], vertical_alignment="bottom")
with f1:
    addiction = addiction_picker(ctx, key="analytics_addiction")
meta = ADDICTIONS[addiction]
start_day = an.tracking_start(ctx, addiction)
ranges = {"7": "7 days", "30": "30 days", "90": "90 days", "all": "All time", "custom": "Custom"}
with f2:
    choice = st.segmented_control("Period", list(ranges), default="30", format_func=ranges.get,
                                  key="analytics-range", label_visibility="collapsed") or "30"
if choice == "custom":
    picked = st.date_input("Date range", value=(max(start_day, today - timedelta(days=13)), today),
                           min_value=start_day, max_value=today, key="analytics-custom")
    first, last = (picked[0], picked[1]) if isinstance(picked, tuple) and len(picked) == 2 else (today, today)
elif choice == "all":
    first, last = start_day, today
else:
    first, last = today - timedelta(days=int(choice) - 1), today

try:
    rd = an.load_range(ctx, addiction, first, last)
    m = an.period_metrics(ctx, rd)
    week_now, week_before = an.compare_periods(ctx, addiction, 7)
except Exception:
    st.error("Couldn't load your analytics. Check your connection and try again.")
    st.stop()

if rd.empty:
    empty_state("📊", "No data in this period yet",
                f"Your tracking started on {start_day.strftime('%d %b %Y')}. Log a few hours and entries, then come back.")
    st.stop()

st.caption(f"Showing {rd.first.strftime('%d %b')} – {rd.last.strftime('%d %b %Y')}"
           + (f" · analytics start from your tracking start date ({start_day.strftime('%d %b')})"
              if first < start_day else "") + ". Today counts as a partial day.")


DAY_NAMES = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


def counts(values: list, index_name: str, value_name: str) -> pd.DataFrame:
    """Value counts as a small table; weekdays get their names."""
    table = pd.Series(values, dtype=float).value_counts().sort_index().rename_axis(index_name).reset_index(name=value_name)
    table[index_name] = table[index_name].astype(int)
    if index_name == "weekday":
        table[index_name] = table[index_name].map(lambda w: DAY_NAMES[w])
    return table


def show(fig, data: pd.DataFrame, key: str) -> None:
    """Chart + an accessible table view of exactly the numbers it plots."""
    st.plotly_chart(fig, width="stretch", config={"displayModeBar": False}, key=key)
    with st.expander("View data"):
        st.dataframe(data, hide_index=True, width="stretch")


# ---------------------------------------------------------------- insights
section("Insights", "Each insight shows the numbers it's based on. More logging = sharper insights.")
insights = build_insights(an.insight_input(ctx, rd, m, week_now["tracked_days"], week_before["tracked_days"]))
if insights:
    with st.container(border=True):
        for ins in insights:
            st.markdown(f"{ins.icon} {ins.text}")
else:
    st.caption("Not enough data for reliable insights yet. Insights appear once you've logged at least a few "
               "days, 5+ cravings or 10+ tracked hours in this period.")

# ---------------------------------------------------------------- KPIs
if addiction == SMOKING:
    vs = change_pct(m["avg_per_day"], m["baseline"]) if rd.days >= 1 else None
    stat_cards([
        {"label": "Cigarettes", "value": number(m["quantity"]), "accent": "teal", "sub": f"over {rd.days:.1f} days"},
        {"label": "Per day", "value": f"{m['avg_per_day']:.1f}",
         "sub": f"{abs(vs)}% {'below' if vs <= 0 else 'above'} baseline" if vs is not None else f"baseline {m['baseline']:g}"},
        {"label": "Avoided", "value": number(m["avoided"]), "accent": "green", "sub": "estimate vs. baseline"},
        {"label": "Smoke-free hours", "value": f"{m['free_pct']}%", "accent": "green",
         "sub": f"{m['free_hours']} of {m['tracked_hours']} tracked"},
        {"label": "Saved", "value": money(m["saved"], cur), "accent": "teal", "sub": "estimate"},
    ])
else:
    stat_cards([
        {"label": "Drinks", "value": number(m["quantity"]), "accent": "teal",
         "sub": f"≈ {m['standard_drinks']:.1f} standard drinks"},
        {"label": "Drinking days", "value": m["occasions"], "sub": f"over {rd.days:.1f} days"},
        {"label": "Alcohol-free days", "value": m["free_days"], "accent": "green",
         "sub": f"of {rd.completed_days} completed days"},
        {"label": "Alcohol-free hours", "value": f"{m['free_pct']}%", "accent": "green",
         "sub": f"{m['free_hours']} of {m['tracked_hours']} tracked"},
        {"label": "Spent / saved", "value": money(m["spent"], cur), "accent": "teal",
         "sub": f"saved ≈ {money(m['saved'], cur)}"},
    ])

tabs = st.tabs(["📈 Trends", "🕓 When", "⏱️ Hourly tracking", "🌊 Cravings", "🗒️ Reports"])

# ---------------------------------------------------------------- trends
with tabs[0]:
    daily = an.daily_frame(rd)
    unit = meta["units"]
    section(f"{unit.capitalize()} per day", "The dashed line is your starting baseline.")
    show(charts.daily_bars(daily, m["baseline"], unit), daily.rename(columns={"quantity": unit}), "daily")

    days_span = (rd.last - rd.first).days + 1
    if days_span >= 14:
        weekly = an.period_frame(daily, "quantity", "week")
        section("Weekly totals", "Faded bars are weeks only partly inside the period.")
        show(charts.period_bars(weekly, m["baseline"] * 7, unit, "Week"),
             weekly.rename(columns={"label": "week starting", "value": unit}), "weekly")
    if days_span >= 60:
        monthly = an.period_frame(daily, "quantity", "month")
        section("Monthly totals")
        show(charts.period_bars(monthly, None, unit, "Month"),
             monthly.rename(columns={"label": "month", "value": unit}), "monthly")

    if addiction == SMOKING and m["baseline"]:
        avoided = an.avoided_frame(daily, m["baseline"], today, an.today_fraction(ctx))
        section("Cigarettes avoided", "Running total compared with your baseline.")
        show(charts.cumulative_line(avoided, "cigarettes avoided"),
             avoided.rename(columns={"value": "avoided (running total)"}), "avoided")
    if addiction == ALCOHOL:
        std = an.daily_frame(rd, "standard_drinks")
        section("Standard drinks per day", "Estimates based on serving size and alcohol %.")
        show(charts.daily_bars(std, None, "standard drinks", "standard_drinks"), std, "std")

# ---------------------------------------------------------------- when
with tabs[1]:
    c = rd.consumption
    if c.empty:
        empty_state("🕓", f"No {meta['units']} logged in this period", "That's worth celebrating.")
    else:
        section(f"When you {meta['verb'].lower()}", f"Darker cells = more {meta['units']} at that day and hour.")
        heat = c[["weekday", "hour", "quantity"]].copy()
        show(charts.week_hour_heatmap(heat, "quantity", meta["units"]),
             heat.groupby(["weekday", "hour"], as_index=False)["quantity"].sum()
             .assign(weekday=lambda d: d["weekday"].map(lambda w: DAY_NAMES[w]))
             .rename(columns={"quantity": meta["units"]}), "heatmap")
        h1, h2 = st.columns(2)
        hours = [h for h, q in zip(c["hour"], c["quantity"]) for _ in range(max(1, round(q)))]
        with h1:
            st.markdown("**By hour of day**")
            show(charts.hour_of_day_bars(hours, meta["units"]), counts(hours, "hour", meta["units"]), "by-hour")
        with h2:
            if addiction == ALCOHOL:
                st.markdown("**Drinking days by weekday**")
                days = c.drop_duplicates("local_date")["weekday"].tolist()
                show(charts.weekday_bars(days, "drinking days"), counts(days, "weekday", "days"), "by-weekday")
            else:
                st.markdown("**By weekday**")
                weekdays = [w for w, q in zip(c["weekday"], c["quantity"]) for _ in range(max(1, round(q)))]
                show(charts.weekday_bars(weekdays, meta["units"]), counts(weekdays, "weekday", meta["units"]),
                     "by-weekday")

# ---------------------------------------------------------------- hourly tracking
with tabs[2]:
    per_day = an.status_per_day(rd)
    days_in = (rd.last - rd.first).days + 1
    stat_cards([
        {"label": "Days tracked", "value": f"{m['tracked_days']} / {days_in}", "accent": "teal"},
        {"label": "Hours tracked", "value": m["tracked_hours"],
         "sub": f"{m['tracked_hours'] / m['tracked_days']:.1f} per tracked day" if m["tracked_days"] else None},
        {"label": f"{meta['free']}", "value": f"{m['free_pct']}%", "accent": "green", "sub": "of tracked hours"},
    ])
    if m["tracked_hours"]:
        section("Tracked hours per day", "Untracked hours are simply missing – never counted as failures.")
        show(charts.status_stack(per_day),
             per_day.rename(columns={"success": "free", "craving_resisted": "craving resisted"}), "status")
    else:
        empty_state("⏱️", "No tracked hours in this period", "Log hours in the Hourly Tracker to see them here.")

# ---------------------------------------------------------------- cravings
with tabs[3]:
    cr = rd.cravings
    if cr.empty:
        empty_state("🌊", "No cravings logged in this period", "Use the Craving Manager when one hits.")
    else:
        stat_cards([
            {"label": "Cravings", "value": m["cravings"], "accent": "teal"},
            {"label": "Coped successfully", "value": f"{m['resisted_pct']}%", "accent": "green",
             "sub": f"{m['cravings_resisted']} resisted"},
            {"label": "Average intensity", "value": f"{m['avg_intensity']:g}/10", "accent": "yellow"},
        ])
        k1, k2 = st.columns(2)
        with k1:
            st.markdown("**Cravings by hour of day**")
            show(charts.hour_of_day_bars(cr["hour"].tolist(), "cravings"),
                 counts(cr["hour"].tolist(), "hour", "cravings"), "cr-hour")
        with k2:
            st.markdown("**Cravings by weekday**")
            show(charts.weekday_bars(cr["weekday"].tolist(), "cravings"),
                 counts(cr["weekday"].tolist(), "weekday", "cravings"), "cr-weekday")
        triggers = [t for t in cr.get("trigger", pd.Series(dtype=object)).tolist() if t]
        if triggers:
            top = pd.Series(triggers).value_counts()
            section("Most common triggers")
            show(charts.trigger_bars(list(top.head(6).items())),
                 top.rename_axis("trigger").reset_index(name="cravings"), "cr-triggers")
        if "coping_strategy" in cr and cr["coping_strategy"].notna().any():
            section("What helps", "How often you resisted a craving when you used each strategy.")
            coping = (cr.dropna(subset=["coping_strategy"]).groupby("coping_strategy")["resisted"]
                      .agg(["count", "sum"]).reset_index())
            coping["resisted %"] = (100 * coping["sum"] / coping["count"]).round().astype(int)
            st.dataframe(coping.rename(columns={"coping_strategy": "strategy", "count": "times used",
                                                "sum": "resisted"}).sort_values("resisted %", ascending=False),
                         hide_index=True, width="stretch")

# ---------------------------------------------------------------- reports
with tabs[4]:
    kind = st.segmented_control("Report", ["week", "month"], default="week", key="report-kind",
                                format_func=lambda k: "Weekly (last 7 days)" if k == "week" else "Monthly (last 30 days)",
                                label_visibility="collapsed") or "week"
    now_m, before_m = (week_now, week_before) if kind == "week" else an.compare_periods(ctx, addiction, 30)
    label_now, label_before = ("Last 7 days", "7 days before") if kind == "week" else ("Last 30 days", "30 days before")

    # (metric label, key, lower is better?, formatter)
    rows = [
        (f"{meta['units'].capitalize()} per day", "avg_per_day", True, lambda v: f"{v:.1f}"),
        (f"Total {meta['units']}", "quantity", True, number),
        ("Hours tracked", "tracked_hours", False, lambda v: f"{v:g}"),
        (f"{meta['free']} share of tracked hours", "free_pct", False, lambda v: f"{v}%"),
        ("Cravings resisted", "cravings_resisted", False, lambda v: f"{v:g}"),
        ("Estimated saved", "saved", False, lambda v: money(v, cur)),
    ]
    if addiction == ALCOHOL:
        rows.insert(2, ("Standard drinks", "standard_drinks", True, lambda v: f"{v:.1f}"))
        rows.insert(3, ("Alcohol-free days", "free_days", False, lambda v: f"{v:g}"))

    has_before = before_m["days"] > 0
    table = []
    for label, key, lower_better, fmt in rows:
        change = "—"
        if has_before:
            pct = change_pct(now_m[key], before_m[key])
            if pct is not None and pct != 0:
                better = (pct < 0) == lower_better
                change = f"{'▼' if pct < 0 else '▲'} {abs(pct)}% · {'better' if better else 'harder period'}"
            elif pct == 0:
                change = "no change"
        table.append({"Metric": label, label_now: fmt(now_m[key]),
                      label_before: fmt(before_m[key]) if has_before else "—", "Change": change})
    st.dataframe(pd.DataFrame(table), hide_index=True, width="stretch")
    if not has_before:
        st.caption(f"The comparison period is before you started tracking ({start_day.strftime('%d %b')}), "
                   "so there's nothing to compare against yet.")
    else:
        st.caption("Totals for the current period include today so far; per-day figures adjust for that.")

    # A short plain-language summary, built only from the numbers above
    lines = []
    if has_before and before_m["avg_per_day"] > 0:
        pct = change_pct(now_m["avg_per_day"], before_m["avg_per_day"])
        if pct is not None and pct < 0:
            lines.append(f"You cut your {meta['units']} per day by {abs(pct)}% compared with the period before. 🎉")
        elif pct is not None and pct > 0:
            lines.append(f"This was a harder {kind} – {meta['units']} per day rose by {pct}%. "
                         "One tough stretch doesn't erase your progress.")
    if now_m["cravings"]:
        lines.append(f"You resisted {now_m['cravings_resisted']} of {now_m['cravings']} cravings "
                     f"({now_m['resisted_pct']}%).")
    if now_m["tracked_hours"]:
        lines.append(f"{now_m['free_pct']}% of your {now_m['tracked_hours']} tracked hours were "
                     f"{meta['free'].lower()}.")
    if lines:
        with st.container(border=True):
            st.markdown(f"**Your {'weekly' if kind == 'week' else 'monthly'} summary**")
            for line in lines:
                st.markdown(f"- {line}")

"""Plotly charts for Reclaim.

Colours were checked with the data-viz palette validator for BOTH themes
(lightness band, chroma, colour-blind separation, contrast). Each theme gets
its own selected steps – dark mode is not an automatic inversion.

Conventions: one hue for a single series; status colours (free / craving
resisted / consumed) only where they mean exactly that; thin bars with 4px
rounded ends; solid hairline grid; hover tooltips on every mark; no dual axes.
"""

from datetime import date

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from utils.insights import WEEKDAYS

PALETTE = {
    "light": {
        "series": "#1a9488", "surface": "#f7f9f8", "grid": "rgba(26,38,51,0.10)", "ref": "#6b7280",
        "free": "#2e9e74", "craving": "#c99a2e", "consumed": "#c95454",
        "heat": ["#e7f2f0", "#a9d8d1", "#5fb6ab", "#1a9488", "#0d5f57"],
    },
    "dark": {
        "series": "#1fa898", "surface": "#0e1621", "grid": "rgba(228,234,240,0.10)", "ref": "#9aa4af",
        "free": "#2e9e74", "craving": "#b8891c", "consumed": "#e0607a",
        "heat": ["#16232c", "#17423d", "#1a6b62", "#1fa898", "#7fd9cc"],
    },
}
ASSUMED_PLOT_WIDTH = 700  # px – used to keep bars at most ~24px thick


def colors() -> dict:
    theme = getattr(getattr(st.context, "theme", None), "type", None)
    return PALETTE["light" if theme == "light" else "dark"]


def _bargap(n: int) -> float:
    """Leave air around bars so a handful of bars never become thick blocks."""
    slot = ASSUMED_PLOT_WIDTH / max(n, 1)
    return min(0.85, max(0.15, 1 - 24 / slot))


def _layout(fig: go.Figure, height: int = 260, n_bars: int | None = None) -> go.Figure:
    c = colors()
    fig.update_layout(
        height=height,
        margin=dict(l=8, r=8, t=16, b=8),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        showlegend=False,
        bargap=_bargap(n_bars) if n_bars else 0.35,
        barcornerradius=4,
        hoverlabel=dict(font_size=13),
    )
    fig.update_xaxes(showgrid=False, linecolor=c["grid"], ticks="", automargin=True)
    fig.update_yaxes(gridcolor=c["grid"], gridwidth=1, zeroline=False, rangemode="tozero", automargin=True)
    return fig


def _reference_line(fig: go.Figure, y: float, label: str) -> None:
    """A threshold line (dashed on purpose – it marks a reference value, not a gridline)."""
    fig.add_hline(y=y, line_dash="dash", line_width=1.5, line_color=colors()["ref"],
                  annotation_text=label, annotation_position="top left", annotation_font_size=11)


# ---------------------------------------------------------------------------
# Single-series bars
# ---------------------------------------------------------------------------

def daily_bars(series: pd.DataFrame, baseline: float | None, unit_label: str, value_col: str = "quantity") -> go.Figure:
    """Amount per day, with the user's original baseline as a reference line."""
    fig = go.Figure(go.Bar(
        x=pd.to_datetime(series["date"]), y=series[value_col], marker_color=colors()["series"],
        marker_line_width=0, hovertemplate=f"%{{x|%a %d %b}}<br>%{{y:.3g}} {unit_label}<extra></extra>",
    ))
    if baseline:
        _reference_line(fig, baseline, f"Your baseline ({baseline:.3g}/day)")
    _layout(fig, n_bars=len(series))
    fig.update_xaxes(tickformat="%d %b" if len(series) > 14 else "%a %d")
    return fig


def period_bars(periods: pd.DataFrame, baseline: float | None, unit_label: str, period_name: str) -> go.Figure:
    """Weekly or monthly totals. periods: columns label, value, partial (bool)."""
    c = colors()
    fig = go.Figure(go.Bar(
        x=periods["label"], y=periods["value"], marker_color=c["series"], marker_line_width=0,
        marker_opacity=[0.55 if p else 1 for p in periods["partial"]],
        customdata=[" (so far)" if p else "" for p in periods["partial"]],
        hovertemplate=f"{period_name} of %{{x}}%{{customdata}}<br>%{{y:.3g}} {unit_label}<extra></extra>",
    ))
    if baseline:
        _reference_line(fig, baseline, f"Baseline ({baseline:.3g} per {period_name.lower()})")
    return _layout(fig, n_bars=len(periods))


def hour_of_day_bars(hours: list[int], unit_label: str) -> go.Figure:
    counts = pd.Series(hours).value_counts().reindex(range(24), fill_value=0) if hours else pd.Series([0] * 24)
    labels = [f"{h % 12 or 12}{'a' if h < 12 else 'p'}" for h in range(24)]
    fig = go.Figure(go.Bar(
        x=labels, y=counts.values, marker_color=colors()["series"], marker_line_width=0,
        hovertemplate=f"%{{x}}: %{{y}} {unit_label}<extra></extra>",
    ))
    _layout(fig, height=230, n_bars=24)
    fig.update_xaxes(tickvals=labels[::3])
    fig.update_yaxes(tickformat="d")
    return fig


def weekday_bars(weekdays: list[int], unit_label: str) -> go.Figure:
    counts = pd.Series(weekdays).value_counts().reindex(range(7), fill_value=0) if weekdays else pd.Series([0] * 7)
    fig = go.Figure(go.Bar(
        x=[d[:3] for d in WEEKDAYS], y=counts.values, marker_color=colors()["series"], marker_line_width=0,
        hovertemplate=f"%{{x}}: %{{y}} {unit_label}<extra></extra>",
    ))
    _layout(fig, height=230, n_bars=7)
    fig.update_yaxes(tickformat="d")
    return fig


def trigger_bars(top_triggers: list[tuple[str, int]]) -> go.Figure:
    """Horizontal bars of craving triggers, most common at the top."""
    labels = [t for t, _ in top_triggers][::-1]
    counts = [n for _, n in top_triggers][::-1]
    fig = go.Figure(go.Bar(
        x=counts, y=labels, orientation="h", marker_color=colors()["series"], marker_line_width=0,
        hovertemplate="%{y}: %{x} craving(s)<extra></extra>",
    ))
    _layout(fig, height=max(180, 38 * len(labels) + 40))
    fig.update_layout(bargap=0.45)
    fig.update_xaxes(tickformat="d", showgrid=True, gridcolor=colors()["grid"], rangemode="tozero")
    fig.update_yaxes(showgrid=False)
    return fig


# ---------------------------------------------------------------------------
# Status stack, heatmap, cumulative line
# ---------------------------------------------------------------------------

def status_stack(per_day: pd.DataFrame) -> go.Figure:
    """Tracked hours per day split by status. per_day: date, success, craving_resisted, consumed."""
    c = colors()
    fig = go.Figure()
    for col, name, color in [("success", "Free", c["free"]), ("craving_resisted", "Craving resisted", c["craving"]),
                             ("consumed", "Consumed", c["consumed"])]:
        fig.add_bar(x=pd.to_datetime(per_day["date"]), y=per_day[col], name=name, marker_color=color,
                    marker_line_color=c["surface"], marker_line_width=1,  # 2px surface gap between segments
                    hovertemplate=f"{name}: %{{y}} h<extra></extra>")
    _layout(fig, height=280, n_bars=len(per_day))
    fig.update_layout(barmode="stack", showlegend=True, hovermode="x unified",
                      legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0, title_text=""))
    fig.update_xaxes(tickformat="%d %b" if len(per_day) > 14 else "%a %d")
    fig.update_yaxes(tickformat="d", title_text="hours")
    return fig


def week_hour_heatmap(df: pd.DataFrame, value_col: str, unit_label: str) -> go.Figure:
    """Weekday × hour-of-day heatmap (one hue, light→dark = less→more)."""
    c = colors()
    grid = (df.pivot_table(index="weekday", columns="hour", values=value_col, aggfunc="sum")
            .reindex(index=range(7), columns=range(24)).fillna(0))
    hour_labels = [f"{h % 12 or 12}{'a' if h < 12 else 'p'}" for h in range(24)]
    steps = c["heat"]
    scale = [[i / (len(steps) - 1), color] for i, color in enumerate(steps)]
    fig = go.Figure(go.Heatmap(
        z=grid.values, x=hour_labels, y=[d[:3] for d in WEEKDAYS], colorscale=scale, zmin=0,
        xgap=2, ygap=2,  # surface gap between cells
        colorbar=dict(thickness=10, len=0.9, outlinewidth=0, tickformat="d", title=dict(text=unit_label, side="right")),
        hovertemplate=f"%{{y}} %{{x}}: %{{z:.3g}} {unit_label}<extra></extra>",
    ))
    _layout(fig, height=290)
    fig.update_yaxes(autorange="reversed", showgrid=False)
    fig.update_xaxes(tickvals=hour_labels[::3])
    return fig


def cumulative_line(series: pd.DataFrame, unit_label: str) -> go.Figure:
    """Running total (e.g. cigarettes avoided) – 2px line with a light wash."""
    c = colors()
    x = pd.to_datetime(series["date"])
    fig = go.Figure(go.Scatter(
        x=x, y=series["value"], mode="lines", line=dict(color=c["series"], width=2, shape="linear"),
        fill="tozeroy", fillcolor=_wash(c["series"]),
        hovertemplate=f"%{{x|%a %d %b}}<br>%{{y:,.0f}} {unit_label}<extra></extra>",
    ))
    if len(series):  # end-dot with a surface ring, labelled with the latest value
        fig.add_scatter(x=[x.iloc[-1]], y=[series["value"].iloc[-1]], mode="markers+text",
                        marker=dict(size=9, color=c["series"], line=dict(color=c["surface"], width=2)),
                        text=[f"{series['value'].iloc[-1]:,.0f}"], textposition="top left", hoverinfo="skip")
    _layout(fig, height=250)
    fig.update_layout(hovermode="x", margin=dict(t=30))
    return fig


def _wash(hex_color: str, alpha: float = 0.10) -> str:
    h = hex_color.lstrip("#")
    r, g, b = (int(h[i:i + 2], 16) for i in (0, 2, 4))
    return f"rgba({r},{g},{b},{alpha})"


def week_label(d: date) -> str:
    return d.strftime("%d %b")

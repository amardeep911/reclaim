"""Plotly charts styled to sit on either the light or dark theme."""

import pandas as pd
import plotly.graph_objects as go

TEAL = "#4fb3a9"
MUTED = "rgba(127,140,155,0.55)"


def _layout(fig: go.Figure, height: int = 260) -> go.Figure:
    fig.update_layout(
        height=height,
        margin=dict(l=8, r=8, t=16, b=8),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        showlegend=False,
        bargap=0.35,
        hoverlabel=dict(font_size=13),
    )
    fig.update_xaxes(showgrid=False, tickformat="%a %d")
    fig.update_yaxes(gridcolor="rgba(127,140,155,0.18)", zeroline=False, rangemode="tozero")
    return fig


def daily_bars(series: pd.DataFrame, baseline: float | None, unit_label: str) -> go.Figure:
    """Bars of quantity per day, with the user's original baseline as a dashed reference line."""
    fig = go.Figure(go.Bar(
        x=pd.to_datetime(series["date"]), y=series["quantity"], marker_color=TEAL,
        marker_line_width=0, hovertemplate=f"%{{x|%a %d %b}}<br>%{{y:g}} {unit_label}<extra></extra>",
    ))
    if baseline:
        fig.add_hline(y=baseline, line_dash="dash", line_color=MUTED,
                      annotation_text=f"Your baseline ({baseline:g}/day)", annotation_position="top left",
                      annotation_font_size=11)
    return _layout(fig)


def trigger_bars(top_triggers: list[tuple[str, int]]) -> go.Figure:
    """Horizontal bars of craving triggers, most common at the top."""
    labels = [t for t, _ in top_triggers][::-1]
    counts = [c for _, c in top_triggers][::-1]
    fig = go.Figure(go.Bar(
        x=counts, y=labels, orientation="h", marker_color=TEAL, marker_line_width=0,
        hovertemplate="%{y}: %{x} craving(s)<extra></extra>",
    ))
    _layout(fig, height=max(180, 38 * len(labels) + 40))
    fig.update_xaxes(tickformat="d", showgrid=True, gridcolor="rgba(127,140,155,0.18)", rangemode="tozero")
    fig.update_yaxes(showgrid=False)
    return fig

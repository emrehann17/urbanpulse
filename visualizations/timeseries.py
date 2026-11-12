"""Member 1: aligned demand and closed-only duration panels."""

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots


def create_visualization(chart_df: pd.DataFrame, *, rolling: bool = True) -> go.Figure:
    """Render daily_data's complete calendar, median, counts and rolling columns.

    The median belongs to the creation-day cohort, not the day it closed.
    Missing duration days remain gaps. Input is never changed.
    """
    fig = make_subplots(
        rows=2,
        cols=1,
        shared_xaxes=True,
        vertical_spacing=0.19,
        subplot_titles=(
            "Exact daily request volume",
            "Median closure time · completed requests only",
        ),
    )
    fig.add_trace(
        go.Scatter(
            x=chart_df.created_day,
            y=chart_df.requests,
            name="Daily requests",
            mode="lines",
            line=dict(color="#0072B2", width=1.6),
            hovertemplate="%{x|%b %d, %Y}<br>Requests: %{y:,}<extra></extra>",
        ),
        row=1,
        col=1,
    )
    fig.add_trace(
        go.Scatter(
            x=chart_df.created_day,
            y=chart_df.closure_median_hours / 24,
            name="Daily closure median",
            mode="lines",
            connectgaps=False,
            line=dict(color="#D55E00", width=1.6),
            customdata=chart_df[["valid_closures", "requests"]],
            hovertemplate=(
                "%{x|%b %d, %Y}<br>Median: %{y:.2f} days<br>Valid closures: %{customdata[0]:,}"
                "<br>All requests: %{customdata[1]:,}<extra></extra>"
            ),
        ),
        row=2,
        col=1,
    )
    if rolling:
        window = chart_df.attrs["rolling_days"]
        fig.add_trace(
            go.Scatter(
                x=chart_df.created_day,
                y=chart_df.request_trend,
                name=f"{window}-day mean count",
                line=dict(color="#243247", width=2.5, dash="dash"),
            ),
            row=1,
            col=1,
        )
        fig.add_trace(
            go.Scatter(
                x=chart_df.created_day,
                y=chart_df.closure_trend_hours / 24,
                name=f"{window}-day median of medians",
                connectgaps=False,
                customdata=chart_df[["trend_valid_days"]],
                hovertemplate=(
                    "%{x|%b %d, %Y}<br>Trend: %{y:.2f} days"
                    "<br>Contributing days: %{customdata[0]:.0f}<extra></extra>"
                ),
                line=dict(color="#243247", width=2.5, dash="dash"),
            ),
            row=2,
            col=1,
        )
    fig.update_layout(
        title=dict(
            text="Daily demand and closure time · 2025 creation cohorts", font=dict(size=20), y=0.98
        ),
        template="plotly_white",
        autosize=True,
        height=890,
        font=dict(family="Arial, sans-serif", size=14, color="#243247"),
        hoverlabel=dict(font_size=14, bgcolor="white"),
        hovermode="x unified",
        hoversubplots="axis",
        legend=dict(
            orientation="h",
            x=0,
            y=1.10,
            yanchor="bottom",
            entrywidth=0.48,
            entrywidthmode="fraction",
            font=dict(size=13),
        ),
        margin=dict(l=80, r=30, t=175, b=130),
    )
    fig.update_annotations(font_size=15)
    fig.update_yaxes(title_text="Requests", rangemode="tozero", row=1, col=1)
    fig.update_yaxes(title_text="Elapsed days", rangemode="tozero", row=2, col=1)
    fig.update_xaxes(type="date", tickformat="%b %d", nticks=7)
    fig.update_xaxes(
        title=dict(text="Created date · New York calendar (both panels)", standoff=15),
        rangeslider=dict(
            visible=True, thickness=0.055, bgcolor="#f1f5f9", bordercolor="#d7dee8", borderwidth=1
        ),
        row=2,
        col=1,
    )
    if chart_df.empty or not chart_df.requests.any():
        fig.add_annotation(
            text="No requests in the selected calendar range",
            showarrow=False,
            x=0.5,
            y=0.76,
            xref="paper",
            yref="paper",
        )
    return fig

"""Member 1: borough Kaplan–Meier curves and pointwise uncertainty."""

import pandas as pd
import plotly.graph_objects as go

DASHES = ["solid", "dash", "dot", "dashdot", "longdash"]
COLORS = ["#0072B2", "#D55E00", "#009E73", "#CC79A7", "#000000"]


def cohort_summary(outcomes: pd.DataFrame) -> pd.DataFrame:
    """Return a compact presentation table; retain exact cohort denominators."""
    frame = outcomes[["borough", "requests", "closed", "censored", "unknown_outcomes"]].copy()
    frame.insert(2, "valid_observations", frame.closed + frame.censored)
    return frame.rename(
        columns={
            "borough": "Borough",
            "requests": "Requests",
            "valid_observations": "Valid observations",
            "closed": "Closures",
            "censored": "Censored",
            "unknown_outcomes": "Unknown outcomes",
        }
    )


def create_visualization(
    chart_df: pd.DataFrame, *, outcomes: pd.DataFrame, confidence: bool = True
) -> go.Figure:
    """Render KM_COLUMNS from survival_data with its per-borough outcome table.

    hours are elapsed hours, survival/lower/upper are probabilities. Outcome
    columns: borough, requests, closed, censored, unknown_outcomes. No raw rows.
    """
    fig = go.Figure()
    for color, dash, (borough, group) in zip(
        COLORS, DASHES, chart_df.groupby("borough", sort=True), strict=False
    ):
        x = group.hours / 24
        if confidence:
            fig.add_trace(
                go.Scatter(
                    x=x,
                    y=group.lower,
                    mode="lines",
                    line=dict(width=0, shape="hv"),
                    showlegend=False,
                    hoverinfo="skip",
                    legendgroup=borough,
                )
            )
            rgb = tuple(int(color[i : i + 2], 16) for i in (1, 3, 5))
            fig.add_trace(
                go.Scatter(
                    x=x,
                    y=group.upper,
                    mode="lines",
                    line=dict(width=0, shape="hv"),
                    fill="tonexty",
                    fillcolor=f"rgba{(*rgb, 0.12)}",
                    showlegend=False,
                    hoverinfo="skip",
                    legendgroup=borough,
                )
            )
        fig.add_trace(
            go.Scatter(
                x=x,
                y=group.survival,
                name=borough,
                mode="lines",
                legendgroup=borough,
                line=dict(color=color, dash=dash, shape="hv", width=2.5),
                customdata=group[["at_risk", "events", "censored", "lower", "upper"]],
                hovertemplate=(
                    "<b>%{fullData.name}</b><br>Elapsed time: %{x:.2f} days"
                    "<br>Still administratively unclosed: %{y:.2%}"
                    "<br>At risk before time: %{customdata[0]:,}"
                    "<br>Closures at time: %{customdata[1]:,}"
                    "<br>Censored at time: %{customdata[2]:,}"
                    "<br>95% pointwise CI: %{customdata[3]:.2%}–%{customdata[4]:.2%}"
                    "<extra></extra>"
                ),
            )
        )
    full_days = max(1.0, float(chart_df.hours.max()) / 24) if not chart_df.empty else 1.0
    buttons = [
        dict(
            label=label,
            method="relayout",
            args=[{"xaxis.range": [0, days], "xaxis.autorange": False}],
        )
        for label, days in [
            ("First 7 days", 7),
            ("First 30 days", 30),
            ("First 90 days", 90),
            ("Full observed period", full_days),
        ]
    ]
    fig.update_layout(
        title=dict(
            text="Time to recorded administrative closure", x=0.02, y=0.98, font=dict(size=20)
        ),
        template="plotly_white",
        autosize=True,
        height=660,
        font=dict(family="Arial, sans-serif", size=14, color="#243247"),
        hoverlabel=dict(font_size=14, bgcolor="white"),
        hovermode="closest",
        xaxis=dict(
            title="Elapsed days since request creation",
            range=[0, 30],
            autorange=False,
            tickformat=",.0f",
            zeroline=False,
        ),
        yaxis=dict(title="Probability still unclosed", range=[0, 1.02], tickformat=".0%"),
        legend=dict(
            orientation="h",
            x=0,
            y=1.03,
            yanchor="bottom",
            groupclick="togglegroup",
            font=dict(size=13),
        ),
        updatemenus=[
            dict(
                type="buttons",
                direction="right",
                active=1,
                buttons=buttons,
                x=0,
                xanchor="left",
                y=1.19,
                yanchor="bottom",
                font=dict(size=12),
                bgcolor="#f1f5f9",
                bordercolor="#d7dee8",
            )
        ],
        margin=dict(l=75, r=25, t=160, b=75),
        meta=dict(cohort_summary=cohort_summary(outcomes).to_dict("records")),
    )
    if chart_df.empty:
        fig.add_annotation(
            text="No valid closure or censoring observations",
            showarrow=False,
            x=0.5,
            y=0.5,
            xref="paper",
            yref="paper",
        )
    return fig

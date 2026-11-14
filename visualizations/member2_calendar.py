"""Member 2 calendar heatmap from exact, shared-filter daily request counts."""

import pandas as pd
import plotly.graph_objects as go

REQUIRED_COLUMNS = {"created_day", "requests"}
WEEKDAYS = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")


def create_visualization(daily: pd.DataFrame, *, subtitle: str | None = None) -> go.Figure:
    """Render complete daily aggregates; null creation dates stay in the note, not a cell."""
    missing = REQUIRED_COLUMNS - set(daily.columns)
    if missing:
        raise ValueError(f"Missing required calendar columns: {', '.join(sorted(missing))}")
    if daily.created_day.isna().any() or daily.created_day.duplicated().any():
        raise ValueError("created_day must contain one non-null row per calendar date")
    dates = pd.to_datetime(daily.created_day, errors="coerce")
    counts = pd.to_numeric(daily.requests, errors="coerce")
    if dates.isna().any() or counts.isna().any() or (counts < 0).any():
        raise ValueError("Calendar dates and request counts must be valid and non-negative")

    fig = go.Figure()
    if daily.empty:
        fig.add_annotation(text="No dates fall within the selected 2025 period.", showarrow=False)
        fig.update_layout(title="Calendar heatmap", template="plotly_white", height=260)
        return fig

    start = pd.Timestamp("2025-01-01")
    stop = pd.Timestamp("2025-12-31")
    if ((dates < start) | (dates > stop)).any():
        raise ValueError("created_day values must fall within calendar year 2025")
    day_offsets = (dates - start).dt.days
    columns = (day_offsets + start.weekday()) // 7
    z = [[None] * 53 for _ in WEEKDAYS]
    custom = [[None] * 53 for _ in WEEKDAYS]
    for day, week, count in zip(dates, columns, counts, strict=True):
        weekday, week = day.weekday(), int(week)
        z[weekday][week] = int(count)
        date_label = day.strftime("%a, %b %d, %Y").replace(" 0", " ")
        custom[weekday][week] = [date_label, int(count)]

    fig.add_trace(
        go.Heatmap(
            z=z,
            x=list(range(53)),
            y=list(WEEKDAYS),
            customdata=custom,
            colorscale=[[0, "#f1f5f9"], [0.25, "#b6e3d2"], [0.55, "#52b788"], [1, "#14532d"]],
            colorbar={"title": "Requests", "thickness": 14},
            hovertemplate="%{customdata[0]}<br>Requests: %{customdata[1]:,}<extra></extra>",
            xgap=3,
            ygap=3,
            meta={"kind": "daily_request_counts"},
        )
    )
    month_ticks = []
    month_labels = []
    for month in pd.date_range(start, stop, freq="MS"):
        month_ticks.append(int((month - start).days + start.weekday()) // 7)
        month_labels.append(month.strftime("%b"))
    unknown = int(daily.attrs.get("unknown_created_day", 0))
    scope = f"<br><sup>{subtitle}</sup>" if subtitle else ""
    fig.update_layout(
        title=f"Calendar heatmap · daily service requests{scope}",
        template="plotly_white",
        height=310,
        margin={"l": 60, "r": 30, "t": 85, "b": 35},
        xaxis={
            "tickmode": "array",
            "tickvals": month_ticks,
            "ticktext": month_labels,
            "side": "top",
            "range": [-0.6, 52.6],
            "fixedrange": True,
        },
        yaxis={"autorange": "reversed", "fixedrange": True},
        meta={"population": int(counts.sum()), "unknown_created_day": unknown},
        annotations=(
            [
                {
                    "text": (
                        f"{unknown:,} requests with unknown creation day are "
                        "excluded from the calendar."
                    ),
                    "xref": "paper",
                    "yref": "paper",
                    "x": 0,
                    "y": -0.17,
                    "showarrow": False,
                    "xanchor": "left",
                    "font": {"size": 11, "color": "#64748b"},
                }
            ]
            if unknown
            else []
        ),
    )
    return fig

"""Member 2 ridgeline density from exact complaint-type × closure-hour frequencies."""

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from scipy.stats import gaussian_kde

REQUIRED_COLUMNS = {"complaint_type", "closure_hours", "requests"}


def create_visualization(
    frequencies: pd.DataFrame, *, subtitle: str | None = None, max_types: int = 6
) -> go.Figure:
    """Plot weighted KDEs of exact duration frequencies; show all selected-cohort tails."""
    missing = REQUIRED_COLUMNS - set(frequencies.columns)
    if missing:
        raise ValueError(f"Missing required ridgeline columns: {', '.join(sorted(missing))}")
    if isinstance(max_types, bool) or not isinstance(max_types, int) or max_types < 1:
        raise ValueError("max_types must be a positive integer")
    counts = pd.to_numeric(frequencies.requests, errors="coerce")
    durations = pd.to_numeric(frequencies.closure_hours, errors="coerce")
    if counts.isna().any() or (counts < 0).any():
        raise ValueError("requests must contain non-negative numeric counts")
    if (durations.dropna() < 0).any():
        raise ValueError("closure_hours must be non-negative")

    data = frequencies.assign(requests=counts, closure_hours=durations)
    data = data.dropna(subset=["complaint_type", "closure_hours"])
    data = data.loc[data.requests > 0]
    data = data.groupby(
        ["complaint_type", "closure_hours"], as_index=False, sort=False
    ).requests.sum()
    support = (
        data.groupby("complaint_type").requests.sum().sort_values(ascending=False, kind="stable")
    )
    types = support.head(max_types).index.tolist()
    data = data.loc[data.complaint_type.isin(types)]
    fig = go.Figure()
    if data.empty:
        fig.add_annotation(text="No completed requests match the shared filters.", showarrow=False)
        fig.update_layout(title="Closure duration ridgeline", template="plotly_white", height=300)
        return fig

    values_all = data.closure_hours.to_numpy(dtype=float)
    weights_all = data.requests.to_numpy(dtype=float)
    # The 98th percentile is weighted by exact grouped counts, with no request sampling.
    order = np.argsort(values_all)
    cumulative = np.cumsum(weights_all[order])
    upper = float(
        values_all[order[np.searchsorted(cumulative, 0.98 * cumulative[-1], side="left")]]
    )
    upper = max(upper, 1e-6)
    grid = np.linspace(0, upper, 320)
    row_height = 1.25
    for index, complaint in enumerate(types):
        group = data.loc[data.complaint_type == complaint]
        values = group.closure_hours.to_numpy(dtype=float)
        weights = group.requests.to_numpy(dtype=float)
        if len(values) > 1 and np.ptp(values) > 0:
            density = gaussian_kde(values, weights=weights)(grid)
        else:
            center = float(values[0])
            bandwidth = max(0.1, upper / 100)
            density = np.exp(-0.5 * ((grid - center) / bandwidth) ** 2) / (
                bandwidth * np.sqrt(2 * np.pi)
            )
        density = density / density.max() * row_height
        baseline = float(len(types) - index - 1) * 1.6
        fill_x = np.concatenate((grid, grid[::-1]))
        fill_y = np.concatenate((np.full_like(grid, baseline), baseline + density[::-1]))
        fig.add_trace(
            go.Scatter(
                x=fill_x,
                y=fill_y,
                mode="lines",
                fill="toself",
                name=str(complaint),
                line={"color": "#2563eb", "width": 1.2},
                fillcolor=f"rgba(37,99,235,{0.18 + 0.09 * (index % 4):.2f})",
                customdata=np.concatenate((density, density[::-1])),
                hovertemplate=(
                    "Duration: %{x:.2f} hours<br>Relative density: %{customdata:.3f}<extra></extra>"
                ),
                meta={
                    "kind": "weighted_density",
                    "complaint_type": str(complaint),
                    "valid_closures": int(weights.sum()),
                },
            )
        )
        fig.add_annotation(
            x=upper * 1.01,
            y=baseline + 0.12,
            text=str(complaint),
            showarrow=False,
            xanchor="left",
            align="left",
            font={"size": 11, "color": "#243247"},
        )
    excluded = int(data.loc[data.closure_hours > upper, "requests"].sum())
    total = int(data.requests.sum())
    scope = f"<br><sup>{subtitle}</sup>" if subtitle else ""
    fig.update_layout(
        title=f"Closure duration by complaint type · weighted density{scope}",
        template="plotly_white",
        height=max(420, 100 + 82 * len(types)),
        margin={"l": 65, "r": 250, "t": 90, "b": 65},
        xaxis={
            "title": "Completed closure duration (hours)",
            "range": [0, upper * 1.04],
            "gridcolor": "#e2e8f0",
            "zeroline": False,
        },
        yaxis={"visible": False, "range": [-0.35, len(types) * 1.6]},
        showlegend=False,
        meta={
            "plotted_complaint_types": [str(value) for value in types],
            "valid_closures": total,
            "requests_above_98th_percentile": excluded,
            "display_limit_hours": upper,
        },
        annotations=[
            *fig.layout.annotations,
            {
                "text": (
                    f"Top {len(types)} types by valid closures; {excluded:,} of "
                    f"{total:,} plotted-cohort closures lie above the shared "
                    "weighted 98th-percentile x-axis limit."
                ),
                "xref": "paper",
                "yref": "paper",
                "x": 0,
                "y": -0.2,
                "showarrow": False,
                "xanchor": "left",
                "font": {"size": 10, "color": "#64748b"},
            },
        ],
    )
    return fig

"""Member 3: complaint type and agency request-volume heatmap."""

import pandas as pd
import plotly.graph_objects as go


def create_visualization(
    aggregates: pd.DataFrame,
    subtitle: str | None = None,
) -> go.Figure:
    """Render a heatmap without modifying the aggregate input."""

    required = {"agency", "complaint_type", "requests"}

    if not required.issubset(aggregates.columns):
        raise ValueError("Missing required aggregate columns.")

    fig = go.Figure()

    data = aggregates.dropna(subset=["agency", "complaint_type"]).copy()

    if data.empty:
        fig.add_annotation(
            text="No matching requests to display.",
            showarrow=False,
        )
        return fig

    agencies = data.groupby("agency")["requests"].sum().nlargest(8).index.tolist()

    complaints = data.groupby("complaint_type")["requests"].sum().nlargest(12).index.tolist()

    selected = data[data["agency"].isin(agencies) & data["complaint_type"].isin(complaints)]

    matrix = selected.pivot_table(
        index="complaint_type",
        columns="agency",
        values="requests",
        aggfunc="sum",
        fill_value=0,
    ).reindex(
        index=complaints,
        columns=agencies,
        fill_value=0,
    )

    # Calculate coverage
    shown_count = int(matrix.to_numpy().sum())
    total_count = int(aggregates["requests"].sum())

    shown_pct = 100 * shown_count / total_count if total_count else 0.0

    # Create heatmap
    fig.add_trace(
        go.Heatmap(
            x=agencies,
            y=complaints,
            z=matrix.to_numpy(dtype=int),
            colorscale="Blues",
            colorbar={"title": "Requests"},
            hovertemplate=(
                "<b>Agency:</b> %{x}<br>"
                "<b>Complaint:</b> %{y}<br>"
                "<b>Requests:</b> %{z:,}"
                "<extra></extra>"
            ),
        )
    )

    # Optional dataset and date information
    scope_text = f"<br><sup>{subtitle}</sup>" if subtitle else ""

    # Configure layout
    fig.update_layout(
        title=(
            "Request volume by agency and complaint type"
            f"{scope_text}"
            "<br><sup>Top 8 agencies × top 12 complaint types</sup>"
            "<br><sup>"
            f"Showing {shown_count:,} of {total_count:,} "
            f"filtered requests ({shown_pct:.1f}%)"
            "</sup>"
        ),
        xaxis_title="Agency (top 8)",
        yaxis_title="Complaint type (top 12)",
        height=750,
        margin={
            "l": 160,
            "r": 40,
            "t": 120,
            "b": 90,
        },
    )

    return fig

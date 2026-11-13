"""Member 3: bipartite agency and complaint-type request network."""

import numpy as np
import pandas as pd
import plotly.graph_objects as go

REQUIRED_COLUMNS = {"agency", "complaint_type", "requests"}
AGENCY_COLOR = "#0072B2"
COMPLAINT_COLOR = "#D55E00"
EDGE_COLOR = "rgba(71, 85, 105, 0.28)"


def _display_limit(value: int, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError(f"{name} must be a positive integer")
    return value


def create_visualization(
    aggregates: pd.DataFrame,
    subtitle: str | None = None,
    *,
    max_agencies: int = 8,
    max_complaints: int = 12,
    max_edges: int = 40,
) -> go.Figure:
    """Render a bounded network from exact agency × complaint aggregate counts."""
    missing = REQUIRED_COLUMNS - set(aggregates.columns)
    if missing:
        raise ValueError(f"Missing required network columns: {', '.join(sorted(missing))}")
    max_agencies = _display_limit(max_agencies, "max_agencies")
    max_complaints = _display_limit(max_complaints, "max_complaints")
    max_edges = _display_limit(max_edges, "max_edges")

    requests = pd.to_numeric(aggregates["requests"], errors="coerce")
    if requests.isna().any() or (requests < 0).any():
        raise ValueError("requests must contain non-negative numeric counts")

    fig = go.Figure()
    data = aggregates.assign(requests=requests).dropna(subset=["agency", "complaint_type"])
    data = data.groupby(["agency", "complaint_type"], as_index=False, sort=False).requests.sum()
    total_requests = int(requests.sum())
    if data.empty or not data.requests.any():
        fig.add_annotation(text="No matching agency–complaint links to display.", showarrow=False)
        fig.update_layout(meta={"shown_requests": 0, "total_requests": total_requests})
        return fig

    agencies = (
        data.groupby("agency").requests.sum().nlargest(max_agencies).index.astype(str).tolist()
    )
    complaints = (
        data.groupby("complaint_type")
        .requests.sum()
        .nlargest(max_complaints)
        .index.astype(str)
        .tolist()
    )
    edges = data[
        data.agency.astype(str).isin(agencies) & data.complaint_type.astype(str).isin(complaints)
    ]
    edges = edges.nlargest(max_edges, "requests").sort_values(
        ["agency", "requests", "complaint_type"], ascending=[True, False, True]
    )
    shown_requests = int(edges.requests.sum())
    shown_pct = 100 * shown_requests / total_requests if total_requests else 0.0

    shown_agencies = [agency for agency in agencies if agency in set(edges.agency.astype(str))]
    shown_complaints = [
        complaint for complaint in complaints if complaint in set(edges.complaint_type.astype(str))
    ]
    agency_y = dict(zip(shown_agencies, np.linspace(1, 0, len(shown_agencies)), strict=True))
    complaint_y = dict(zip(shown_complaints, np.linspace(1, 0, len(shown_complaints)), strict=True))
    max_requests = float(edges.requests.max())

    for row in edges.itertuples(index=False):
        agency = str(row.agency)
        complaint = str(row.complaint_type)
        width = 1.0 + 7.0 * np.sqrt(float(row.requests) / max_requests)
        hover = f"<b>{agency} → {complaint}</b><br>Requests: {int(row.requests):,}"
        fig.add_trace(
            go.Scatter(
                x=[0, 1],
                y=[agency_y[agency], complaint_y[complaint]],
                mode="lines",
                line={"color": EDGE_COLOR, "width": width},
                text=[hover, hover],
                hovertemplate="%{text}<extra></extra>",
                showlegend=False,
                meta={"kind": "edge"},
            )
        )

    agency_totals = edges.groupby(edges.agency.astype(str)).requests.sum()
    complaint_totals = edges.groupby(edges.complaint_type.astype(str)).requests.sum()
    fig.add_trace(
        go.Scatter(
            x=[0] * len(shown_agencies),
            y=[agency_y[name] for name in shown_agencies],
            mode="markers+text",
            name="Agencies",
            text=shown_agencies,
            textposition="middle left",
            cliponaxis=False,
            marker={"color": AGENCY_COLOR, "size": 18, "line": {"color": "white", "width": 1}},
            customdata=[[f"{int(agency_totals[name]):,}"] for name in shown_agencies],
            hovertemplate=(
                "<b>%{text}</b><br>Displayed-link requests: %{customdata[0]}<extra></extra>"
            ),
            meta={"kind": "agency_nodes"},
        )
    )
    fig.add_trace(
        go.Scatter(
            x=[1] * len(shown_complaints),
            y=[complaint_y[name] for name in shown_complaints],
            mode="markers+text",
            name="Complaint types",
            text=shown_complaints,
            textposition="middle right",
            cliponaxis=False,
            marker={
                "color": COMPLAINT_COLOR,
                "size": 18,
                "line": {"color": "white", "width": 1},
            },
            customdata=[[f"{int(complaint_totals[name]):,}"] for name in shown_complaints],
            hovertemplate=(
                "<b>%{text}</b><br>Displayed-link requests: %{customdata[0]}<extra></extra>"
            ),
            meta={"kind": "complaint_nodes"},
        )
    )

    scope = f"<br><sup>{subtitle}</sup>" if subtitle else ""
    fig.update_layout(
        title=(
            "Agency × complaint type bipartite network"
            f"{scope}<br><sup>Top {max_agencies} agencies · top {max_complaints} complaint "
            f"types · strongest {len(edges)} links</sup>"
            f"<br><sup>Showing {shown_requests:,} of {total_requests:,} filtered requests "
            f"({shown_pct:.1f}%)</sup>"
        ),
        template="plotly_white",
        height=820,
        font={"family": "Arial, sans-serif", "size": 14, "color": "#243247"},
        hoverlabel={"font_size": 14, "bgcolor": "white"},
        legend={"orientation": "h", "x": 0.38, "y": 1.03, "yanchor": "bottom"},
        margin={"l": 230, "r": 300, "t": 155, "b": 65},
        xaxis={"range": [-0.08, 1.08], "visible": False, "fixedrange": True},
        yaxis={"range": [-0.05, 1.05], "visible": False, "fixedrange": True},
        meta={
            "shown_requests": shown_requests,
            "total_requests": total_requests,
            "edge_count": len(edges),
        },
    )
    return fig

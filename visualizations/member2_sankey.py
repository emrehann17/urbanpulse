"""Member 2 Sankey diagram for exact agency-to-complaint request flows."""

import pandas as pd
import plotly.graph_objects as go

REQUIRED_COLUMNS = {"agency", "complaint_type", "requests"}
MISSING_AGENCY = "[Missing agency]"
MISSING_COMPLAINT = "[Missing complaint type]"


def create_visualization(aggregates: pd.DataFrame, *, subtitle: str | None = None) -> go.Figure:
    """Render every exact edge, including null agency or complaint-category groups."""
    missing = REQUIRED_COLUMNS - set(aggregates.columns)
    if missing:
        raise ValueError(f"Missing required Sankey columns: {', '.join(sorted(missing))}")
    counts = pd.to_numeric(aggregates.requests, errors="coerce")
    if counts.isna().any() or (counts < 0).any():
        raise ValueError("requests must contain non-negative numeric counts")
    total = int(counts.sum())
    data = aggregates[["agency", "complaint_type"]].copy()
    data["requests"] = counts.astype("int64")
    data = data.loc[data.requests > 0]
    if data.empty:
        fig = go.Figure()
        fig.add_annotation(text="No requests match the shared filters.", showarrow=False)
        fig.update_layout(title="Agency → complaint type Sankey", meta={"requests": total})
        return fig

    # Prefix internal IDs so a real category named like the missing label stays distinct.
    agency_ids = [
        ("agency:null", MISSING_AGENCY) if pd.isna(value) else (f"agency:value:{value}", str(value))
        for value in data.agency
    ]
    complaint_ids = [
        ("complaint:null", MISSING_COMPLAINT)
        if pd.isna(value)
        else (f"complaint:value:{value}", str(value))
        for value in data.complaint_type
    ]
    data["agency_id"] = [item[0] for item in agency_ids]
    data["agency_label"] = [item[1] for item in agency_ids]
    data["complaint_id"] = [item[0] for item in complaint_ids]
    data["complaint_label"] = [item[1] for item in complaint_ids]
    data = data.groupby(
        ["agency_id", "agency_label", "complaint_id", "complaint_label"],
        as_index=False,
        sort=False,
    ).requests.sum()
    agencies = data[["agency_id", "agency_label"]].drop_duplicates()
    complaints = data[["complaint_id", "complaint_label"]].drop_duplicates()
    nodes = [*agencies.to_dict("records"), *complaints.to_dict("records")]
    node_ids = [row["agency_id"] if "agency_id" in row else row["complaint_id"] for row in nodes]
    labels = [
        row["agency_label"] if "agency_label" in row else row["complaint_label"] for row in nodes
    ]
    index = {node_id: position for position, node_id in enumerate(node_ids)}
    sources = [index[value] for value in data.agency_id]
    targets = [index[value] for value in data.complaint_id]
    values = data.requests.astype(int).tolist()
    labels_hover = [
        f"{agency} → {complaint}<br>Requests: {int(value):,}"
        for agency, complaint, value in zip(
            data.agency_label, data.complaint_label, values, strict=True
        )
    ]
    scope = f"<br><sup>{subtitle}</sup>" if subtitle else ""
    fig = go.Figure(
        go.Sankey(
            arrangement="snap",
            node={
                "label": labels,
                "pad": 12,
                "thickness": 18,
                "line": {"color": "#ffffff", "width": 0.8},
                "color": ["#2563eb"] * len(agencies) + ["#d97706"] * len(complaints),
            },
            link={
                "source": sources,
                "target": targets,
                "value": values,
                "customdata": labels_hover,
                "hovertemplate": "%{customdata}<extra></extra>",
                "color": "rgba(100,116,139,0.24)",
            },
            meta={"kind": "exact_agency_complaint_counts"},
        )
    )
    fig.update_layout(
        title=f"Agency → complaint type · exact request flows{scope}",
        template="plotly_white",
        height=max(560, min(1100, 24 * max(len(agencies), len(complaints)))),
        font={"family": "Arial, sans-serif", "size": 12, "color": "#243247"},
        margin={"l": 20, "r": 20, "t": 90, "b": 25},
        meta={
            "requests": total,
            "edge_count": len(data),
            "missing_agency_requests": int(
                aggregates.loc[aggregates.agency.isna(), "requests"].sum()
            ),
            "missing_complaint_requests": int(
                aggregates.loc[aggregates.complaint_type.isna(), "requests"].sum()
            ),
        },
    )
    return fig

"""Member 3: parallel-coordinates view of persisted district profiles."""

from collections.abc import Mapping
from typing import Any

import numpy as np
import pandas as pd
import plotly.graph_objects as go

from pipeline.geography import DISTRICT_CODES
from visualizations.member3_pca_clusters import CLUSTER_COLORS

PROFILE_COLUMNS = (
    "request_count",
    "median_closure_hours",
    "long_closure_rate",
    "complaint_share_0",
    "complaint_share_1",
    "complaint_share_2",
    "complaint_share_other",
)
REQUIRED_COLUMNS = {"boro_cd", "cluster_id", *PROFILE_COLUMNS}


def _validate_profiles(clusters: pd.DataFrame, metadata: Mapping[str, Any]) -> None:
    missing = REQUIRED_COLUMNS - set(clusters.columns)
    if missing:
        raise ValueError(f"Missing required profile columns: {', '.join(sorted(missing))}")
    district_codes = clusters.boro_cd.astype("string")
    if len(clusters) != 59 or set(district_codes) != DISTRICT_CODES:
        raise ValueError("Parallel coordinates require exactly the 59 ordinary districts")
    if district_codes.duplicated().any():
        raise ValueError("District profile input contains duplicate codes")

    cluster_ids = pd.to_numeric(clusters.cluster_id, errors="coerce")
    if cluster_ids.isna().any() or set(cluster_ids.astype(int)) != set(CLUSTER_COLORS):
        raise ValueError("Expected categorical cluster IDs 0 and 1")
    for column in PROFILE_COLUMNS:
        values = pd.to_numeric(clusters[column], errors="coerce")
        if values.isna().any() or not np.isfinite(values).all():
            raise ValueError(f"Column {column!r} must contain complete finite values")
        if (values < 0).any():
            raise ValueError(f"Column {column!r} cannot contain negative values")
        if (column.startswith("complaint_share_") or column == "long_closure_rate") and (
            values > 1
        ).any():
            raise ValueError(f"Column {column!r} must contain proportions from zero to one")

    categories = metadata.get("complaint_categories")
    if not isinstance(categories, Mapping):
        raise ValueError("Metadata must include complaint_categories")
    for column in ("complaint_share_0", "complaint_share_1", "complaint_share_2"):
        if column not in categories:
            raise ValueError(f"Metadata is missing the label for {column}")


def _dimension(values: pd.Series, label: str, *, percent: bool = False) -> dict:
    numeric = pd.to_numeric(values).astype(float)
    if percent:
        numeric = numeric * 100
    low, high = float(numeric.min()), float(numeric.max())
    padding = (high - low) * 0.03 or 1.0
    result = {
        "label": label,
        "values": numeric,
        "range": [low - padding, high + padding],
    }
    if percent:
        result["tickformat"] = ".1f"
    return result


def create_visualization(
    clusters: pd.DataFrame,
    metadata: Mapping[str, Any],
    subtitle: str | None = None,
) -> go.Figure:
    """Render the 59 saved district profiles without refitting or normalizing them."""
    _validate_profiles(clusters, metadata)
    categories = metadata["complaint_categories"]
    residential_label = categories["complaint_share_1"].replace(
        "Noise - Residential", "Residential noise"
    )
    district_values = pd.to_numeric(clusters.boro_cd).astype(float)
    district_low, district_high = district_values.min(), district_values.max()
    dimensions = [
        {
            "label": "District code",
            "values": district_values,
            "range": [float(district_low), float(district_high)],
            "tickformat": "d",
        },
        _dimension(clusters.request_count, "Requests"),
        _dimension(clusters.median_closure_hours, "Median closure (h)"),
        _dimension(clusters.long_closure_rate, "Over 7 days (%)", percent=True),
        _dimension(
            clusters.complaint_share_0,
            f"{categories['complaint_share_0']} (%)",
            percent=True,
        ),
        _dimension(
            clusters.complaint_share_1,
            f"{residential_label} (%)",
            percent=True,
        ),
        _dimension(
            clusters.complaint_share_2,
            f"{categories['complaint_share_2']} (%)",
            percent=True,
        ),
        _dimension(
            clusters.complaint_share_other,
            "Other complaints (%)",
            percent=True,
        ),
    ]
    colorscale = [
        [0.0, CLUSTER_COLORS[0]],
        [0.499, CLUSTER_COLORS[0]],
        [0.5, CLUSTER_COLORS[1]],
        [1.0, CLUSTER_COLORS[1]],
    ]
    fig = go.Figure(
        go.Parcoords(
            line={
                "color": pd.to_numeric(clusters.cluster_id).astype(int),
                "colorscale": colorscale,
                "cmin": 0,
                "cmax": 1,
                "showscale": True,
                "colorbar": {
                    "title": {"text": "Cluster<br>(categorical)", "side": "top"},
                    "tickvals": [0, 1],
                    "ticktext": ["Cluster 0", "Cluster 1"],
                    "len": 0.38,
                    "thickness": 18,
                    "x": 0.94,
                    "xanchor": "left",
                },
            },
            dimensions=dimensions,
            domain={"x": [0, 0.88], "y": [0.10, 0.68]},
            labelfont={"size": 11, "color": "#243247"},
            tickfont={"size": 10, "color": "#475569"},
            rangefont={"size": 10, "color": "#475569"},
        )
    )
    scope = f"<br><sup>{subtitle}</sup>" if subtitle else ""
    fig.update_layout(
        title=(
            "Community district profile comparison · precomputed 2025 K-Means model"
            f"{scope}<br><sup>59 districts · drag an axis to brush; "
            "double-click to clear</sup>"
        ),
        template="plotly_white",
        height=850,
        font={"family": "Arial, sans-serif", "size": 14, "color": "#243247"},
        margin={"l": 65, "r": 120, "t": 190, "b": 70},
        annotations=[
            {
                "text": (
                    "Axes retain their original units. Cluster colors are nominal categories, "
                    "not performance rankings."
                ),
                "showarrow": False,
                "xref": "paper",
                "yref": "paper",
                "x": 0,
                "y": 0.01,
                "xanchor": "left",
                "font": {"size": 12, "color": "#475569"},
            }
        ],
        meta={"district_count": len(clusters), "dimension_count": len(dimensions)},
    )
    return fig

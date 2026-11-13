"""Member 3: PCA projection of the persisted district K-Means solution."""

from collections.abc import Mapping
from typing import Any

import numpy as np
import pandas as pd
import plotly.graph_objects as go

from pipeline.geography import DISTRICT_CODES

REQUIRED_COLUMNS = {
    "boro_cd",
    "cluster_id",
    "request_count",
    "median_closure_hours",
    "long_closure_rate",
    "pca_x",
    "pca_y",
}
CLUSTER_COLORS = {0: "#0072B2", 1: "#D55E00"}


def _numeric_column(clusters: pd.DataFrame, column: str) -> pd.Series:
    """Return a numeric view of one column or reject non-numeric values."""
    values = pd.to_numeric(clusters[column], errors="coerce")
    if values.isna().sum() > clusters[column].isna().sum():
        raise ValueError(f"Column {column!r} contains non-numeric values")
    return values


def _validate_inputs(clusters: pd.DataFrame, metadata: Mapping[str, Any] | None) -> None:
    """Validate the reviewed 59-district export and optional companion metadata."""
    missing = REQUIRED_COLUMNS - set(clusters.columns)
    if missing:
        raise ValueError(f"Missing required cluster columns: {', '.join(sorted(missing))}")

    district_codes = clusters["boro_cd"].astype("string")
    if len(clusters) != 59 or set(district_codes) != DISTRICT_CODES:
        raise ValueError("PCA cluster input must contain exactly the 59 ordinary districts")
    if district_codes.duplicated().any():
        raise ValueError("PCA cluster input contains duplicate district codes")

    cluster_ids = _numeric_column(clusters, "cluster_id")
    if cluster_ids.isna().any() or not np.equal(cluster_ids, np.floor(cluster_ids)).all():
        raise ValueError("cluster_id must contain integer categorical labels")
    cluster_ids = cluster_ids.astype(int)
    if set(cluster_ids) != set(CLUSTER_COLORS):
        raise ValueError("Expected the persisted categorical cluster IDs 0 and 1")

    for column in ("pca_x", "pca_y"):
        values = _numeric_column(clusters, column)
        if values.isna().any() or not np.isfinite(values).all():
            raise ValueError(f"Column {column!r} must contain finite PCA coordinates")

    requests = _numeric_column(clusters, "request_count")
    if requests.isna().any() or (requests < 0).any():
        raise ValueError("request_count must contain non-negative values")

    medians = _numeric_column(clusters, "median_closure_hours")
    if (medians.dropna() < 0).any():
        raise ValueError("median_closure_hours cannot be negative")

    rates = _numeric_column(clusters, "long_closure_rate")
    if ((rates.dropna() < 0) | (rates.dropna() > 1)).any():
        raise ValueError("long_closure_rate must be between zero and one")

    if "selected_k" in clusters:
        selected = _numeric_column(clusters, "selected_k").dropna().unique().tolist()
        if selected != [2]:
            raise ValueError("CSV selected_k must consistently identify the saved K=2 solution")

    if metadata is None:
        return

    if metadata.get("selected_k") != 2:
        raise ValueError("Metadata selected_k must identify the saved K=2 solution")

    expected_sizes = metadata.get("cluster_sizes")
    actual_sizes = clusters.groupby(cluster_ids, sort=True).size().tolist()
    if expected_sizes is not None and list(expected_sizes) != actual_sizes:
        raise ValueError("CSV cluster sizes do not match the companion metadata")

    source = metadata.get("source")
    source_hash = source.get("parquet_sha256") if isinstance(source, Mapping) else None
    if source_hash is not None and "source_sha256" in clusters:
        csv_hashes = clusters["source_sha256"].dropna().astype(str).unique().tolist()
        if csv_hashes != [source_hash]:
            raise ValueError("CSV source hash does not match the companion metadata")

    model_version = metadata.get("model_version")
    if model_version is not None and "model_version" in clusters:
        csv_versions = clusters["model_version"].dropna().astype(str).unique().tolist()
        if csv_versions != [model_version]:
            raise ValueError("CSV model version does not match the companion metadata")

    variance = metadata.get("pca_explained_variance_ratio")
    if variance is not None:
        if not isinstance(variance, list | tuple) or len(variance) < 2:
            raise ValueError("PCA explained-variance metadata must contain two values")
        try:
            variance_values = np.asarray(variance[:2], dtype=float)
        except (TypeError, ValueError) as exc:
            raise ValueError("PCA explained-variance values must be numeric") from exc
        if not np.isfinite(variance_values).all() or not ((0 <= variance_values).all()):
            raise ValueError("PCA explained-variance values must be finite and non-negative")


def _display_number(value: Any, *, percentage: bool = False) -> str:
    """Format hover values while retaining explicit missing-value semantics."""
    if pd.isna(value):
        return "Unavailable"
    if percentage:
        return f"{float(value):.2%}"
    return f"{float(value):,.2f}"


def create_visualization(
    clusters: pd.DataFrame,
    metadata: Mapping[str, Any] | None = None,
    subtitle: str | None = None,
) -> go.Figure:
    """Render all persisted district PCA coordinates without refitting or rescaling."""
    _validate_inputs(clusters, metadata)

    variance = metadata.get("pca_explained_variance_ratio") if metadata else None
    if variance is None:
        x_title, y_title = "PCA component 1", "PCA component 2"
    else:
        x_title = f"PCA component 1 ({float(variance[0]):.2%} explained variance)"
        y_title = f"PCA component 2 ({float(variance[1]):.2%} explained variance)"

    cluster_ids = pd.to_numeric(clusters["cluster_id"]).astype(int)
    district_codes = clusters["boro_cd"].astype("string")
    fig = go.Figure()

    for cluster_id in sorted(CLUSTER_COLORS):
        mask = cluster_ids.eq(cluster_id)
        group = clusters.loc[mask]
        group_codes = district_codes.loc[mask]
        customdata = [
            [
                code,
                str(cluster_id),
                f"{int(requests):,}",
                _display_number(median),
                _display_number(rate, percentage=True),
            ]
            for code, requests, median, rate in zip(
                group_codes,
                group["request_count"],
                group["median_closure_hours"],
                group["long_closure_rate"],
                strict=True,
            )
        ]
        fig.add_trace(
            go.Scatter(
                x=group["pca_x"],
                y=group["pca_y"],
                mode="markers",
                name=f"Cluster {cluster_id} · descriptive label ({len(group)} districts)",
                marker={
                    "color": CLUSTER_COLORS[cluster_id],
                    "size": 13,
                    "line": {"color": "white", "width": 1},
                    "opacity": 0.88,
                },
                customdata=customdata,
                hovertemplate=(
                    "<b>Community district %{customdata[0]}</b>"
                    "<br>Cluster: %{customdata[1]} (categorical)"
                    "<br>Requests: %{customdata[2]}"
                    "<br>Median closure hours: %{customdata[3]}"
                    "<br>Beyond-seven-day closure rate: %{customdata[4]}"
                    "<extra></extra>"
                ),
            )
        )

    scope = f"{subtitle} · " if subtitle else ""
    fig.update_layout(
        title={
            "text": (
                "PCA Cluster Explorer · precomputed 2025 K-Means model"
                f"<br><sup>{scope}59 ordinary community districts · PCA coordinates are saved "
                "model outputs</sup>"
            ),
            "font": {"size": 20},
        },
        template="plotly_white",
        autosize=True,
        height=720,
        font={"family": "Arial, sans-serif", "size": 14, "color": "#243247"},
        hoverlabel={"font_size": 14, "bgcolor": "white"},
        hovermode="closest",
        xaxis={"title": x_title, "zeroline": True, "zerolinecolor": "#cbd5e1"},
        yaxis={"title": y_title, "zeroline": True, "zerolinecolor": "#cbd5e1"},
        legend={"orientation": "h", "x": 0, "y": 1.04, "yanchor": "bottom"},
        margin={"l": 85, "r": 35, "t": 155, "b": 105},
        annotations=[
            {
                "text": (
                    "Cluster IDs are nominal categories—not success, quality, or performance "
                    "rankings. Distances are descriptive in the saved PCA projection."
                ),
                "showarrow": False,
                "xref": "paper",
                "yref": "paper",
                "x": 0,
                "y": -0.16,
                "xanchor": "left",
                "align": "left",
                "font": {"size": 12, "color": "#475569"},
            }
        ],
    )
    return fig

"""Streamlit integration for Member 3's persisted PCA cluster explorer."""

import json
from pathlib import Path

import pandas as pd
import streamlit as st

from config.settings import ROOT
from visualizations.member3_pca_clusters import create_visualization

CLUSTERS_PATH = ROOT / "ml" / "results" / "district_clusters.csv"
METADATA_PATH = ROOT / "ml" / "results" / "kmeans_metrics.json"


@st.cache_data(max_entries=4, show_spinner="Loading the reviewed PCA cluster results…")
def load_cluster_results(
    clusters_path: str,
    clusters_fingerprint: tuple[int, int],
    metadata_path: str,
    metadata_fingerprint: tuple[int, int],
) -> tuple[pd.DataFrame, dict]:
    """Load small persisted results and reject replacement during the app session."""
    csv_path = Path(clusters_path)
    json_path = Path(metadata_path)
    csv_stat = csv_path.stat()
    json_stat = json_path.stat()
    if (csv_stat.st_mtime_ns, csv_stat.st_size) != clusters_fingerprint:
        raise ValueError("PCA cluster CSV changed; refresh the application")
    if (json_stat.st_mtime_ns, json_stat.st_size) != metadata_fingerprint:
        raise ValueError("PCA metadata changed; refresh the application")

    clusters = pd.read_csv(csv_path, dtype={"boro_cd": "string"})
    with json_path.open(encoding="utf-8") as handle:
        metadata = json.load(handle)
    return clusters, metadata


def render_member3_clusters(*, is_full: bool) -> None:
    """Render the fixed full-year model without applying dashboard filters."""
    st.header("Member 3 · PCA Cluster Explorer")
    if not is_full:
        st.info(
            "Select the full dataset to view the reviewed 2025 PCA cluster model. "
            "The model is not estimated from the demo sample."
        )
        return

    try:
        csv_stat = CLUSTERS_PATH.stat()
        json_stat = METADATA_PATH.stat()
        clusters, metadata = load_cluster_results(
            str(CLUSTERS_PATH),
            (csv_stat.st_mtime_ns, csv_stat.st_size),
            str(METADATA_PATH),
            (json_stat.st_mtime_ns, json_stat.st_size),
        )
        figure = create_visualization(
            clusters,
            metadata,
            subtitle="Entire verified 2025 district cohort",
        )
        st.plotly_chart(
            figure,
            use_container_width=True,
            key="member3_pca_clusters",
        )
        geography = metadata.get("geography_counts", {})
        st.caption(
            "This is the saved full-year K-Means solution. Sidebar filters do not refit, "
            "subset, or recolor these 59 district points. Cluster IDs are nominal categories, "
            "not performance rankings. "
            f"Excluded from model fitting: {geography.get('joint_interest_area', 0):,} JIA "
            f"requests and {geography.get('unmatched_or_invalid', 0):,} unmatched/invalid "
            "requests."
        )
    except (OSError, TypeError, ValueError) as exc:
        st.error(f"Member 3 PCA clusters could not be prepared: {exc}")

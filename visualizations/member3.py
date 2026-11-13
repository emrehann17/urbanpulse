"""Streamlit integration for Member 3's three assigned visualizations."""

import json
from pathlib import Path

import pandas as pd
import streamlit as st

from config.settings import ROOT
from pipeline.filters import FilterSpec
from pipeline.query import ParquetQuery
from visualizations.member3_bipartite import create_visualization as create_bipartite
from visualizations.member3_parallel_coordinates import (
    create_visualization as create_parallel_coordinates,
)
from visualizations.member3_pca_clusters import create_visualization as create_pca_clusters

CLUSTERS_PATH = ROOT / "ml" / "results" / "district_clusters.csv"
METADATA_PATH = ROOT / "ml" / "results" / "kmeans_metrics.json"


@st.cache_data(max_entries=16, ttl=600, show_spinner="Preparing agency network…")
def prepare_agency_complaints(path: str, fingerprint: tuple, filters: FilterSpec) -> pd.DataFrame:
    """Return exact agency × complaint counts for the shared filtered population."""
    query = ParquetQuery(path)
    stat = query.path.stat()
    if (str(query.path), stat.st_mtime_ns, stat.st_size) != fingerprint:
        raise ValueError("Dataset changed; refresh the application")
    return query.aggregate(
        ("agency", "complaint_type"),
        metrics=("requests",),
        filters=filters,
    )


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


def render_member3_bipartite(path: Path, filters: FilterSpec, *, fingerprint: tuple) -> None:
    """Render the assigned bipartite network from the common filtered cohort."""
    st.header("Member 3 · Agency × Complaint Bipartite Network")
    try:
        aggregates = prepare_agency_complaints(str(path), fingerprint, filters)
        st.plotly_chart(
            create_bipartite(
                aggregates,
                subtitle="Current shared filters · full 2025 source",
            ),
            use_container_width=True,
            key="member3_agency_complaint_bipartite",
        )
        st.caption(
            "Exact counts use the same borough, complaint, agency, and creation-date filters "
            "as the application. For readability, the display retains the top 8 agencies, top "
            "12 complaint types, and strongest 40 links. The figure reports their coverage of "
            "all filtered requests; line width encodes exact request count."
        )
    except (OSError, ValueError) as exc:
        st.error(f"Member 3 bipartite network could not be prepared: {exc}")


def render_member3_models(*, is_full: bool) -> None:
    """Render the two fixed full-year district views without applying dashboard filters."""
    st.header("Member 3 · District profiles and PCA clusters")
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
        parallel_figure = create_parallel_coordinates(
            clusters,
            metadata,
            subtitle="Entire verified 2025 district cohort",
        )
        st.plotly_chart(
            parallel_figure,
            use_container_width=True,
            key="member3_parallel_coordinates",
        )
        st.caption(
            "Parallel axes retain raw district-profile units and support interactive brushing. "
            "Sidebar filters do not alter these saved full-year profiles."
        )
        pca_figure = create_pca_clusters(
            clusters,
            metadata,
            subtitle="Entire verified 2025 district cohort",
        )
        st.plotly_chart(
            pca_figure,
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
        st.error(f"Member 3 district model views could not be prepared: {exc}")

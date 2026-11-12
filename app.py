"""Shared-filter integration: Member 1 charts and original data diagnostics."""

from datetime import date

import pandas as pd
import streamlit as st

from pipeline import apply_filters, get_data_summary, get_filter_options, load_data
from pipeline.filters import FilterSpec
from pipeline.loader import data_path
from pipeline.query import ParquetQuery
from visualizations.member1 import render_member1
from visualizations.member3 import render_member3_clusters

PREVIEW_COLUMNS = (
    "unique_key",
    "created_date",
    "borough",
    "complaint_type",
    "agency",
    "duration_bucket",
    "closure_hours",
    "boro_cd",
)


@st.cache_data(show_spinner="Loading the shared dataset…")
def cached_data(dataset: str, modified_ns: int, file_size: int) -> pd.DataFrame:
    """Invalidate cached data when the local artifact changes."""
    return load_data(dataset=dataset)


def snapshot_query(dataset: str, fingerprint: tuple) -> ParquetQuery:
    """Reject a replacement between the app's catalog and diagnostic queries."""
    query = ParquetQuery(dataset=dataset)
    stat = query.path.stat()
    if (str(query.path), stat.st_mtime_ns, stat.st_size) != fingerprint:
        raise ValueError("Dataset changed; rerun the application to refresh this snapshot")
    return query


@st.cache_data(max_entries=8, ttl=600)
def query_catalog(dataset: str, fingerprint: tuple) -> tuple:
    """Cache small option lists/provenance, never a full request DataFrame."""
    query = snapshot_query(dataset, fingerprint)
    return query.provenance, query.filter_options(), query.count()


@st.cache_data(max_entries=32, ttl=600)
def query_diagnostics(dataset: str, fingerprint: tuple, filters: FilterSpec) -> tuple:
    """Cache one summary and at most 200 projected rows per selection."""
    query = snapshot_query(dataset, fingerprint)
    return query.summary(filters=filters), query.preview(PREVIEW_COLUMNS, filters=filters)


def main() -> None:
    """Render a minimal integration app without making any network requests."""
    st.set_page_config(page_title="UrbanPulse", layout="wide")
    st.title("UrbanPulse — Where Do Public Service Requests Wait?")
    st.caption("Geography, waiting times, daily demand, and district clusters · CEN445")
    dataset = st.sidebar.selectbox("Dataset", ["demo", "smoke", "full"], key="dataset")
    try:
        path = data_path(dataset)
        stat = path.stat()
        fingerprint = (str(path.resolve()), stat.st_mtime_ns, stat.st_size)
        if dataset == "full":
            provenance, options, total_rows = query_catalog(dataset, fingerprint)
        else:
            df = cached_data(dataset, stat.st_mtime_ns, stat.st_size)
            provenance = df.attrs["urbanpulse"]
            options, total_rows = get_filter_options(df), len(df)
    except (OSError, ValueError) as exc:
        st.error(f"The selected dataset could not be loaded. {exc}")
        st.code("python -m pipeline --help")
        return
    if provenance["mode"] != "full":
        st.warning(
            "SAMPLE: selected records from each month of 2025. Counts and rates describe "
            "this sample only; they do not estimate the full NYC population."
        )
    else:
        st.info(
            "Full-scope extraction of 2025 requests in five boroughs; live-source changes "
            "can affect snapshot completeness. Review the quality report."
        )
    st.caption(
        f"Observation cutoff: {provenance['extraction_cutoff']} · "
        f"Schema {provenance['schema_version']}"
    )
    selections = {}
    for field, label in (
        ("borough", "Borough"),
        ("complaint_type", "Complaint type"),
        ("agency", "Agency"),
    ):
        selections[field] = st.sidebar.multiselect(
            label,
            ["All", *options[field]],
            default=["All"],
            key=f"{dataset}_{field}",
            help="All disables this filter. Clear every selection to show no records.",
        )
    start = end = None
    if options["start_date"]:
        dates = st.sidebar.date_input(
            "Created date range",
            value=(
                date.fromisoformat(options["start_date"]),
                date.fromisoformat(options["end_date"]),
            ),
            key=f"{dataset}_dates",
        )
        if len(dates) != 2:
            st.info("Choose both a start and end date.")
            return
        start, end = dates
    try:
        filters = FilterSpec(**selections, start_date=start, end_date=end)
        if dataset == "full":
            summary, preview = query_diagnostics(dataset, fingerprint, filters)
        else:
            filtered = apply_filters(df, **selections, start_date=start, end_date=end)
            summary = get_data_summary(filtered)
            preview = filtered[list(PREVIEW_COLUMNS)].head(200)
    except (OSError, ValueError) as exc:
        st.error(f"Unable to query the selected data. {exc}")
        return
    left, middle, right = st.columns(3)
    left.metric(
        "Filtered requests", f"{summary['rows']:,}", help=f"Dataset records: {total_rows:,}"
    )
    middle.metric("Valid closure observations", f"{summary['valid_closures']:,}")
    right.metric("Matched district / JIA", f"{summary['geographic_matches']:,}")
    if summary["rows"] == 0:
        st.info("No records match these filters. Adjust the sidebar selections.")
    else:
        with st.expander("Shared-data diagnostics", expanded=False):
            st.subheader("Shared-data quality indicators")
            st.json(summary)
            st.subheader("Filtered record preview")
            st.dataframe(
                preview,
                hide_index=True,
                use_container_width=True,
            )
            st.caption(
                "Preview limited to 200 rows. All indicators use the same complete filtered data. "
                "These diagnostics are not part of the nine final visualizations."
            )
        render_member1(
            path,
            filters,
            is_full=provenance["mode"] == "full",
            fingerprint=fingerprint,
        )
    render_member3_clusters(is_full=provenance["mode"] == "full")


if __name__ == "__main__":
    main()

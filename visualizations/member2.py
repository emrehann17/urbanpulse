"""Streamlit integration for Member 2's three shared-filter visualizations."""

from dataclasses import replace
from pathlib import Path

import pandas as pd
import streamlit as st

from pipeline.chart_data import daily_data
from pipeline.filters import FilterSpec
from pipeline.query import ParquetQuery
from visualizations.member2_calendar import create_visualization as create_calendar
from visualizations.member2_ridgeline import create_visualization as create_ridgeline
from visualizations.member2_sankey import create_visualization as create_sankey

RIDGELINE_TYPES = 6


def _snapshot_query(path: str, fingerprint: tuple) -> ParquetQuery:
    query = ParquetQuery(path)
    stat = query.path.stat()
    if (str(query.path.resolve()), stat.st_mtime_ns, stat.st_size) != fingerprint:
        raise ValueError("Dataset changed; refresh the application")
    return query


@st.cache_data(max_entries=32, ttl=600, show_spinner="Preparing the calendar heatmap…")
def prepare_calendar(path: str, fingerprint: tuple, filters: FilterSpec) -> pd.DataFrame:
    """Return exact daily counts and the separate unknown-created-day total."""
    query = _snapshot_query(path, fingerprint)
    return daily_data(query, filters)


@st.cache_data(max_entries=32, ttl=600, show_spinner="Preparing exact Sankey flows…")
def prepare_sankey(path: str, fingerprint: tuple, filters: FilterSpec) -> pd.DataFrame:
    """Return exact agency × complaint counts, including null-category groups."""
    query = _snapshot_query(path, fingerprint)
    return query.aggregate(("agency", "complaint_type"), metrics=("requests",), filters=filters)


@st.cache_data(max_entries=32, ttl=600, show_spinner="Preparing closure duration densities…")
def prepare_ridgeline(path: str, fingerprint: tuple, filters: FilterSpec) -> pd.DataFrame:
    """Build exact duration frequencies for the six complaint types with most valid closures."""
    query = _snapshot_query(path, fingerprint)
    by_type = query.aggregate("complaint_type", metrics=("valid_closures",), filters=filters)
    by_type = by_type.dropna(subset=["complaint_type"])
    by_type = by_type.loc[by_type.valid_closures > 0]
    selected = (
        by_type.sort_values(["valid_closures", "complaint_type"], ascending=[False, True])
        .head(RIDGELINE_TYPES)
        .complaint_type.astype(str)
        .tolist()
    )
    if not selected:
        return pd.DataFrame(columns=["complaint_type", "closure_hours", "requests"])
    cohort = replace(filters, complaint_type=tuple(selected))
    return query.aggregate(
        ("complaint_type", "closure_hours"), metrics=("requests",), filters=cohort
    )


def render_member2(path: Path, filters: FilterSpec, *, fingerprint: tuple, is_full: bool) -> None:
    """Render calendar, exact flow, and duration-density charts for the shared cohort."""
    st.header("Member 2 · Calendar, Service Flows and Closure Durations")
    subtitle = (
        "Current shared filters · full 2025 source"
        if is_full
        else "Current shared filters · demo sample"
    )
    try:
        calendar = prepare_calendar(str(path), fingerprint, filters)
        st.plotly_chart(
            create_calendar(calendar, subtitle=subtitle),
            use_container_width=True,
            key="member2_calendar_heatmap",
        )
        unknown_days = int(calendar.attrs.get("unknown_created_day", 0))
        st.caption(
            "Cell color shows the exact number of requests created on each New York calendar day. "
            f"Displayed daily total: {int(calendar.requests.sum()):,}; "
            f"requests with unknown creation day: {unknown_days:,}. "
            + ("Full source." if is_full else "Demo sample only; not a population estimate.")
        )

        flows = prepare_sankey(str(path), fingerprint, filters)
        st.plotly_chart(
            create_sankey(flows, subtitle=subtitle),
            use_container_width=True,
            key="member2_sankey",
        )
        st.caption(
            "Link widths and hover counts are exact agency × complaint-type request totals. "
            "Missing agency and complaint labels remain separate visible groups; "
            "no edges are dropped."
        )

        durations = prepare_ridgeline(str(path), fingerprint, filters)
        density = create_ridgeline(durations, subtitle=subtitle, max_types=RIDGELINE_TYPES)
        st.plotly_chart(
            density,
            use_container_width=True,
            key="member2_ridgeline_density",
        )
        st.caption(
            "Each ridge is a frequency-weighted kernel density from exact "
            "completed-closure duration frequencies for the six complaint types "
            "with the most valid closures. Ridges show shape; their heights are "
            "normalized within type. The common horizontal view ends at the weighted "
            "98th percentile, and the number of records beyond it is reported on the chart. "
            + (
                "Open and unknown outcomes are not closure durations."
                if is_full
                else (
                    "The demo sample is selected and is not a population estimate; "
                    "open and unknown outcomes are not closure durations."
                )
            )
        )
    except (OSError, TypeError, ValueError) as exc:
        st.error(f"Member 2 charts could not be prepared: {exc}")

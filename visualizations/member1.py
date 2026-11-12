"""Streamlit integration and bounded aggregate caches for Member 1."""

from pathlib import Path

import streamlit as st

from config.settings import DATA_DIR
from pipeline.chart_data import daily_data, district_data, survival_data
from pipeline.filters import FilterSpec
from pipeline.geography import load_geography
from pipeline.query import ParquetQuery
from visualizations import bivariate, survival, timeseries


@st.cache_data(max_entries=8, ttl=600, show_spinner="Preparing exact filtered chart data…")
def prepare_charts(
    path: str,
    fingerprint: tuple,
    filters: FilterSpec,
    geography_path: str,
    geography_fingerprint: tuple,
) -> tuple:
    """Cache small tables only, keyed by snapshot, geography and shared filters."""
    query = ParquetQuery(path)
    stat = query.path.stat()
    if (stat.st_mtime_ns, stat.st_size) != fingerprint:
        raise ValueError("Dataset changed; refresh the application")
    geo_path = Path(geography_path)
    geo_stat = geo_path.stat()
    if (geo_stat.st_mtime_ns, geo_stat.st_size) != geography_fingerprint:
        raise ValueError("Geography changed; refresh the application")
    geojson = load_geography(geo_path)
    districts = district_data(query, filters, geojson)
    days = daily_data(query, filters)
    curves, outcomes = survival_data(query, filters)
    return districts, days, curves, outcomes


def render_member1(path: Path, filters: FilterSpec, *, is_full: bool, fingerprint: tuple) -> None:
    """Render three charts from exactly the FilterSpec used by app diagnostics."""
    st.header("Member 1 · Geography, waiting times, and daily demand")
    if not is_full:
        st.info(
            "Select the full dataset to explore these population charts. The demo's earliest "
            "200 requests per month cannot support population trends. Diagnostics remain available."
        )
        return
    try:
        geo_path = DATA_DIR / "geographic" / "community_districts.geojson"
        geo_stat, stat = geo_path.stat(), path.stat()
        if (str(path.resolve()), stat.st_mtime_ns, stat.st_size) != fingerprint:
            raise ValueError("Dataset changed since diagnostics; refresh the application")
        districts, days, curves, outcomes = prepare_charts(
            str(path),
            (stat.st_mtime_ns, stat.st_size),
            filters,
            str(geo_path),
            (geo_stat.st_mtime_ns, geo_stat.st_size),
        )
        geojson = load_geography(geo_path)
        st.plotly_chart(
            bivariate.create_visualization(districts, geojson=geojson),
            use_container_width=True,
            key="member1_districts",
        )
        st.markdown("**Classification thresholds · current filtered cohort**")
        st.table(bivariate.classification_thresholds(districts))
        st.caption(
            "Thresholds are rounded for display. Exact classification is unchanged. "
            "Low / Medium / High are cohort-relative tertiles; ties can leave tiers empty."
        )
        exclusions = districts.attrs["excluded"]
        st.caption(
            f"Known-label denominator includes mature open requests beyond seven days. "
            "Excluded from district comparisons: "
            f"{exclusions['joint_interest_area']:,} JIA requests; "
            f"{exclusions['unmatched']:,} unmatched requests (no reliable polygon assignment). "
            "Gray districts have no matching requests or fewer than 30 known labels. "
            "Raw counts are not population-adjusted; "
            "reporting propensity and complaint mix differ. "
            "These associations are not causal evidence of unequal service quality."
        )
        confidence = st.checkbox("Show pointwise 95% confidence intervals", value=True)
        st.plotly_chart(
            survival.create_visualization(curves, outcomes=outcomes, confidence=confidence),
            use_container_width=True,
            key="member1_survival",
        )
        st.caption(
            "View controls change the time axis only. The initial view shows 30 days; "
            "Full observed period restores the complete follow-up range without refitting."
        )
        st.caption(
            f"Excluded unknown outcomes: {int(outcomes.unknown_outcomes.sum()):,}. "
            "Every valid closure and right-censored observation enters the exact Kaplan–Meier "
            "calculation. Administrative closure is not verified problem resolution. "
            "Intervals assume independent requests and non-informative censoring; repeated reports "
            "and complaint mix can violate these assumptions. "
            "No causal borough comparison is implied."
        )
        if curves.attrs["display_thinned"]:
            st.caption(
                f"Display retains {curves.attrs['plotted_time_groups']:,} of "
                f"{curves.attrs['input_time_groups']:,} distinct borough/time groups. "
                "All groups affect estimation; plotted values and intervals are exact, "
                "but intermediate steps and censor marks are omitted. Zoom does not restore them."
            )
        with st.expander("Borough cohort sizes and censoring", expanded=False):
            st.dataframe(
                survival.cohort_summary(outcomes), hide_index=True, use_container_width=True
            )
        rolling = st.checkbox("Show trailing seven-day trends", value=True)
        st.plotly_chart(
            timeseries.create_visualization(days, rolling=rolling),
            use_container_width=True,
            key="member1_daily",
        )
        st.caption(
            f"Requests without a valid creation day: {days.attrs['unknown_created_day']:,} "
            "(excluded from the calendar). Daily medians describe valid completed requests "
            "grouped by creation day; open and unknown outcomes are absent from that statistic, "
            "so it can understate waits. Hover shows valid-closure and request denominators. "
            "The closure trend is a median of daily medians, not a pooled request median. "
            "Partial initial windows are allowed; missing medians remain gaps. Zoom either panel "
            "or drag the date slider to update both panels."
        )
    except (OSError, ValueError) as exc:
        st.error(f"Member 1 charts could not be prepared: {exc}")

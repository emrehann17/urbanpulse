"""Deterministic synthetic edge cases and real-demo integration; no live API."""

import json
from dataclasses import asdict
from datetime import datetime, timedelta

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
import pytest
from streamlit.testing.v1 import AppTest

from config.settings import DATA_DIR, ROOT
from pipeline import apply_filters
from pipeline.chart_data import daily_data, district_data, kaplan_meier, survival_data
from pipeline.contract import SCHEMA
from pipeline.filters import FilterSpec
from pipeline.geography import DISTRICT_CODES, load_geography
from pipeline.query import ParquetQuery
from visualizations import bivariate, survival, timeseries


@pytest.fixture
def geo():
    return load_geography(DATA_DIR / "geographic" / "community_districts.geojson")


@pytest.fixture
def query(tmp_path, frame):
    schema = SCHEMA.with_metadata(
        {b"urbanpulse": json.dumps({"schema_version": "1.0.0", "mode": "smoke"}).encode()}
    )
    path = tmp_path / "synthetic.parquet"
    pq.write_table(pa.Table.from_pandas(frame, schema=schema, preserve_index=False), path)
    return ParquetQuery(path)


def test_km_analytic_ties_and_greenwood():
    # Four subjects: closure+censor at t=1, closure at t=2, censor at t=3.
    curve = kaplan_meier([("Bronx", 1, 1, 1), ("Bronx", 2, 1, 0), ("Bronx", 3, 0, 1)], {"Bronx": 4})
    assert curve.survival.tolist() == [1, 0.75, 0.375, 0.375]
    assert curve.at_risk.tolist() == [4, 4, 2, 1]
    # Independent hand evaluation of Greenwood log-log 95% interval at t=1.
    assert curve.lower.iloc[1] == pytest.approx(0.1279469176)
    assert curve.upper.iloc[1] == pytest.approx(0.9605486423)
    assert (curve.lower <= curve.survival).all()
    assert (curve.upper >= curve.survival).all()


def test_km_zero_time_all_events_and_all_censored():
    curve = kaplan_meier([("Bronx", 0, 2, 0), ("Queens", 1, 0, 3)], {"Bronx": 2, "Queens": 3})
    assert curve.groupby("borough").survival.last().to_dict() == {"Bronx": 0, "Queens": 1}
    assert np.isfinite(curve[["survival", "lower", "upper"]]).all().all()
    assert kaplan_meier([], {}).empty


@pytest.mark.parametrize(
    "counts,totals",
    [
        ([("Bronx", -1, 1, 0)], {"Bronx": 1}),
        ([("Bronx", 1, 2, 0)], {"Bronx": 1}),
        ([("Bronx", 1, 1, 0)], {"Bronx": 2}),
        ([("Bronx", 1, 1, 0), ("Bronx", 1, 1, 0)], {"Bronx": 2}),
        ([], {"Bronx": 1}),
        ([], {"Unknown": 0}),
    ],
)
def test_bad_life_tables_raise(counts, totals):
    with pytest.raises(ValueError):
        kaplan_meier(counts, totals)


def test_streaming_display_bound_preserves_exact_estimates():
    counts = (("Bronx", float(t), 1, 0) for t in range(1, 10001))
    curve = kaplan_meier(counts, {"Bronx": 10000}, max_points=64)
    assert len(curve) <= 64
    assert curve.hours.iloc[-1] == 10000 and curve.survival.iloc[-1] == 0
    np.testing.assert_allclose(curve.survival, 1 - curve.hours / 10000, atol=1e-12)
    assert curve.attrs["input_time_groups"] == 10000 and curve.attrs["display_thinned"]


@pytest.mark.parametrize(
    "spec",
    [
        FilterSpec(),
        FilterSpec(borough="All"),
        FilterSpec(borough=[]),
        FilterSpec(borough="Atlantis"),
        FilterSpec(borough=["Manhattan", "Queens"]),
        FilterSpec(
            agency="OTHER", complaint_type="Other", start_date="2025-02-01", end_date="2025-02-01"
        ),
        FilterSpec(start_date="2025-01-01", end_date="2025-01-01"),
        FilterSpec(end_date="2025-02-02T02:00:00Z"),
        FilterSpec(agency=[]),
    ],
)
def test_every_helper_uses_global_population(query, frame, geo, spec, monkeypatch):
    # Rendering preparation must not depend on the bounded row preview.
    monkeypatch.setattr(query, "preview", lambda *a, **kw: pytest.fail("No preview statistics"))
    expected = apply_filters(frame, **asdict(spec))
    districts = district_data(query, spec, geo, min_known=1)
    days = daily_data(query, spec)
    curve, outcomes = survival_data(query, spec)
    assert districts.requests.sum() + sum(districts.attrs["excluded"].values()) == len(expected)
    assert days.requests.sum() + days.attrs["unknown_created_day"] == len(expected)
    assert outcomes.requests.sum() == len(expected)
    assert outcomes.closed.sum() == expected.closure_event.eq(True).sum()
    assert outcomes.censored.sum() == expected.closure_event.eq(False).sum()
    assert outcomes.unknown_outcomes.sum() == expected.closure_event.isna().sum()
    assert len(days) <= 365 and len(districts) == 59 and len(curve) <= 5 * 1024


def test_district_bins_exclusions_and_missing(geo):
    codes = sorted(DISTRICT_CODES)
    rows = [
        {
            "boro_cd": c,
            "requests": (i // 3 + 1) * 100,
            "known_long_labels": 100,
            "long_closures": i % 3 * 30,
            "long_closure_rate": i % 3 * 0.3,
        }
        for i, c in enumerate(codes[:9])
    ]
    rows += [
        {
            "boro_cd": c,
            "requests": 4,
            "known_long_labels": 0,
            "long_closures": 0,
            "long_closure_rate": None,
        }
        for c in [codes[9], "164", None]
    ]

    class Fake:
        def aggregate(self, *args, **kwargs):
            return pd.DataFrame(rows)

    result = district_data(Fake(), FilterSpec(), geo)
    assert set(result.bivariate_class) == set(range(-1, 9))
    assert result.attrs["excluded"] == {"joint_interest_area": 4, "unmatched": 4}
    assert result.loc[result.boro_cd.eq(codes[9]), "support"].item() == "Insufficient known labels"
    assert result.loc[result.requests.eq(0), "long_closure_rate"].isna().all()
    assert set(result.boro_cd) == DISTRICT_CODES
    fig = bivariate.create_visualization(result, geojson=geo)
    assert np.array(fig.data[1].z).shape == (3, 3)
    assert len(set(bivariate.PALETTE)) == 9
    assert len(fig.data[0].geojson["features"]) == 59
    with pytest.raises(ValueError, match="59"):
        district_data(Fake(), FilterSpec(), {"type": "FeatureCollection", "features": []})


def test_daily_gaps_medians_and_rolling(query):
    result = daily_data(
        query, FilterSpec(start_date="2025-01-01", end_date="2025-01-03"), rolling_days=2
    )
    assert result.requests.tolist() == [1, 0, 0]
    assert result.valid_closures.tolist() == [1, 0, 0]
    assert result.request_trend.tolist() == [1, 0.5, 0]
    assert result.closure_median_hours.iloc[0] == 24
    assert result.closure_median_hours.iloc[1:].isna().all()
    assert result.trend_valid_days.tolist() == [1, 1, 0]
    assert pd.isna(result.closure_trend_hours.iloc[-1])
    assert daily_data(query, FilterSpec(start_date="2026-01-01")).empty
    assert query.aggregate(metrics=("closure_median_hours",)).valid_closures.item() == 1


def test_chart_rendering_and_immutability(query, geo):
    districts = district_data(query, FilterSpec(), geo, min_known=1)
    days = daily_data(query, FilterSpec())
    curve, outcomes = survival_data(query, FilterSpec())
    originals = [f.copy(deep=True) for f in (districts, days, curve, outcomes)]
    original_geo = json.dumps(geo)
    figures = [
        bivariate.create_visualization(districts, geojson=geo),
        timeseries.create_visualization(days),
        survival.create_visualization(curve, outcomes=outcomes),
    ]
    assert figures[1].layout.xaxis.matches == "x2"
    for fig in figures:
        assert "Plotly.newPlot" in fig.to_html(include_plotlyjs=False)
    for original, actual in zip(originals, (districts, days, curve, outcomes), strict=True):
        pd.testing.assert_frame_equal(original, actual)
        assert original.attrs == actual.attrs
    assert original_geo == json.dumps(geo)
    empty_curve, empty_outcomes = survival_data(query, FilterSpec(borough=[]))
    assert survival.create_visualization(empty_curve, outcomes=empty_outcomes).layout.annotations


def test_real_demo_aggregate_reconciliation(geo):
    query = ParquetQuery()
    curves, outcomes = survival_data(query, FilterSpec())
    assert (
        outcomes.requests.sum(),
        outcomes.closed.sum(),
        outcomes.censored.sum(),
        outcomes.unknown_outcomes.sum(),
    ) == (2400, 2388, 7, 5)
    assert curves.attrs["input_time_groups"] > 0
    districts = district_data(query, FilterSpec(), geo)
    assert districts.requests.sum() == 2378
    days = daily_data(query, FilterSpec())
    assert days.requests.sum() == 2400 and days.requests.eq(0).sum() == 353


def test_demo_app_does_not_present_population_charts():
    app = AppTest.from_file(str(ROOT / "app.py"), default_timeout=20).run()
    assert not app.exception
    assert len(app.get("plotly_chart")) == 0
    assert any("earliest" in info.value for info in app.info)


def test_full_shell_renders_all_charts_and_controls(tmp_path, raw_run, monkeypatch):
    import pipeline.loader as loader
    from pipeline.build import build_processed

    monkeypatch.setattr(loader, "DATA_DIR", tmp_path)
    manifest_path = raw_run / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["config"]["mode"] = "full"  # synthetic full-mode integration fixture
    manifest_path.write_text(json.dumps(manifest))
    build_processed(raw_run, tmp_path / "processed" / "requests.parquet")
    app = AppTest.from_file(str(ROOT / "app.py"), default_timeout=20).run()
    app.sidebar.selectbox[0].set_value("full").run()
    assert not app.exception and not app.error
    assert len(app.get("plotly_chart")) == 3
    app.checkbox[0].uncheck().run()
    app.checkbox[1].uncheck().run()
    assert not app.exception and len(app.get("plotly_chart")) == 3
    app.sidebar.multiselect[0].set_value([]).run()
    assert app.metric[0].value == "0" and len(app.get("plotly_chart")) == 0


@pytest.mark.parametrize("bad", [0, -1, 32, True])
def test_rolling_bound_validation(query, bad):
    with pytest.raises(ValueError):
        daily_data(query, FilterSpec(), rolling_days=bad)


@pytest.mark.parametrize("bad", [0, 3, 4097, True])
def test_curve_output_bound_validation(bad):
    with pytest.raises(ValueError):
        kaplan_meier([], {}, max_points=bad)


def test_survival_stream_fetches_fixed_batches(query, monkeypatch):
    from contextlib import contextmanager

    original = query._cursor
    sizes = []

    @contextmanager
    def cursor(*args, **kwargs):
        with original(*args, **kwargs) as real:

            class Proxy:
                def fetchmany(self, size):
                    sizes.append(size)
                    return real.fetchmany(size)

            yield Proxy()

    monkeypatch.setattr(query, "_cursor", cursor)
    with query.survival_counts(filters=FilterSpec()) as rows:
        values = list(rows)
    assert sum(d + c for _, _, d, c in values) == 2
    assert sizes and set(sizes) == {4096}


def test_exact_even_median_and_open_denominator(tmp_path, raw_row, transform):
    rows = [
        {
            **raw_row,
            "unique_key": str(i),
            "closed_date": (datetime(2025, 1, 1) + timedelta(hours=h)).isoformat(),
        }
        for i, h in enumerate([0, 2, 4, 100])
    ]
    rows.append({**raw_row, "unique_key": "open", "closed_date": None, "status": "Open"})
    frame = transform(rows)
    path = tmp_path / "median.parquet"
    schema = SCHEMA.with_metadata({b"urbanpulse": b'{"schema_version":"1.0.0","mode":"smoke"}'})
    pq.write_table(pa.Table.from_pandas(frame, schema=schema, preserve_index=False), path)
    day = daily_data(ParquetQuery(path), FilterSpec()).iloc[0]
    assert (day.requests, day.valid_closures, day.closure_median_hours) == (5, 4, 3)


def test_equal_district_values_stay_in_one_tier(geo):
    class EqualQuery:
        def aggregate(self, *args, **kwargs):
            return pd.DataFrame(
                [
                    {
                        "boro_cd": c,
                        "requests": 100,
                        "known_long_labels": 100,
                        "long_closures": 40,
                        "long_closure_rate": 0.4,
                    }
                    for c in sorted(DISTRICT_CODES)
                ]
            )

    frame = district_data(EqualQuery(), FilterSpec(), geo)
    assert frame.bivariate_class.eq(0).all()
    assert frame.attrs["cuts"] == {"requests": [100, 100], "long_closure_rate": [0.4, 0.4]}


def test_survival_view_controls_only_relayout(query):
    curves, outcomes = survival_data(query, FilterSpec())
    original = curves.copy(deep=True)
    fig = survival.create_visualization(curves, outcomes=outcomes)
    assert tuple(fig.layout.xaxis.range) == (0, 30)
    assert fig.layout.xaxis.autorange is False
    menu = fig.layout.updatemenus[0]
    assert menu.active == 1
    assert [b.label for b in menu.buttons] == [
        "First 7 days",
        "First 30 days",
        "First 90 days",
        "Full observed period",
    ]
    expected = [7, 30, 90, max(1, curves.hours.max() / 24)]
    for button, maximum in zip(menu.buttons, expected, strict=True):
        assert button.method == "relayout"
        assert button.args[0] == {"xaxis.range": [0, maximum], "xaxis.autorange": False}
    for trace in fig.data:
        if trace.showlegend is not False:
            group = curves.loc[curves.borough.eq(trace.name)]
            np.testing.assert_array_equal(trace.x, group.hours / 24)
            np.testing.assert_array_equal(trace.y, group.survival)
    assert max(max(t.x) for t in fig.data) > 30  # tail is still present in traces
    assert "n=" not in " ".join(t.name or "" for t in fig.data)
    assert fig.layout.legend.groupclick == "togglegroup"
    pd.testing.assert_frame_equal(curves, original)
    assert survival.cohort_summary(outcomes)["Valid observations"].sum() == 2


def test_survival_empty_view_controls(query):
    curves, outcomes = survival_data(query, FilterSpec(borough=[]))
    fig = survival.create_visualization(curves, outcomes=outcomes)
    assert tuple(fig.layout.xaxis.range) == (0, 30)
    assert fig.layout.updatemenus[0].buttons[-1].args[0]["xaxis.range"] == [0, 1]
    assert not fig.data and fig.layout.annotations[0].xref == "paper"


def test_bivariate_separate_key_and_threshold_table(query, geo):
    districts = district_data(query, FilterSpec(), geo, min_known=1)
    original = districts.copy(deep=True)
    fig = bivariate.create_visualization(districts, geojson=geo)
    assert tuple(fig.layout.map.domain.x) == (0, 1)
    assert fig.layout.yaxis.domain[1] < fig.layout.shapes[0].y0 < fig.layout.map.domain.y[0]
    assert fig.layout.yaxis.scaleanchor == "x" and fig.layout.yaxis.scaleratio == 1
    assert tuple(fig.layout.xaxis.ticktext) == ("Low", "Medium", "High")
    assert tuple(fig.layout.yaxis.ticktext) == ("Low", "Medium", "High")
    assert np.array(fig.data[1].z).tolist() == [[0, 1, 2], [3, 4, 5], [6, 7, 8]]
    assert all("cuts" not in a.text.lower() for a in fig.layout.annotations)
    thresholds = bivariate.classification_thresholds(districts)
    assert thresholds.columns.tolist() == ["Dimension", "Low", "Medium", "High"]
    assert thresholds.iloc[0].Low.startswith("≤ ")
    assert thresholds.iloc[1].High.endswith("%")
    pd.testing.assert_frame_equal(districts, original)
    empty = district_data(query, FilterSpec(borough=[]), geo)
    assert bivariate.classification_thresholds(empty).Low.tolist() == ["Unavailable"] * 2
    assert set(bivariate.create_visualization(empty, geojson=geo).data[0].z) == {0}


@pytest.mark.parametrize("viewport", [1024, 1440, 1920])
def test_map_camera_and_key_fit_review_width(query, geo, viewport):
    from math import asinh, pi, radians, tan

    fig = bivariate.create_visualization(district_data(query, FilterSpec(), geo), geojson=geo)
    # Programmatic Mercator viewport containment, not a browser pixel/render test.
    width = min(viewport - (24 if viewport <= 1100 else 48), 1760)
    width -= (8 if viewport <= 1100 else 24) + fig.layout.margin.l + fig.layout.margin.r
    height = (fig.layout.height - fig.layout.margin.t - fig.layout.margin.b) * 0.70
    scale = 512 * 2**fig.layout.map.zoom
    center = fig.layout.map.center
    center_y = asinh(tan(radians(center.lat))) / (2 * pi)
    for feature in fig.data[0].geojson["features"]:
        geometry = feature["geometry"]
        polygons = geometry["coordinates"]
        if geometry["type"] == "Polygon":
            polygons = [polygons]
        for polygon in polygons:
            for ring in polygon:
                for lon, lat, *_ in ring:
                    assert abs((lon - center.lon) / 360 * scale) < width / 2
                    assert (
                        abs((asinh(tan(radians(lat))) / (2 * pi) - center_y) * scale) < height / 2
                    )
    assert fig.layout.annotations[0].y < fig.layout.shapes[0].y0
    assert fig.layout.annotations[0].y > fig.layout.yaxis.domain[1]


def test_daily_layout_and_empty_state(query):
    days = daily_data(query, FilterSpec())
    fig = timeseries.create_visualization(days)
    assert fig.layout.xaxis.matches == "x2"
    assert fig.layout.yaxis.domain[0] - fig.layout.yaxis2.domain[1] >= 0.18
    assert fig.layout.legend.y > 1 and fig.layout.legend.yanchor == "bottom"
    assert fig.layout.xaxis2.rangeslider.thickness <= 0.06
    assert fig.layout.height >= 800
    assert all(t.line.dash == "dash" for t in fig.data[2:])
    for trace, expected in zip(
        fig.data,
        [
            days.requests,
            days.closure_median_hours / 24,
            days.request_trend,
            days.closure_trend_hours / 24,
        ],
        strict=True,
    ):
        np.testing.assert_allclose(trace.y, expected, equal_nan=True)
    empty = timeseries.create_visualization(daily_data(query, FilterSpec(borough=[])))
    assert any("No requests" in a.text for a in empty.layout.annotations)


def test_review_html_readable_sections_and_scope(query, geo):
    from benchmarks.review_html import render_review

    districts = district_data(query, FilterSpec(), geo)
    curves, outcomes = survival_data(query, FilterSpec())
    days = daily_data(query, FilterSpec())
    summary = {"rows": 3, "survival": curves.attrs, "daily": days.attrs}
    fig = survival.create_visualization(curves, outcomes=outcomes)
    html = render_review(
        fig,
        chart="survival",
        cohort="<script>bad</script>",
        dataset="demo",
        summary=summary,
        districts=districts,
        outcomes=outcomes,
    )
    assert "name='viewport'" in html and '"responsive": true' in html
    assert "Methods and limitations" in html and "Explore the chart" in html
    assert "BIASED SAMPLE" in html and "Borough cohort sizes" in html
    assert "<script>bad</script>" not in html
    assert "Full observed period" in html and "First 30 days" in html
    assert "<ul>" in html and "width: min(100% - 48px, 1760px)" in html

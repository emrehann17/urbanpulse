"""Offline parity, safety, null handling, and full-mode integration tests."""

import json
from dataclasses import asdict

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
import pytest
from streamlit.testing.v1 import AppTest

from config.settings import ROOT
from pipeline import apply_filters, get_data_summary, get_filter_options, load_data
from pipeline.build import build_processed
from pipeline.contract import SCHEMA
from pipeline.filters import FilterSpec
from pipeline.query import METRICS, ParquetQuery


@pytest.fixture
def query_file(tmp_path, frame):
    # Synthetic source fixture includes a null category and creation date.
    frame.loc[2, "agency"] = pd.NA
    frame.loc[2, "complaint_type"] = pd.NA
    schema = SCHEMA.with_metadata(
        {
            b"urbanpulse": json.dumps(
                {
                    "schema_version": "1.0.0",
                    "mode": "smoke",
                    "sampling": "synthetic test fixture",
                }
            ).encode()
        }
    )
    path = tmp_path / "quoted ' directory" / "requests.parquet"
    path.parent.mkdir()
    pq.write_table(pa.Table.from_pandas(frame, schema=schema, preserve_index=False), path)
    return path, frame


@pytest.mark.parametrize(
    "kwargs",
    [
        {},
        {"borough": None},
        {"borough": "All"},
        {"borough": ["All", "Brooklyn"]},
        {"borough": "Manhattan"},
        {"borough": ["Manhattan", "Queens"]},
        {"borough": []},
        {"borough": "Atlantis"},
        {"complaint_type": "Other"},
        {"agency": "TEST"},
        {"agency": ("OTHER", "TEST")},
        {"agency": []},
        {"agency": "' OR TRUE --"},
        {"start_date": "2025-01-01", "end_date": "2025-01-01"},
        {"start_date": "2025-02-01", "end_date": "2025-02-01"},
        {"end_date": "2025-02-02T02:00:00Z"},
        {"start_date": "2026-01-01"},
        {
            "borough": "Brooklyn",
            "agency": ["OTHER"],
            "complaint_type": "Other",
            "start_date": "2025-02-01",
            "end_date": "2025-02-01",
        },
        {"borough": "Manhattan", "agency": "OTHER"},
    ],
)
def test_filter_population_parity(query_file, kwargs):
    path, source = query_file
    query = ParquetQuery(path)
    spec = FilterSpec(**kwargs)
    expected = apply_filters(source, **kwargs)
    actual = query.preview(SCHEMA.names, filters=spec, limit=100)
    assert query.count(filters=spec) == len(expected)
    assert query.summary(filters=spec) == get_data_summary(expected)
    assert set(actual.unique_key) == set(expected.unique_key)
    pd.testing.assert_frame_equal(
        actual.sort_values("unique_key").reset_index(drop=True),
        expected.sort_values("unique_key").reset_index(drop=True),
    )
    assert query.aggregate("borough", filters=spec).requests.sum() == len(expected)


def test_filter_options_and_date_errors(query_file):
    path, frame = query_file
    assert ParquetQuery(path).filter_options() == get_filter_options(frame)
    for kwargs in ({"start_date": "bad"}, {"start_date": "2025-12-01", "end_date": "2025-01-01"}):
        with pytest.raises(ValueError):
            FilterSpec(**kwargs)
        with pytest.raises(ValueError):
            apply_filters(frame, **kwargs)
    spec = FilterSpec(borough=["All"], agency=[])
    assert spec.borough is None and spec.agency == ()
    assert len(apply_filters(frame, **asdict(spec))) == 0


@pytest.mark.parametrize(
    "groups",
    [
        "borough",
        "created_day",
        "complaint_type",
        ["agency", "complaint_type"],
        "boro_cd",
        "closure_event",
    ],
)
def test_aggregates_keep_null_groups_and_respect_filters(query_file, groups):
    path, source = query_file
    query = ParquetQuery(path)
    for spec in (FilterSpec(), FilterSpec(borough=["Brooklyn", "Queens"])):
        expected = apply_filters(source, **asdict(spec))
        actual = query.aggregate(groups, filters=spec, metrics=("requests", "valid_closures"))
        group_names = [groups] if isinstance(groups, str) else groups
        pandas_counts = (
            expected.groupby(group_names, dropna=False).size().reset_index(name="requests")
        )
        assert actual.requests.sum() == len(expected)
        pd.testing.assert_frame_equal(
            actual[group_names + ["requests"]].sort_values(group_names).reset_index(drop=True),
            pandas_counts.sort_values(group_names).reset_index(drop=True),
            check_dtype=False,
        )
        assert actual.valid_closures.sum() == expected.closure_hours.notna().sum()


def test_denominators_and_unknowns(query_file):
    path, _ = query_file
    query = ParquetQuery(path)
    row = query.aggregate(metrics=tuple(METRICS)).iloc[0]
    assert (row.requests, row.closed, row.censored, row.unknown_outcomes) == (3, 1, 1, 1)
    assert (row.valid_closures, row.closure_mean_hours, row.closure_min_hours) == (1, 24, 24)
    assert (row.known_long_labels, row.long_closures, row.long_closure_rate) == (2, 1, 0.5)
    unknown = query.aggregate(metrics=tuple(METRICS), filters=FilterSpec(borough="Queens")).iloc[0]
    assert unknown.requests == 1 and unknown.unknown_outcomes == 1
    assert pd.isna(unknown.closure_mean_hours) and pd.isna(unknown.long_closure_rate)
    empty = query.aggregate(metrics=tuple(METRICS), filters=FilterSpec(borough=[])).iloc[0]
    assert empty.requests == 0 and pd.isna(empty.closure_mean_hours)
    assert query.aggregate("borough", filters=FilterSpec(borough=[])).empty
    assert set(query.aggregate(metrics=("closure_mean_hours",)).columns) == {
        "closure_mean_hours",
        "requests",
        "valid_closures",
    }
    assert set(query.aggregate(metrics=("long_closure_rate",)).columns) == {
        "long_closure_rate",
        "requests",
        "known_long_labels",
        "long_closures",
    }


@pytest.mark.parametrize(
    "columns", [[], ["not_a_column"], ["borough", "borough"], ['borough"; DROP TABLE x; --']]
)
def test_unsafe_projection_rejected(query_file, columns):
    with pytest.raises(ValueError):
        ParquetQuery(query_file[0]).preview(columns)


def test_safe_group_and_metric_names(query_file):
    query = ParquetQuery(query_file[0])
    for groups, metrics in [
        ("borough; SELECT 1", ("requests",)),
        ("borough", ("sum(status)",)),
        ("borough", ()),
        ("borough", ("requests", "requests")),
    ]:
        with pytest.raises(ValueError):
            query.aggregate(groups, metrics=metrics)


@pytest.mark.parametrize("limit", [-1, 10001, None, True, "100"])
def test_invalid_limit(query_file, limit):
    with pytest.raises(ValueError, match="limit"):
        ParquetQuery(query_file[0]).preview(["unique_key"], limit=limit)


def test_preview_limits_projection_and_memory_guard(query_file, monkeypatch):
    query = ParquetQuery(query_file[0])
    assert query.preview(["unique_key"], limit=0).empty
    assert query.preview(["unique_key"], limit=1).unique_key.tolist() == ["000123"]
    assert query.preview(["unique_key"], limit=2).columns.tolist() == ["unique_key"]
    monkeypatch.setattr("pipeline.query.MAX_GROUPS", 1)
    with pytest.raises(ValueError, match="Too many aggregate"):
        query.aggregate("unique_key")


def test_schema_version_paths_and_snapshot_guard(query_file, tmp_path, monkeypatch):
    path, _ = query_file
    import pipeline.loader as loader

    monkeypatch.setattr(loader, "DATA_DIR", path.parent)
    monkeypatch.chdir(tmp_path)
    query = ParquetQuery("requests.parquet")
    assert query.count() == 3
    table = pq.read_table(path)
    pq.write_table(table, path)
    with pytest.raises(ValueError, match="Dataset changed"):
        query.count()
    pq.write_table(table.drop(["status"]), path)
    with pytest.raises(ValueError, match="schema differs"):
        ParquetQuery(path)
    pq.write_table(table.replace_schema_metadata({b"urbanpulse": b'{"schema_version":"9"}'}), path)
    with pytest.raises(ValueError, match="schema version"):
        ParquetQuery(path)


def test_empty_artifact(query_file):
    path, _ = query_file
    table = pq.read_table(path).slice(0, 0)
    pq.write_table(table, path)
    query = ParquetQuery(path)
    assert query.count() == 0 and query.preview(["created_date"]).empty
    assert query.filter_options()["start_date"] is None
    assert query.summary() == get_data_summary(load_data(path))


def test_full_app_uses_sql_not_loader(tmp_path, raw_run, monkeypatch):
    import pipeline
    import pipeline.loader as loader

    monkeypatch.setattr(loader, "DATA_DIR", tmp_path)
    manifest_path = raw_run / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    # Explicitly synthetic full-mode fixture; no genuine full dataset is claimed.
    manifest["config"]["mode"] = "full"
    manifest_path.write_text(json.dumps(manifest))
    build_processed(raw_run, tmp_path / "processed" / "requests.parquet")

    def reject(*args, **kwargs):
        raise AssertionError("Full mode must not call the DataFrame loader")

    monkeypatch.setattr(pipeline, "load_data", reject)
    monkeypatch.setattr(pq, "read_table", reject)
    app = AppTest.from_file(str(ROOT / "app.py"), default_timeout=20).run()
    app.sidebar.selectbox[0].set_value("full").run()
    assert not app.exception and app.metric[0].value == "2"
    assert len(app.dataframe[0].value) == 2
    app.sidebar.multiselect[0].set_value([]).run()
    assert not app.exception and app.metric[0].value == "0"
    assert any("No records" in item.value for item in app.info)


def test_real_demo_summary_and_projection_parity():
    df = load_data()
    query = ParquetQuery()
    assert query.summary() == get_data_summary(df)
    spec = FilterSpec(borough="Brooklyn")
    assert query.count(filters=spec) == len(apply_filters(df, borough="Brooklyn"))
    assert query.filter_options() == get_filter_options(df)


def test_query_failure_is_clear_and_cleans_temp_directory(query_file, monkeypatch):
    from pathlib import Path

    import duckdb

    directories = []

    def fail_connect(*, config):
        directories.append(Path(config["temp_directory"]))
        raise duckdb.OutOfMemoryException("synthetic memory exhaustion")

    monkeypatch.setattr(duckdb, "connect", fail_connect)
    with pytest.raises(ValueError, match="Parquet query failed"):
        ParquetQuery(query_file[0]).count()
    assert directories and not directories[0].exists()


def test_invalid_filter_object_does_not_disable_filters(query_file):
    with pytest.raises(TypeError, match="FilterSpec"):
        ParquetQuery(query_file[0]).count(filters={})

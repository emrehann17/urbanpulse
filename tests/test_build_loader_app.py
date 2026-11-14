"""Offline end-to-end integration with synthetic raw data and Streamlit AppTest."""

import json
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from config.settings import ROOT
from pipeline import load_data
from pipeline.build import build_processed
from pipeline.ingest import write_json
from pipeline.quality import check_parquet


def test_build_deduplication_loading_and_quality(tmp_path, raw_run):
    output = tmp_path / "requests.parquet"
    report = build_processed(raw_run, output)
    assert report["downloaded_rows"] == 4 and report["processed_rows"] == 2
    assert report["excluded_rows"] == {"missing_unique_key": 1, "duplicate_unique_key": 1}
    df = load_data(output)
    assert len(df) == 2 and df.unique_key.is_unique
    assert df.attrs["urbanpulse"]["mode"] == "smoke"
    assert check_parquet(output)["validation"] == "passed"
    assert output.with_suffix(".quality.json").is_file()


def test_incomplete_run_is_rejected(tmp_path, raw_run):
    path = raw_run / "manifest.json"
    manifest = json.loads(path.read_text())
    manifest["complete"] = False
    write_json(path, manifest)
    with pytest.raises(ValueError, match="incomplete"):
        build_processed(raw_run, tmp_path / "out.parquet")


def test_paths_and_full_mode_guard(tmp_path, raw_run, monkeypatch):
    import pipeline.loader as loader

    monkeypatch.setattr(loader, "DATA_DIR", tmp_path)
    output = tmp_path / "processed" / "requests.parquet"
    build_processed(raw_run, output)
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    monkeypatch.chdir(elsewhere)
    assert len(load_data(Path("processed") / "requests.parquet")) == 2
    assert loader.data_path("full") == output
    with pytest.raises(ValueError, match="sample"):
        load_data(dataset="full")
    with pytest.raises(FileNotFoundError, match="Dataset not found"):
        load_data(dataset="demo")
    with pytest.raises(ValueError, match="dataset must"):
        load_data(dataset="unknown")


def test_app_filters_and_missing_data(tmp_path, raw_run, monkeypatch):
    import pipeline.loader as loader

    monkeypatch.setattr(loader, "DATA_DIR", tmp_path)
    build_processed(raw_run, tmp_path / "demo" / "requests.parquet")
    app = AppTest.from_file(str(ROOT / "app.py"), default_timeout=15).run()
    assert not app.exception and app.warning
    assert app.metric[0].value == "2"
    assert len(app.dataframe[0].value) == 2
    assert len(app.get("plotly_chart")) == 3
    app.sidebar.multiselect[0].set_value([]).run()
    assert not app.exception and app.metric[0].value == "0"
    assert any("No records" in item.value for item in app.info)
    app.sidebar.selectbox[0].set_value("full").run()
    assert not app.exception and app.error


def test_failed_build_preserves_previous_artifact(tmp_path, raw_run):
    output = tmp_path / "requests.parquet"
    build_processed(raw_run, output)
    previous = output.read_bytes()
    (raw_run / "page-000001.jsonl").write_text("corrupted", encoding="utf-8")
    with pytest.raises(ValueError, match="checksum"):
        build_processed(raw_run, output)
    assert output.read_bytes() == previous
    assert len(load_data(output)) == 2


def test_version_and_column_drift_rejected(tmp_path, raw_run):
    import pyarrow.parquet as pq

    output = tmp_path / "requests.parquet"
    build_processed(raw_run, output)
    table = pq.read_table(output)
    pq.write_table(
        table.replace_schema_metadata({b"urbanpulse": b'{"schema_version":"2.0.0"}'}), output
    )
    with pytest.raises(ValueError, match="schema version"):
        load_data(output)
    pq.write_table(table.drop(["agency"]), output)
    with pytest.raises(ValueError, match="schema differs"):
        load_data(output)

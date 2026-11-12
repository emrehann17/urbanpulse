import copy
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from pipeline.geography import DISTRICT_CODES
from visualizations.member3 import load_cluster_results
from visualizations.member3_pca_clusters import CLUSTER_COLORS, create_visualization

ROOT = Path(__file__).resolve().parents[1]
CSV_PATH = ROOT / "ml" / "results" / "district_clusters.csv"
METADATA_PATH = ROOT / "ml" / "results" / "kmeans_metrics.json"


@pytest.fixture
def clusters():
    return pd.read_csv(CSV_PATH, dtype={"boro_cd": "string"})


@pytest.fixture
def metadata():
    with METADATA_PATH.open(encoding="utf-8") as handle:
        return json.load(handle)


def test_pca_scatter_contains_all_districts_and_saved_coordinates(clusters, metadata):
    fig = create_visualization(clusters, metadata)

    assert len(fig.data) == 2
    assert {trace.name.split(" ·")[0] for trace in fig.data} == {"Cluster 0", "Cluster 1"}
    assert [len(trace.x) for trace in fig.data] == [36, 23]
    assert sum(len(trace.x) for trace in fig.data) == 59
    assert {trace.marker.color for trace in fig.data} == set(CLUSTER_COLORS.values())

    plotted = {
        str(row[0]): (float(x), float(y))
        for trace in fig.data
        for x, y, row in zip(trace.x, trace.y, trace.customdata, strict=True)
    }
    expected = clusters.set_index("boro_cd")[["pca_x", "pca_y"]].apply(tuple, axis=1).to_dict()
    assert plotted.keys() == DISTRICT_CODES
    for code in DISTRICT_CODES:
        assert plotted[code] == pytest.approx(expected[code])


def test_pca_hover_axes_title_and_semantics(clusters, metadata):
    fig = create_visualization(clusters, metadata, subtitle="Reviewed full-year district cohort")

    hover = fig.data[0].hovertemplate
    assert all(
        label in hover
        for label in (
            "Community district",
            "Cluster:",
            "Requests:",
            "Median closure hours:",
            "Beyond-seven-day closure rate:",
        )
    )
    assert "49.70%" in fig.layout.xaxis.title.text
    assert "27.73%" in fig.layout.yaxis.title.text
    assert "precomputed 2025 K-Means model" in fig.layout.title.text
    assert "Reviewed full-year district cohort" in fig.layout.title.text
    assert fig.layout.title.text.count("<br>") == 1
    assert fig.layout.legend.y > 1
    assert fig.layout.margin.t >= 155
    assert "not success" in fig.layout.annotations[0].text
    assert "Plotly.newPlot" in fig.to_html(include_plotlyjs=False)


def test_pca_renderer_preserves_inputs(clusters, metadata):
    original_clusters = clusters.copy(deep=True)
    original_metadata = copy.deepcopy(metadata)

    create_visualization(clusters, metadata)

    pd.testing.assert_frame_equal(clusters, original_clusters)
    assert metadata == original_metadata


def test_pca_axes_work_without_optional_variance_metadata(clusters):
    fig = create_visualization(clusters)

    assert fig.layout.xaxis.title.text == "PCA component 1"
    assert fig.layout.yaxis.title.text == "PCA component 2"


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (lambda frame: frame.drop(columns="pca_x"), "Missing required"),
        (lambda frame: frame.iloc[:-1].copy(), "exactly the 59"),
        (lambda frame: frame.assign(pca_x=np.inf), "finite PCA"),
        (lambda frame: frame.assign(long_closure_rate=1.1), "between zero and one"),
        (lambda frame: frame.assign(cluster_id=2), "cluster IDs 0 and 1"),
    ],
)
def test_pca_rejects_invalid_csv_contract(clusters, metadata, mutation, message):
    with pytest.raises(ValueError, match=message):
        create_visualization(mutation(clusters), metadata)


def test_pca_rejects_metadata_mismatches(clusters, metadata):
    bad_sizes = copy.deepcopy(metadata)
    bad_sizes["cluster_sizes"] = [35, 24]
    with pytest.raises(ValueError, match="cluster sizes"):
        create_visualization(clusters, bad_sizes)

    bad_hash = copy.deepcopy(metadata)
    bad_hash["source"]["parquet_sha256"] = "not-the-reviewed-source"
    with pytest.raises(ValueError, match="source hash"):
        create_visualization(clusters, bad_hash)


def test_streamlit_loader_reads_reviewed_results_and_checks_fingerprints():
    csv_stat = CSV_PATH.stat()
    metadata_stat = METADATA_PATH.stat()
    clusters, metadata = load_cluster_results(
        str(CSV_PATH),
        (csv_stat.st_mtime_ns, csv_stat.st_size),
        str(METADATA_PATH),
        (metadata_stat.st_mtime_ns, metadata_stat.st_size),
    )

    assert len(clusters) == 59
    assert metadata["selected_k"] == 2
    with pytest.raises(ValueError, match="CSV changed"):
        load_cluster_results(
            str(CSV_PATH),
            (0, 0),
            str(METADATA_PATH),
            (metadata_stat.st_mtime_ns, metadata_stat.st_size),
        )

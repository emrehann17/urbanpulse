import copy
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from visualizations.member3_parallel_coordinates import create_visualization

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


def test_parallel_coordinates_contains_all_districts_and_dimensions(clusters, metadata):
    fig = create_visualization(clusters, metadata, subtitle="Reviewed 2025 cohort")

    assert len(fig.data) == 1
    trace = fig.data[0]
    assert trace.type == "parcoords"
    assert len(trace.line.color) == 59
    assert set(trace.line.color) == {0, 1}
    assert len(trace.dimensions) == 8
    assert [dimension.label for dimension in trace.dimensions[:4]] == [
        "District code",
        "Requests",
        "Median closure (h)",
        "Over 7 days (%)",
    ]
    assert "Illegal Parking (%)" in [dimension.label for dimension in trace.dimensions]
    assert "Residential noise (%)" in [dimension.label for dimension in trace.dimensions]
    assert "HEAT/HOT WATER (%)" in [dimension.label for dimension in trace.dimensions]
    assert all("<br>" not in dimension.label for dimension in trace.dimensions)
    assert tuple(trace.domain.x) == (0, 0.88)
    assert tuple(trace.domain.y) == (0.10, 0.68)
    assert trace.labelfont.size == 11
    assert trace.line.colorbar.x <= 0.94
    assert fig.layout.margin.t == 190
    assert fig.layout.meta["district_count"] == 59
    assert "Reviewed 2025 cohort" in fig.layout.title.text
    assert fig.layout.title.text.count("<br>") == 2
    assert "not performance rankings" in fig.layout.annotations[0].text
    assert "Plotly.newPlot" in fig.to_html(include_plotlyjs=False)


def test_parallel_coordinates_preserves_raw_values_and_inputs(clusters, metadata):
    original_clusters = clusters.copy(deep=True)
    original_metadata = copy.deepcopy(metadata)

    fig = create_visualization(clusters, metadata)

    np.testing.assert_allclose(fig.data[0].dimensions[1].values, clusters.request_count)
    np.testing.assert_allclose(
        fig.data[0].dimensions[2].values,
        clusters.median_closure_hours,
    )
    np.testing.assert_allclose(
        fig.data[0].dimensions[3].values,
        clusters.long_closure_rate * 100,
    )
    pd.testing.assert_frame_equal(clusters, original_clusters)
    assert metadata == original_metadata


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (lambda frame: frame.drop(columns="complaint_share_0"), "Missing required"),
        (lambda frame: frame.iloc[:-1].copy(), "exactly the 59"),
        (lambda frame: frame.assign(median_closure_hours=np.nan), "complete finite"),
        (lambda frame: frame.assign(long_closure_rate=1.2), "zero to one"),
        (lambda frame: frame.assign(cluster_id=2), "cluster IDs 0 and 1"),
    ],
)
def test_parallel_coordinates_rejects_invalid_profiles(clusters, metadata, mutation, message):
    with pytest.raises(ValueError, match=message):
        create_visualization(mutation(clusters), metadata)


def test_parallel_coordinates_requires_category_metadata(clusters, metadata):
    invalid = copy.deepcopy(metadata)
    invalid["complaint_categories"].pop("complaint_share_2")

    with pytest.raises(ValueError, match="complaint_share_2"):
        create_visualization(clusters, invalid)

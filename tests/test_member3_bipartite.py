import pandas as pd
import pytest

from visualizations.member3_bipartite import (
    AGENCY_COLOR,
    COMPLAINT_COLOR,
    create_visualization,
)


@pytest.fixture
def network_data():
    return pd.DataFrame(
        {
            "agency": ["NYPD", "NYPD", "HPD", "HPD", "DEP", None],
            "complaint_type": [
                "Illegal Parking",
                "Noise - Residential",
                "HEAT/HOT WATER",
                "UNSANITARY CONDITION",
                "Water System",
                "Unknown",
            ],
            "requests": [100, 40, 80, 20, 30, 5],
        }
    )


def test_bipartite_draws_bounded_edges_nodes_and_coverage(network_data):
    fig = create_visualization(
        network_data,
        subtitle="Brooklyn · 2025",
        max_agencies=3,
        max_complaints=5,
        max_edges=4,
    )

    edge_traces = [trace for trace in fig.data if trace.meta["kind"] == "edge"]
    node_traces = [trace for trace in fig.data if trace.meta["kind"] != "edge"]
    assert len(edge_traces) == 4
    assert len(node_traces) == 2
    assert {trace.marker.color for trace in node_traces} == {AGENCY_COLOR, COMPLAINT_COLOR}
    assert fig.layout.meta["shown_requests"] == 250
    assert fig.layout.meta["total_requests"] == 275
    assert "Brooklyn · 2025" in fig.layout.title.text
    assert "90.9%" in fig.layout.title.text
    assert fig.layout.title.text.count("<br>") == 3
    assert fig.layout.margin.t == 200
    assert fig.layout.margin.l == 150
    assert fig.layout.margin.r == 250
    assert fig.layout.legend.xanchor == "center"
    assert all("Requests:" in trace.text[0] for trace in edge_traces)


def test_bipartite_preserves_input(network_data):
    original = network_data.copy(deep=True)

    create_visualization(network_data)

    pd.testing.assert_frame_equal(network_data, original)


def test_bipartite_handles_empty_and_missing_categories():
    empty = pd.DataFrame(columns=["agency", "complaint_type", "requests"])
    fig = create_visualization(empty)
    assert not fig.data and fig.layout.annotations

    only_missing = pd.DataFrame({"agency": [None], "complaint_type": ["Noise"], "requests": [7]})
    fig = create_visualization(only_missing)
    assert not fig.data
    assert fig.layout.meta["total_requests"] == 7


@pytest.mark.parametrize(
    ("frame", "message"),
    [
        (pd.DataFrame({"agency": ["NYPD"]}), "Missing required"),
        (
            pd.DataFrame({"agency": ["NYPD"], "complaint_type": ["Noise"], "requests": [-1]}),
            "non-negative",
        ),
    ],
)
def test_bipartite_rejects_invalid_data(frame, message):
    with pytest.raises(ValueError, match=message):
        create_visualization(frame)


@pytest.mark.parametrize("value", [0, -1, True, 1.5])
def test_bipartite_rejects_invalid_display_limits(network_data, value):
    with pytest.raises(ValueError, match="positive integer"):
        create_visualization(network_data, max_edges=value)

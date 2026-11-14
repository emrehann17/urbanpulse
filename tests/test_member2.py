import pandas as pd
import pytest

from visualizations.member2_calendar import create_visualization as create_calendar
from visualizations.member2_ridgeline import create_visualization as create_ridgeline
from visualizations.member2_sankey import create_visualization as create_sankey


def test_calendar_places_days_and_reports_unknown_dates():
    daily = pd.DataFrame(
        {"created_day": ["2025-01-01", "2025-01-02", "2025-12-31"], "requests": [4, 0, 8]}
    )
    daily.attrs["unknown_created_day"] = 3

    figure = create_calendar(daily, subtitle="Brooklyn")

    heatmap = figure.data[0]
    assert heatmap.z[2][0] == 4  # Jan 1, 2025 was Wednesday, week 0.
    assert heatmap.z[3][0] == 0
    assert heatmap.z[2][52] == 8
    assert figure.layout.meta["population"] == 12
    assert figure.layout.meta["unknown_created_day"] == 3
    assert "Brooklyn" in figure.layout.title.text


def test_calendar_empty_and_invalid_inputs():
    empty = create_calendar(pd.DataFrame(columns=["created_day", "requests"]))
    assert not empty.data and empty.layout.annotations
    with pytest.raises(ValueError, match="one non-null row"):
        create_calendar(pd.DataFrame({"created_day": [None], "requests": [1]}))


def test_sankey_keeps_exact_edges_and_missing_groups():
    aggregates = pd.DataFrame(
        {
            "agency": ["NYPD", None, "[Missing agency]"],
            "complaint_type": ["Noise", "Noise", None],
            "requests": [11, 3, 5],
        }
    )

    figure = create_sankey(aggregates)

    trace = figure.data[0]
    assert sum(trace.link.value) == 19
    assert len(trace.link.value) == 3
    assert "[Missing agency]" in trace.node.label
    assert figure.layout.meta["requests"] == 19
    assert figure.layout.meta["missing_agency_requests"] == 3
    assert figure.layout.meta["missing_complaint_requests"] == 5


def test_sankey_empty_and_invalid_counts():
    empty = create_sankey(pd.DataFrame(columns=["agency", "complaint_type", "requests"]))
    assert not empty.data and empty.layout.annotations
    with pytest.raises(ValueError, match="non-negative"):
        create_sankey(pd.DataFrame({"agency": ["A"], "complaint_type": ["B"], "requests": [-2]}))


def test_ridgeline_uses_frequency_weights_and_reports_tail():
    frequencies = pd.DataFrame(
        {
            "complaint_type": ["Noise", "Noise", "Heat", "Heat", None],
            "closure_hours": [1.0, 10.0, 2.0, 20.0, 4.0],
            "requests": [98, 2, 50, 50, 100],
        }
    )

    figure = create_ridgeline(frequencies)

    assert len(figure.data) == 2
    assert figure.layout.meta["plotted_complaint_types"] == ["Heat", "Noise"]
    assert figure.layout.meta["valid_closures"] == 200
    assert figure.layout.meta["requests_above_98th_percentile"] >= 0
    assert all(len(trace.x) == len(trace.customdata) for trace in figure.data)


def test_ridgeline_empty_and_rejects_bad_limits():
    empty = create_ridgeline(pd.DataFrame(columns=["complaint_type", "closure_hours", "requests"]))
    assert not empty.data and empty.layout.annotations
    with pytest.raises(ValueError, match="positive integer"):
        create_ridgeline(
            pd.DataFrame({"complaint_type": ["Noise"], "closure_hours": [1], "requests": [1]}),
            max_types=0,
        )

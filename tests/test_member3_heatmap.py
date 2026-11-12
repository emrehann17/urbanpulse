import pandas as pd
import pytest

from visualizations.member3_heatmap import create_visualization


@pytest.fixture
def sample_data():
    return pd.DataFrame(
        {
            "agency": ["NYPD", "NYPD", "HPD", "HPD"],
            "complaint_type": [
                "Illegal Parking",
                "Noise - Residential",
                "HEAT/HOT WATER",
                "Noise - Residential",
            ],
            "requests": [10, 5, 7, 3],
        }
    )


def test_heatmap_has_correct_counts(sample_data):
    fig = create_visualization(sample_data)

    assert len(fig.data) == 1
    assert fig.data[0].type == "heatmap"
    assert fig.data[0].z.sum() == 25


def test_heatmap_preserves_input(sample_data):
    original = sample_data.copy(deep=True)

    create_visualization(sample_data)

    pd.testing.assert_frame_equal(sample_data, original)


def test_heatmap_handles_empty_data():
    empty = pd.DataFrame(columns=["agency", "complaint_type", "requests"])

    fig = create_visualization(empty)

    assert len(fig.data) == 0
    assert len(fig.layout.annotations) > 0


def test_heatmap_rejects_missing_columns():
    invalid = pd.DataFrame({"agency": ["NYPD"]})

    with pytest.raises(ValueError):
        create_visualization(invalid)

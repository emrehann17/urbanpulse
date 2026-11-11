"""Shared filter behavior, inclusive local dates, and dtype preservation."""

import pandas as pd
import pytest

from pipeline import apply_filters, get_filter_options


@pytest.mark.parametrize(
    "kwargs,keys",
    [
        ({"borough": "Manhattan"}, ["000123"]),
        ({"borough": ["Manhattan", "Queens"]}, ["000123", "3"]),
        ({"complaint_type": "Other"}, ["2"]),
        ({"agency": "TEST"}, ["000123", "3"]),
        ({"borough": "All"}, ["000123", "2", "3"]),
        ({"borough": ["All", "Manhattan"]}, ["000123", "2", "3"]),
        ({"agency": []}, []),
        ({"borough": "Unknown"}, []),
        (
            {
                "borough": "Brooklyn",
                "agency": "OTHER",
                "complaint_type": "Other",
                "start_date": "2025-02-01",
                "end_date": "2025-02-01",
            },
            ["2"],
        ),
        ({"borough": "Manhattan", "agency": "OTHER"}, []),
        ({"start_date": "2025-02-01", "end_date": "2025-02-01"}, ["2"]),
        ({"end_date": "2025-01-01"}, ["000123"]),
    ],
)
def test_selections(frame, kwargs, keys):
    before = frame.copy(deep=True)
    actual = apply_filters(frame, **kwargs)
    assert actual.unique_key.tolist() == keys
    pd.testing.assert_series_equal(actual.dtypes, frame.dtypes)
    pd.testing.assert_frame_equal(frame, before)


def test_date_errors_and_timezone(frame):
    with pytest.raises(ValueError, match="start_date"):
        apply_filters(frame, start_date="2025-03-01", end_date="2025-01-01")
    with pytest.raises(ValueError):
        apply_filters(frame, start_date="bad")
    assert len(apply_filters(frame, end_date="2025-01-02T01:00:00Z")) == 1


def test_options(frame):
    assert get_filter_options(frame)["borough"] == ["Brooklyn", "Manhattan", "Queens"]
    assert get_filter_options(frame)["end_date"] == "2025-02-01"
    assert get_filter_options(frame.iloc[:0])["start_date"] is None


def test_result_is_independent(frame):
    result = apply_filters(frame)
    result.loc[0, "agency"] = "Changed"
    assert frame.loc[0, "agency"] == "TEST"

"""All records in these tests are synthetic."""

from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

import pandas as pd
import pytest

from pipeline.contract import validate_schema
from pipeline.features import DURATION_BUCKETS, engineer_features
from pipeline.preprocess import preprocess
from pipeline.quality import get_data_summary, validate_outcomes


def test_identifiers_nulls_and_copy(raw_row, transform):
    source = pd.DataFrame([raw_row])
    before = source.copy(deep=True)
    preprocess(source)
    df = transform([raw_row])
    pd.testing.assert_frame_equal(source, before)
    assert df.unique_key.iloc[0] == "000123"
    assert df.incident_zip.iloc[0] == "00123"
    assert pd.isna(df.descriptor.iloc[0])
    assert str(df.created_date.dtype) == "datetime64[ns, America/New_York]"
    validate_schema(df)


@pytest.mark.parametrize(
    "hours,bucket,long",
    [
        (0, 0, False),
        (24, 0, False),
        (24.01, 1, False),
        (168, 1, False),
        (168.01, 2, True),
        (720, 2, True),
        (720.01, 3, True),
        (9000, 3, True),
    ],
)
def test_duration_boundaries(raw_row, transform, hours, bucket, long):
    origin = datetime.fromisoformat(raw_row["created_date"]).replace(
        tzinfo=ZoneInfo("America/New_York")
    )
    closed = (origin.astimezone(UTC) + timedelta(hours=hours)).astimezone(
        ZoneInfo("America/New_York")
    )
    df = transform([{**raw_row, "closed_date": closed.strftime("%Y-%m-%dT%H:%M:%S")}])
    assert df.closure_hours.iloc[0] == pytest.approx(hours)
    assert df.duration_bucket.iloc[0] == DURATION_BUCKETS[bucket]
    assert bool(df.is_long_closure.iloc[0]) is long
    assert bool(df.duration_outlier.iloc[0]) is (hours > 8760)
    validate_outcomes(df)


@pytest.mark.parametrize("age,label", [(24, None), (168, None), (168.01, True)])
def test_censoring_maturity(raw_row, transform, age, label):
    cutoff = datetime.fromisoformat("2025-01-01T05:00:00Z") + timedelta(hours=age)
    df = transform([{**raw_row, "status": "Open", "closed_date": None}], cutoff=cutoff)
    assert pd.isna(df.closure_hours.iloc[0])
    assert not df.closure_event.iloc[0]
    assert df.observed_hours.iloc[0] == pytest.approx(age)
    assert df.duration_bucket.iloc[0] == DURATION_BUCKETS[4]
    if label is None:
        assert pd.isna(df.is_long_closure.iloc[0])
    else:
        assert df.is_long_closure.iloc[0]


@pytest.mark.parametrize(
    "changes,flag",
    [
        ({"closed_date": "2024-12-31T23:00:00"}, "negative_duration"),
        ({"closed_date": None}, "status_date_inconsistent"),
        ({"status": "Open"}, "status_date_inconsistent"),
        ({"status": None}, "status_date_inconsistent"),
        ({"closed_date": "garbage"}, "invalid_closed_date"),
        ({"created_date": "garbage"}, "invalid_created_date"),
        ({"closed_date": "2027-01-01T00:00:00"}, "after_cutoff"),
        (
            {"created_date": "2027-01-01T00:00:00", "status": "Open", "closed_date": None},
            "after_cutoff",
        ),
    ],
)
def test_invalid_outcomes(raw_row, transform, changes, flag):
    row = transform([{**raw_row, **changes}]).iloc[0]
    assert row[flag]
    assert pd.isna(row.closure_hours)
    assert pd.isna(row.observed_hours)
    assert pd.isna(row.closure_event)
    assert pd.isna(row.is_long_closure)
    assert row.duration_bucket == DURATION_BUCKETS[5]


@pytest.mark.parametrize("value", ["2025-03-09T02:30:00", "2025-11-02T01:30:00"])
def test_dst_unresolvable(raw_row, transform, value):
    row = transform([{**raw_row, "created_date": value}]).iloc[0]
    assert row.dst_unresolved and row.invalid_created_date
    assert pd.isna(row.created_date)
    assert row.created_date_raw == value


@pytest.mark.parametrize(
    "created,closed,hours",
    [
        ("2025-03-09T01:30:00", "2025-03-09T03:30:00", 1),
        ("2025-11-02T00:30:00", "2025-11-02T02:30:00", 3),
    ],
)
def test_dst_elapsed_time(raw_row, transform, created, closed, hours):
    row = transform([{**raw_row, "created_date": created, "closed_date": closed}]).iloc[0]
    assert row.closure_hours == hours
    assert row.created_hour == pd.Timestamp(created).hour


def test_calendar_features(raw_row, transform):
    row = transform([raw_row]).iloc[0]
    assert (
        row.created_day,
        row.created_hour,
        row.created_weekday,
        row.created_month,
        row.created_quarter,
    ) == ("2025-01-01", 0, 2, 1, 1)


@pytest.mark.parametrize(
    "source,expected",
    [
        (" brooklyn ", "Brooklyn"),
        ("THE BRONX", "Bronx"),
        ("staten island", "Staten Island"),
        ("Unspecified", None),
    ],
)
def test_borough_normalization(raw_row, transform, source, expected):
    row = transform([{**raw_row, "borough": source}]).iloc[0]
    assert row.borough_raw == source
    assert pd.isna(row.borough) if expected is None else row.borough == expected


@pytest.mark.parametrize(
    "lat,lon,valid,invalid",
    [
        ("40.75", "-73.98", True, False),
        (None, None, False, False),
        ("0", "0", False, True),
        ("bad", "-74", False, True),
        ("40.75", None, False, True),
        ("inf", "-74", False, True),
    ],
)
def test_coordinates(raw_row, transform, lat, lon, valid, invalid):
    row = transform([{**raw_row, "latitude": lat, "longitude": lon}]).iloc[0]
    assert bool(row.has_valid_coordinates) is valid
    assert bool(row.invalid_coordinates) is invalid
    if not valid:
        assert pd.isna(row.latitude) and pd.isna(row.longitude)


def test_duplicate_flags_and_schema_failures(raw_row, transform):
    df = transform([raw_row, raw_row])
    assert df.is_duplicate_key.all()
    with pytest.raises(ValueError, match="unique keys"):
        validate_schema(df)
    with pytest.raises(ValueError, match="Missing contract"):
        validate_schema(df.drop(columns="agency"))
    df = transform([raw_row])
    df["unique_key"] = 123
    with pytest.raises(ValueError, match="expected string"):
        validate_schema(df)


def test_cutoff_requires_timezone(raw_row):
    with pytest.raises(ValueError, match="timezone"):
        engineer_features(preprocess(pd.DataFrame([raw_row])), cutoff="2026-01-01")


def test_summary_empty(frame):
    summary = get_data_summary(frame.iloc[:0])
    assert summary["rows"] == 0 and summary["created_min"] is None


def test_corrupt_target_rejected(frame):
    frame.loc[0, "is_long_closure"] = True  # Synthetic 24-hour event must be negative.
    with pytest.raises(ValueError, match="invariants"):
        validate_outcomes(frame)


def test_blank_and_offset_timestamp_policy(raw_row, transform):
    df = transform([{**raw_row, "descriptor": "  ", "created_date": "2025-01-01T00:00:00Z"}])
    assert pd.isna(df.descriptor.iloc[0])
    assert df.invalid_created_date.iloc[0]
    assert df.created_date_raw.iloc[0].endswith("Z")

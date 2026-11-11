"""Versioned Arrow schema and pandas types; all consumers share this contract."""

import pandas as pd
import pyarrow as pa

from config.settings import DATE_FIELDS, RAW_FIELDS, TIMEZONE

AUDIT_FIELDS = tuple(f"{name}_raw" for name in (*DATE_FIELDS, "borough", "latitude", "longitude"))
FLAG_FIELDS = (
    "is_duplicate_key",
    "missing_unique_key",
    "dst_unresolved",
    "invalid_created_date",
    "invalid_closed_date",
    "invalid_resolution_action_updated_date",
    "invalid_borough",
    "has_valid_coordinates",
    "invalid_coordinates",
    "negative_duration",
    "status_date_inconsistent",
    "after_cutoff",
    "duration_outlier",
    "board_borough_mismatch",
)
STRING_FIELDS = (
    tuple(n for n in RAW_FIELDS if n not in (*DATE_FIELDS, "latitude", "longitude"))
    + AUDIT_FIELDS
    + (
        "schema_version",
        "created_day",
        "duration_bucket",
        "boro_cd",
        "geography_status",
    )
)
FLOAT_FIELDS = ("latitude", "longitude", "closure_hours", "observed_hours")
INTEGER_FIELDS = ("created_hour", "created_weekday", "created_month", "created_quarter")
BOOLEAN_FIELDS = FLAG_FIELDS + ("is_closed", "closure_event", "is_long_closure")
SCHEMA = pa.schema(
    [pa.field(n, pa.string(), nullable=n != "unique_key") for n in STRING_FIELDS]
    + [pa.field(n, pa.timestamp("ns", tz=TIMEZONE)) for n in DATE_FIELDS]
    + [pa.field("extraction_cutoff", pa.timestamp("ns", tz="UTC"))]
    + [pa.field(n, pa.float64()) for n in FLOAT_FIELDS]
    + [pa.field(n, pa.int64()) for n in INTEGER_FIELDS]
    + [pa.field(n, pa.bool_()) for n in BOOLEAN_FIELDS]
)


def standardize_types(df: pd.DataFrame) -> pd.DataFrame:
    """Return contract column order and nullable pandas extension dtypes."""
    missing = set(SCHEMA.names) - set(df.columns)
    if missing:
        raise ValueError(f"Missing contract columns: {sorted(missing)}")
    result = df.loc[:, SCHEMA.names].copy()
    for fields, dtype in (
        (STRING_FIELDS, "string"),
        (FLOAT_FIELDS, "Float64"),
        (INTEGER_FIELDS, "Int64"),
        (BOOLEAN_FIELDS, "boolean"),
    ):
        result[list(fields)] = result[list(fields)].astype(dtype)
    return result


def validate_schema(df: pd.DataFrame) -> None:
    """Reject missing columns, dtype drift, null IDs, and duplicate IDs."""
    missing = set(SCHEMA.names) - set(df.columns)
    if missing:
        raise ValueError(f"Missing contract columns: {sorted(missing)}")
    for fields, expected in (
        (STRING_FIELDS, "string"),
        (FLOAT_FIELDS, "Float64"),
        (INTEGER_FIELDS, "Int64"),
        (BOOLEAN_FIELDS, "boolean"),
    ):
        for name in fields:
            if str(df[name].dtype) != expected:
                raise ValueError(f"{name}: expected {expected}, got {df[name].dtype}")
    for name, timezone in [*((n, TIMEZONE) for n in DATE_FIELDS), ("extraction_cutoff", "UTC")]:
        if str(df[name].dtype) != f"datetime64[ns, {timezone}]":
            raise ValueError(f"{name}: wrong datetime timezone or precision")
    if df.unique_key.isna().any() or df.unique_key.duplicated().any():
        raise ValueError("Contract requires non-null unique keys")

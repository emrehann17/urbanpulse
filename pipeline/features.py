"""Creation-time features and conservative closure/censoring outcomes."""

import pandas as pd

from config.settings import SCHEMA_VERSION

DURATION_BUCKETS = (
    "Closed within 24 hours",
    "Closed after 24 hours and within 7 days",
    "Closed after 7 days and within 30 days",
    "Closed after 30 days",
    "Still open / censored",
    "Unknown or invalid",
)
CREATION_FEATURES = (
    "borough",
    "community_board",
    "complaint_type",
    "descriptor",
    "agency",
    "open_data_channel_type",
    "location_type",
    "created_hour",
    "created_weekday",
    "created_month",
    "created_quarter",
)


def engineer_features(clean: pd.DataFrame, *, cutoff: str | pd.Timestamp) -> pd.DataFrame:
    """Add outcomes as of an explicit timezone-aware extraction-start cutoff.

    Inconsistent/invalid records have unknown outcomes. ``is_long_closure`` is
    nullable: completed durations >168 hours and mature open observations >168
    hours are positive; immature open observations are not assigned negatives.
    """
    cutoff = pd.Timestamp(cutoff)
    if cutoff.tzinfo is None:
        raise ValueError("cutoff must include a timezone")
    df = clean.copy()
    df["schema_version"] = pd.Series(SCHEMA_VERSION, index=df.index, dtype="string")
    df["extraction_cutoff"] = pd.Series(
        cutoff.tz_convert("UTC"), index=df.index, dtype="datetime64[ns, UTC]"
    )
    df["is_closed"] = df.status.str.strip().str.casefold().eq("closed").astype("boolean")
    df["after_cutoff"] = (df.created_date > cutoff) | (df.closed_date > cutoff)
    valid = (
        df.created_date.notna()
        & ~df.negative_duration
        & ~df.status_date_inconsistent
        & ~df.after_cutoff
        & ~df.invalid_closed_date
    )
    event = valid & df.is_closed.fillna(False) & df.closed_date.notna()
    censored = valid & df.is_closed.eq(False).fillna(False) & df.closed_date_raw.isna()
    hours = (df.closed_date - df.created_date).dt.total_seconds() / 3600
    df["closure_hours"] = hours.where(event).astype("Float64")
    df["observed_hours"] = pd.Series(pd.NA, index=df.index, dtype="Float64")
    df.loc[event, "observed_hours"] = df.loc[event, "closure_hours"]
    df.loc[censored, "observed_hours"] = (
        cutoff - df.loc[censored, "created_date"]
    ).dt.total_seconds() / 3600
    df["closure_event"] = pd.Series(pd.NA, index=df.index, dtype="boolean")
    df.loc[event, "closure_event"] = True
    df.loc[censored, "closure_event"] = False
    df["is_long_closure"] = pd.Series(pd.NA, index=df.index, dtype="boolean")
    df.loc[event, "is_long_closure"] = df.loc[event, "closure_hours"] > 168
    df.loc[censored & df.observed_hours.gt(168).fillna(False), "is_long_closure"] = True
    df["duration_bucket"] = pd.Series(DURATION_BUCKETS[5], index=df.index, dtype="string")
    df.loc[censored, "duration_bucket"] = DURATION_BUCKETS[4]
    for mask, label in (
        (event & hours.le(24), DURATION_BUCKETS[0]),
        (event & hours.gt(24) & hours.le(168), DURATION_BUCKETS[1]),
        (event & hours.gt(168) & hours.le(720), DURATION_BUCKETS[2]),
        (event & hours.gt(720), DURATION_BUCKETS[3]),
    ):
        df.loc[mask, "duration_bucket"] = label
    df["duration_outlier"] = df.closure_hours.gt(8760).fillna(False)
    df["created_day"] = df.created_date.dt.strftime("%Y-%m-%d").astype("string")
    for name, values in (
        ("created_hour", df.created_date.dt.hour),
        ("created_weekday", df.created_date.dt.dayofweek),
        ("created_month", df.created_date.dt.month),
        ("created_quarter", df.created_date.dt.quarter),
    ):
        df[name] = values.astype("Int64")
    return df

"""Conservative cleaning: preserve rows, flag uncertainty, retain source audit values."""

import pandas as pd

from config.settings import BOROUGHS, DATE_FIELDS, RAW_FIELDS, TIMEZONE


def preprocess(raw: pd.DataFrame) -> pd.DataFrame:
    """Standardize a raw batch without dropping rows or modifying the caller's data.

    Floating source dates are interpreted as New York wall times. Ambiguous autumn
    and nonexistent spring DST times become NaT rather than invented instants.
    Duplicate flags are batch-local; the build step also checks all pages on disk.
    """
    df = raw.reindex(columns=RAW_FIELDS).copy()
    for name in RAW_FIELDS:
        df[name] = df[name].astype("string").replace(r"^\s*$", pd.NA, regex=True)
    for name in (*DATE_FIELDS, "borough", "latitude", "longitude"):
        df[f"{name}_raw"] = df[name].copy()
    df["is_duplicate_key"] = df.unique_key.notna() & df.unique_key.duplicated(keep=False)
    df["missing_unique_key"] = df.unique_key.isna()
    df["dst_unresolved"] = False
    for name in DATE_FIELDS:
        # Reject offset-bearing timestamps: the verified source contract is floating time.
        pattern = r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?"
        source = df[name].where(df[name].str.fullmatch(pattern, na=False))
        parsed = pd.to_datetime(source, format="ISO8601", errors="coerce")
        localized = parsed.dt.tz_localize(TIMEZONE, ambiguous="NaT", nonexistent="NaT")
        df["dst_unresolved"] |= parsed.notna() & localized.isna()
        df[f"invalid_{name}"] = df[name].notna() & localized.isna()
        df[name] = localized
    df["borough"] = df.borough.str.strip().str.title().replace({"The Bronx": "Bronx"})
    df["invalid_borough"] = ~df.borough.isin(BOROUGHS)
    df.loc[df.invalid_borough, "borough"] = pd.NA
    lat = pd.to_numeric(df.latitude, errors="coerce").astype("Float64")
    lon = pd.to_numeric(df.longitude, errors="coerce").astype("Float64")
    # Conservative NYC envelope, not a point-in-polygon assertion.
    valid = (lat.between(40.45, 40.95) & lon.between(-74.30, -73.65)).fillna(False)
    df["has_valid_coordinates"] = valid
    df["invalid_coordinates"] = (df.latitude.notna() | df.longitude.notna()) & ~valid
    df["latitude"], df["longitude"] = lat.where(valid), lon.where(valid)
    df["negative_duration"] = (df.closed_date < df.created_date).fillna(False)
    closed = df.status.str.strip().str.casefold().eq("closed").fillna(False)
    df["status_date_inconsistent"] = (
        (closed & df.closed_date.isna()) | (~closed & df.closed_date_raw.notna()) | df.status.isna()
    )
    return df

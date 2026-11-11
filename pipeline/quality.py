"""Streamlit-independent summaries, streaming quality metrics, and artifact checks."""

import json
import sqlite3
import tempfile
from collections import Counter
from contextlib import closing
from pathlib import Path

import pandas as pd
import pyarrow.parquet as pq

from config.settings import DATE_FIELDS, SCHEMA_VERSION
from pipeline.contract import FLAG_FIELDS, SCHEMA, standardize_types, validate_schema
from pipeline.features import DURATION_BUCKETS


class QualityAccumulator:
    """Accumulate exact counts and missingness without retaining all source rows."""

    def __init__(self):
        self.rows = 0
        self.missing = Counter()
        self.flags = Counter()
        self.geography = Counter()
        self.boroughs = Counter()
        self.months = Counter()
        self.buckets = Counter()
        self.normalization = Counter()

    def add(self, df: pd.DataFrame) -> None:
        """Add one cleaned batch to measured quality totals."""
        self.rows += len(df)
        self.missing.update({n: int(v) for n, v in df.isna().sum().items()})
        self.flags.update({n: int(df[n].sum()) for n in FLAG_FIELDS})
        self.normalization.update(
            {
                "borough_values_changed": int(df.borough.ne(df.borough_raw).sum()),
                **{f"{name}_parsed": int(df[name].notna().sum()) for name in DATE_FIELDS},
            }
        )
        for counter, name in (
            (self.geography, "geography_status"),
            (self.boroughs, "borough"),
            (self.months, "created_month"),
            (self.buckets, "duration_bucket"),
        ):
            counter.update({str(k): int(v) for k, v in df[name].value_counts().items()})

    def report(self) -> dict:
        """Return JSON-serializable counts with all-record missingness denominators."""
        return {
            "processed_rows": self.rows,
            "missing_counts": dict(self.missing),
            "missing_percent": {
                k: round(100 * v / self.rows, 4) if self.rows else 0.0
                for k, v in self.missing.items()
            },
            "quality_flags": dict(self.flags),
            "normalization_counts": dict(self.normalization),
            "geographic_matches": dict(self.geography),
            "geographic_match_percent": round(
                100 * (self.rows - self.geography.get("unmatched", 0)) / self.rows, 4
            )
            if self.rows
            else 0.0,
            "borough_counts": dict(self.boroughs),
            "month_counts": dict(self.months),
            "duration_buckets": dict(self.buckets),
        }


def get_data_summary(df: pd.DataFrame) -> dict:
    """Summarize any contract DataFrame, including an empty filtered result."""
    return {
        "rows": len(df),
        "unique_requests": int(df.unique_key.nunique()),
        "valid_closures": int(df.closure_hours.notna().sum()),
        "censored": int(df.closure_event.eq(False).sum()),
        "unknown_outcomes": int(df.closure_event.isna().sum()),
        "geographic_matches": int(df.boro_cd.notna().sum()),
        "valid_coordinates": int(df.has_valid_coordinates.sum()),
        "created_min": df.created_day.min() if df.created_day.notna().any() else None,
        "created_max": df.created_day.max() if df.created_day.notna().any() else None,
    }


def validate_outcomes(df: pd.DataFrame) -> None:
    """Check outcome invariants independently of source transformation routines."""
    event = df.closure_event.eq(True).fillna(False)
    censored = df.closure_event.eq(False).fillna(False)
    unknown = df.closure_event.isna()
    mature = censored & df.observed_hours.gt(168).fillna(False)
    checks = (
        df.closure_hours.dropna().ge(0).all(),
        df.observed_hours.dropna().ge(0).all(),
        df.loc[event, "closure_hours"].notna().all(),
        df.loc[~event, "closure_hours"].isna().all(),
        df.loc[event, "closure_hours"].eq(df.loc[event, "observed_hours"]).all(),
        df.loc[censored, "observed_hours"].notna().all(),
        df.loc[unknown, "observed_hours"].isna().all(),
        df.loc[unknown, "is_long_closure"].isna().all(),
        df.loc[censored & df.observed_hours.le(168).fillna(False), "is_long_closure"].isna().all(),
        df.loc[mature, "is_long_closure"].eq(True).fillna(False).all(),
        df.loc[event, "is_long_closure"]
        .eq(df.loc[event, "closure_hours"].gt(168))
        .fillna(False)
        .all(),
        df.loc[event, "is_closed"].eq(True).fillna(False).all(),
        df.loc[censored, "is_closed"].eq(False).fillna(False).all(),
        df.loc[censored, "closed_date_raw"].isna().all(),
        df.loc[event | censored, "created_date"].notna().all(),
        ~df.loc[event | censored, ["negative_duration", "status_date_inconsistent", "after_cutoff"]]
        .any()
        .any(),
        df.loc[censored, "duration_bucket"].eq(DURATION_BUCKETS[4]).all(),
        df.loc[unknown, "duration_bucket"].eq(DURATION_BUCKETS[5]).all(),
        df.duration_bucket.isin(DURATION_BUCKETS).all(),
        df.schema_version.eq(SCHEMA_VERSION).all(),
    )
    if not all(checks):
        raise ValueError("Outcome or schema-version invariants failed")


def check_parquet(path: Path) -> dict:
    """Validate a complete artifact in batches, with a disk-backed global ID audit."""
    accumulator = QualityAccumulator()
    with tempfile.TemporaryDirectory() as temporary:
        with closing(sqlite3.connect(str(Path(temporary) / "keys.sqlite"))) as connection:
            connection.execute("CREATE TABLE keys (key TEXT PRIMARY KEY)")
            with pq.ParquetFile(path) as parquet:
                metadata = parquet.schema_arrow.metadata or {}
                provenance = json.loads(metadata.get(b"urbanpulse", b"{}"))
                if provenance.get("schema_version") != SCHEMA_VERSION:
                    raise ValueError("Unsupported or missing UrbanPulse schema metadata")
                if not parquet.schema_arrow.equals(SCHEMA, check_metadata=False):
                    raise ValueError("Parquet schema differs from the shared contract")
                for batch in parquet.iter_batches(batch_size=10000):
                    df = standardize_types(batch.to_pandas())
                    validate_schema(df)
                    validate_outcomes(df)
                    try:
                        connection.executemany(
                            "INSERT INTO keys VALUES (?)", ((k,) for k in df.unique_key)
                        )
                    except sqlite3.IntegrityError as exc:
                        raise ValueError("Duplicate key across Parquet batches") from exc
                    accumulator.add(df)
    return {
        **accumulator.report(),
        "provenance": provenance,
        "unique_keys": accumulator.rows,
        "duplicate_keys": 0,
        "validation": "passed",
    }

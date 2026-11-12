"""Bounded DuckDB projections and aggregates over a verified immutable snapshot."""

import json
import tempfile
from contextlib import contextmanager

import duckdb
import pandas as pd
import pyarrow.parquet as pq

from config.settings import TIMEZONE
from pipeline.geography import DISTRICT_CODES
from pipeline.ingest import sha256
from pipeline.loader import inspect_data

# Conservative subset of pipeline.features.CREATION_FEATURES; see ML_DESIGN.md.
PREDICTORS = ("open_data_channel_type", "created_hour", "created_weekday", "created_month")
COHORTS = {
    "train": ("2025-01-01", "2025-09-01"),
    "validation": ("2025-09-01", "2025-11-01"),
    "test": ("2025-11-01", "2026-01-01"),
}
VALID_DATE = "created_date IS NOT NULL AND NOT coalesce(invalid_created_date, TRUE)"
DISTRICTS = ",".join(f"'{code}'" for code in sorted(DISTRICT_CODES))
ORDINARY = f"geography_status = 'community_district' AND boro_cd IN ({DISTRICTS})"


def cohort_bounds(cohort):
    """UTC epoch microseconds from NY midnights, without DuckDB ICU downloads."""
    return tuple(pd.Timestamp(day, tz=TIMEZONE).value // 1000 for day in COHORTS[cohort])


class MLData:
    """SQL is internal; callers cannot supply projections or predicates.

    Explicit paths support synthetic tests. The production CLI always uses full
    mode and requires matching on-disk quality/checksum metadata.
    """

    def __init__(self, path=None, *, memory_limit_mb=512):
        self.path, self.provenance = inspect_data(path, dataset="full")
        if type(memory_limit_mb) is not int or memory_limit_mb < 32:
            raise ValueError("memory_limit_mb must be an integer >=32")
        self.memory_limit_mb = memory_limit_mb
        self.fingerprint = self._stat()

    def _stat(self):
        stat = self.path.stat()
        return stat.st_size, stat.st_mtime_ns, stat.st_ino

    def verify_full(self):
        """Hash bytes, match quality provenance, and audit IDs/cutoff in SQL."""
        if self.provenance.get("mode") != "full" or self.provenance.get("sampling") != "none":
            raise ValueError("Final training requires an unsampled full snapshot")
        quality_path = self.path.with_suffix(".quality.json")
        quality = json.loads(quality_path.read_text(encoding="utf-8"))
        digest = sha256(self.path)
        rows = pq.read_metadata(self.path).num_rows
        if quality.get("parquet_sha256") != digest or quality.get("processed_rows") != rows:
            raise ValueError("Full snapshot checksum/row count differs from quality report")
        if quality.get("provenance") != self.provenance:
            raise ValueError("Quality report provenance differs from Parquet")
        audit = self._query(
            "SELECT count(*) AS rows, count(DISTINCT unique_key) AS unique_keys, "
            "count(extraction_cutoff) AS cutoffs, "
            "min(epoch_us(extraction_cutoff)) AS cutoff_min, "
            "max(epoch_us(extraction_cutoff)) AS cutoff_max FROM requests"
        ).iloc[0]
        if audit.rows != rows or audit.unique_keys != rows or audit.cutoffs != rows:
            raise ValueError("Snapshot row/ID/cutoff integrity check failed")
        expected = pd.Timestamp(self.provenance["extraction_cutoff"]).value // 1000
        if any(audit[c] != expected for c in ("cutoff_min", "cutoff_max")):
            raise ValueError("Snapshot contains inconsistent extraction cutoffs")
        return {
            "parquet_sha256": digest,
            "rows": rows,
            "columns": len(pq.read_schema(self.path)),
            "provenance": self.provenance,
            "quality_report_sha256": sha256(quality_path),
        }

    @contextmanager
    def _connection(self):
        if self._stat() != self.fingerprint:
            raise ValueError("Snapshot changed during ML run")
        with tempfile.TemporaryDirectory(prefix="urbanpulse-ml-") as temporary:
            with duckdb.connect(
                config={
                    "memory_limit": f"{self.memory_limit_mb}MB",
                    "threads": 1,
                    "temp_directory": temporary,
                }
            ) as connection:
                connection.read_parquet(str(self.path), hive_partitioning=False).create_view(
                    "requests"
                )
                yield connection
        if self._stat() != self.fingerprint:
            raise ValueError("Snapshot changed during ML query")

    def _query(self, sql, parameters=None):
        with self._connection() as connection:
            return connection.execute(sql, parameters or []).df()

    def district_profiles(self, *, top_n=8):
        if not 1 <= top_n <= 20:
            raise ValueError("top_n must be in 1..20")
        categories = self._query(
            f"SELECT complaint_type FROM requests WHERE {ORDINARY} "
            "AND complaint_type IS NOT NULL GROUP BY complaint_type "
            "ORDER BY count(*) DESC, complaint_type LIMIT ?",
            [top_n],
        ).complaint_type.tolist()
        counts = ", ".join(
            f"count(*) FILTER (WHERE complaint_type = ?) AS complaint_{i}_count"
            for i in range(len(categories))
        )
        suffix = f", {counts}" if counts else ""
        frame = (
            self._query(
                "SELECT boro_cd, count(*) AS request_count, "
                "count(closure_hours) AS valid_closures, "
                "median(closure_hours) AS median_closure_hours, "
                "count(is_long_closure) AS known_long_labels, "
                "count(*) FILTER (WHERE is_long_closure) AS long_closures, "
                "count(*) FILTER (WHERE board_borough_mismatch) AS borough_mismatch_count "
                f"{suffix} FROM requests WHERE {ORDINARY} GROUP BY boro_cd ORDER BY boro_cd",
                categories,
            )
            .set_index("boro_cd")
            .reindex(sorted(DISTRICT_CODES))
        )
        count_columns = [c for c in frame if c.endswith("count")] + [
            "valid_closures",
            "known_long_labels",
            "long_closures",
        ]
        frame[count_columns] = frame[count_columns].fillna(0).astype("int64")
        denominator = frame.request_count.replace(0, float("nan"))
        for i in range(len(categories)):
            frame[f"complaint_share_{i}"] = frame.pop(f"complaint_{i}_count") / denominator
        shares = [f"complaint_share_{i}" for i in range(len(categories))]
        frame["complaint_share_other"] = (1 - frame[shares].sum(axis=1)).where(denominator.notna())
        frame["long_closure_rate"] = frame.long_closures / frame.known_long_labels.replace(
            0, float("nan")
        )
        exclusions = self._query(
            f"SELECT CASE WHEN {ORDINARY} THEN 'ordinary' "
            "WHEN geography_status = 'joint_interest_area' THEN 'joint_interest_area' "
            "ELSE 'unmatched_or_invalid' END AS geography, count(*) AS requests "
            "FROM requests GROUP BY geography ORDER BY geography"
        )
        return frame.reset_index(), {
            "complaint_categories": dict(zip(shares, categories, strict=True)),
            "geography_counts": dict(zip(exclusions.geography, exclusions.requests, strict=True)),
            "window": "Entire verified 2025 source scope, including invalid dates in volume",
        }

    def cohort_audit(self):
        """Disjoint exclusions plus overlapping unknown-target total."""
        buckets = f"CASE WHEN NOT ({VALID_DATE}) THEN 'invalid_created_date' "
        for name in COHORTS:
            start, stop = cohort_bounds(name)
            buckets += (
                f"WHEN epoch_us(created_date) >= {start} "
                f"AND epoch_us(created_date) < {stop} THEN '{name}' "
            )
        buckets += "ELSE 'outside_2025' END"
        rows = self._query(
            f"SELECT {buckets} AS cohort, count(*) AS rows, "
            "count(is_long_closure) AS known_labels, "
            "count(*) - count(is_long_closure) AS unknown_labels, "
            "count(*) FILTER (WHERE is_long_closure) AS positives "
            "FROM requests GROUP BY cohort ORDER BY cohort"
        )
        audit = {
            r["cohort"]: {k: int(v) for k, v in r.items() if k != "cohort"}
            for r in rows.to_dict("records")
        }
        for name in (*COHORTS, "invalid_created_date", "outside_2025"):
            audit.setdefault(
                name, {"rows": 0, "known_labels": 0, "unknown_labels": 0, "positives": 0}
            )
        return audit

    def sample(self, cohort, *, limit, seed):
        """Exact-size bottom SHA256 sample; label-independent, no class balancing."""
        if cohort not in COHORTS or type(limit) is not int or not 1 <= limit <= 1_000_000:
            raise ValueError("Known cohort and integer sample limit in 1..1000000 required")
        start, stop = cohort_bounds(cohort)
        projection = ", ".join((*PREDICTORS, "is_long_closure"))
        return self._query(
            f"SELECT {projection} FROM requests WHERE {VALID_DATE} "
            "AND epoch_us(created_date) >= ? "
            "AND epoch_us(created_date) < ? AND is_long_closure IS NOT NULL "
            "ORDER BY sha256(CAST(? AS VARCHAR) || ':' || unique_key), unique_key LIMIT ?",
            [start, stop, seed, limit],
        )

    def predictor_availability(self):
        return (
            self._query(
                "SELECT "
                + ", ".join(
                    f"count(*) - count({c}) AS {c}_missing, count(DISTINCT {c}) AS {c}_distinct"
                    for c in PREDICTORS
                )
                + " FROM requests"
            )
            .iloc[0]
            .astype(int)
            .to_dict()
        )

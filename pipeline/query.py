"""Bounded, parameterized DuckDB queries over local contract Parquet artifacts.

No database server, SQL supplied by callers, or unconditional full DataFrame load.
Run the offline quality command before serving a newly built artifact.
"""

import tempfile
from contextlib import contextmanager
from pathlib import Path

import duckdb
import pandas as pd

from config.settings import DATE_FIELDS, TIMEZONE
from pipeline.contract import BOOLEAN_FIELDS, FLOAT_FIELDS, INTEGER_FIELDS, SCHEMA, STRING_FIELDS
from pipeline.filters import FilterSpec
from pipeline.loader import inspect_data

MAX_PREVIEW_ROWS = 10000
MAX_GROUPS = 100000
# All SQL expressions are maintained in code, never supplied by callers.
METRICS = {
    "requests": "count(*)",
    "valid_closures": 'count("closure_hours")',
    "closed": 'count(*) FILTER (WHERE "closure_event" = TRUE)',
    "censored": 'count(*) FILTER (WHERE "closure_event" = FALSE)',
    "unknown_outcomes": 'count(*) FILTER (WHERE "closure_event" IS NULL)',
    "closure_mean_hours": 'avg("closure_hours")',
    "closure_median_hours": 'median("closure_hours")',
    "closure_min_hours": 'min("closure_hours")',
    "closure_max_hours": 'max("closure_hours")',
    "known_long_labels": 'count("is_long_closure")',
    "long_closures": 'count(*) FILTER (WHERE "is_long_closure" = TRUE)',
    "long_closure_rate": (
        'count(*) FILTER (WHERE "is_long_closure" = TRUE)::DOUBLE '
        '/ nullif(count("is_long_closure"), 0)'
    ),
}
SUMMARY = {
    "rows": "count(*)",
    "unique_requests": 'count(DISTINCT "unique_key")',
    "valid_closures": METRICS["valid_closures"],
    "censored": METRICS["censored"],
    "unknown_outcomes": METRICS["unknown_outcomes"],
    "geographic_matches": 'count("boro_cd")',
    "valid_coordinates": 'count(*) FILTER (WHERE "has_valid_coordinates" = TRUE)',
    "created_min": 'min("created_day")',
    "created_max": 'max("created_day")',
}


def _names(values, allowed, *, label: str, empty: bool = False) -> tuple[str, ...]:
    names = (values,) if isinstance(values, str) else tuple(values)
    if (not names and not empty) or len(set(names)) != len(names):
        raise ValueError(f"{label} must be nonempty and distinct")
    if any(name not in allowed for name in names):
        raise ValueError(f"Unsupported {label}: {names}")
    return names


def _where(filters: FilterSpec | None) -> tuple[str, list]:
    spec = FilterSpec() if filters is None else filters
    if not isinstance(spec, FilterSpec):
        raise TypeError("filters must be a FilterSpec")
    clauses, values = [], []
    for name in ("borough", "complaint_type", "agency"):
        selected = getattr(spec, name)
        if selected is None:
            continue
        if not selected:
            clauses.append("FALSE")
        else:
            clauses.append(f'"{name}" IN ({", ".join("?" for _ in selected)})')
            values.extend(selected)
    for operator, value in ((">=", spec.start_date), ("<=", spec.end_date)):
        if value is not None:
            clauses.append(f'"created_day" {operator} ?')
            values.append(value)
    return " AND ".join(clauses) or "TRUE", values


def _projected_types(df: pd.DataFrame) -> pd.DataFrame:
    """Restore contract pandas types for only the projected source columns."""
    for fields, dtype in (
        (STRING_FIELDS, "string"),
        (FLOAT_FIELDS, "Float64"),
        (INTEGER_FIELDS, "Int64"),
        (BOOLEAN_FIELDS, "boolean"),
    ):
        for name in set(fields) & set(df.columns):
            df[name] = df[name].astype(dtype)
    for name in set((*DATE_FIELDS, "extraction_cutoff")) & set(df.columns):
        timezone = "UTC" if name == "extraction_cutoff" else TIMEZONE
        df[name] = (
            pd.to_datetime(df[name], utc=True)
            .dt.tz_convert(timezone)
            .astype(f"datetime64[ns, {timezone}]")
        )
    return df


class ParquetQuery:
    """Query one immutable local snapshot with a per-operation embedded connection.

    Footer checks are cheap; global uniqueness/outcomes are validated offline.
    Keep serving artifacts immutable while a session uses them; replacing a file
    invalidates this object's fingerprint and requires constructing a fresh object.
    """

    def __init__(
        self,
        path: str | Path | None = None,
        *,
        dataset: str = "demo",
        memory_limit_mb: int = 512,
        threads: int = 2,
    ):
        self.path, self.provenance = inspect_data(path, dataset=dataset)
        if type(memory_limit_mb) is not int or memory_limit_mb < 32:
            raise ValueError("memory_limit_mb must be an integer >=32")
        if type(threads) is not int or not 1 <= threads <= 16:
            raise ValueError("threads must be an integer in 1..16")
        self.memory_limit_mb, self.threads = memory_limit_mb, threads
        self._fingerprint = self._stat()

    def _stat(self) -> tuple[int, int, int]:
        stat = self.path.stat()
        return stat.st_mtime_ns, stat.st_size, stat.st_ino

    @contextmanager
    def _cursor(
        self, select: str, filters: FilterSpec | None = None, *, suffix: str = "", extra: tuple = ()
    ):
        """Own a bounded connection until its result has been consumed."""
        if self._stat() != self._fingerprint:
            raise ValueError("Dataset changed; create a new ParquetQuery for this snapshot")
        where, values = _where(filters)
        sql = (
            f"SELECT {select} FROM read_parquet(?, hive_partitioning=false) WHERE {where} {suffix}"
        )
        # A fresh connection avoids shared mutable state across Streamlit sessions.
        with tempfile.TemporaryDirectory(prefix="urbanpulse-query-") as temporary:
            try:
                with duckdb.connect(
                    config={
                        "memory_limit": f"{self.memory_limit_mb}MB",
                        "threads": self.threads,
                        "temp_directory": temporary,
                    }
                ) as connection:
                    yield connection.execute(sql, [str(self.path), *values, *extra])
            except duckdb.Error as exc:
                raise ValueError(f"Parquet query failed: {exc}") from exc
        if self._stat() != self._fingerprint:
            raise ValueError("Dataset changed during query; retry against a stable snapshot")

    def _execute(
        self, select: str, filters: FilterSpec | None = None, *, suffix: str = "", extra: tuple = ()
    ) -> pd.DataFrame:
        with self._cursor(select, filters, suffix=suffix, extra=extra) as cursor:
            result = cursor.df()
        result.attrs["urbanpulse"] = dict(self.provenance)
        return result

    @contextmanager
    def survival_counts(self, *, filters: FilterSpec | None = None):
        """Yield an iterator of (borough, hours, events, censored), ordered by time.

        Exact ties are aggregated in SQL. Only valid known outcomes enter the
        life table. Consume inside ``with``; at most 4,096 tuples are fetched at
        once, regardless of time cardinality. This bypasses the aggregate output
        cap by streaming, never by truncating the statistical population.
        """
        select = (
            '"borough", "observed_hours", '
            'count(*) FILTER (WHERE "closure_event" = TRUE) AS events, '
            'count(*) FILTER (WHERE "closure_event" = FALSE) AS censored'
        )
        suffix = (
            'AND "closure_event" IS NOT NULL AND "observed_hours" >= 0 '
            'AND isfinite("observed_hours") '
            'GROUP BY "borough", "observed_hours" ORDER BY "borough", "observed_hours"'
        )
        # Parentheses matter: _where builds conjunctions only, so appending AND
        # preserves every existing global predicate, including empty selections.
        with self._cursor(select, filters, suffix=suffix) as cursor:

            def rows():
                while batch := cursor.fetchmany(4096):
                    yield from batch

            yield rows()

    def count(self, *, filters: FilterSpec | None = None) -> int:
        """Return the exact matching row count, with no sampling."""
        return int(self._execute("count(*) AS n", filters).iloc[0, 0])

    def summary(self, *, filters: FilterSpec | None = None) -> dict:
        """Return the same fields/semantics as get_data_summary, computed in SQL."""
        columns = ", ".join(f'{expression} AS "{name}"' for name, expression in SUMMARY.items())
        row = self._execute(columns, filters).iloc[0]
        return {
            name: (None if pd.isna(row[name]) else str(row[name]))
            if name in ("created_min", "created_max")
            else int(row[name])
            for name in SUMMARY
        }

    def filter_options(self) -> dict:
        """Return exact global filter options; excessive category cardinality raises."""
        result = {}
        for name in ("borough", "complaint_type", "agency"):
            frame = self._execute(
                f'DISTINCT "{name}"', suffix=f'ORDER BY "{name}" LIMIT ?', extra=(MAX_GROUPS + 1,)
            )
            if len(frame) > MAX_GROUPS:
                raise ValueError("Too many filter options; design a searchable selector")
            result[name] = sorted(frame[name].dropna().tolist())
        row = self._execute(
            'min("created_day") AS start_date, max("created_day") AS end_date'
        ).iloc[0]
        for name in ("start_date", "end_date"):
            result[name] = None if pd.isna(row[name]) else str(row[name])
        return result

    def aggregate(
        self,
        group_by: str | list[str] | tuple[str, ...] = (),
        *,
        metrics: tuple[str, ...] = ("requests",),
        filters: FilterSpec | None = None,
    ) -> pd.DataFrame:
        """Exact grouped metrics, retaining NULL-key groups and censored/unknown rows.

        SQL avg/min/max ignore null durations; valid_closures is their denominator.
        requests and relevant duration/label denominators are included automatically.
        Results exceeding MAX_GROUPS raise instead of silently truncating.
        """
        groups = _names(group_by, SCHEMA.names, label="group columns", empty=True)
        names = _names(metrics, METRICS, label="metrics")
        denominators = ["requests"]
        if set(names) & {
            "closure_mean_hours",
            "closure_median_hours",
            "closure_min_hours",
            "closure_max_hours",
        }:
            denominators.append("valid_closures")
        if "long_closure_rate" in names:
            denominators.extend(("known_long_labels", "long_closures"))
        names = tuple(dict.fromkeys((*names, *denominators)))
        if set(groups) & set(names):
            raise ValueError("Group and metric names must not overlap")
        quoted = ", ".join(f'"{name}"' for name in groups)
        expressions = ", ".join(f'{METRICS[name]} AS "{name}"' for name in names)
        select = f"{quoted}, {expressions}" if groups else expressions
        suffix = f"GROUP BY {quoted} ORDER BY {quoted} NULLS LAST" if groups else ""
        frame = self._execute(select, filters, suffix=suffix + " LIMIT ?", extra=(MAX_GROUPS + 1,))
        if len(frame) > MAX_GROUPS:
            raise ValueError("Too many aggregate groups; narrow filters or use coarser grouping")
        for name in names:
            is_count = name not in {
                "closure_mean_hours",
                "closure_median_hours",
                "closure_min_hours",
                "closure_max_hours",
                "long_closure_rate",
            }
            frame[name] = frame[name].astype("Int64" if is_count else "Float64")
        return _projected_types(frame)

    def preview(
        self,
        columns: list[str] | tuple[str, ...],
        *,
        filters: FilterSpec | None = None,
        limit: int = 200,
    ) -> pd.DataFrame:
        """Project at most 10,000 ordered rows; a preview is not a random sample.

        Ordering is created_day then unique_key, null dates last. Use aggregates
        for exact statistics, never infer population rates from a limited preview.
        """
        names = _names(columns, SCHEMA.names, label="columns")
        if type(limit) is not int or not 0 <= limit <= MAX_PREVIEW_ROWS:
            raise ValueError(f"limit must be an integer in 0..{MAX_PREVIEW_ROWS}")
        select = ", ".join(f'"{name}"' for name in names)
        frame = self._execute(
            select,
            filters,
            suffix='ORDER BY "created_day" NULLS LAST, "unique_key" LIMIT ?',
            extra=(limit,),
        )
        return _projected_types(frame)

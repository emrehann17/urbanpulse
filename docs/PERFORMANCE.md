# Performance — Phase 1.5 baseline and Phase 2A full data

## Architecture and scope

`pipeline.query.ParquetQuery` uses **DuckDB 1.4.5 LTS** as an embedded engine over
one validated local Parquet file. It does not create a database server or copy
requests into a database. Constructor checks shared footer/schema/provenance;
queries project needed columns and use supported Parquet predicate pushdown.
Read the [DuckDB Parquet documentation](https://duckdb.org/docs/1.4/data/parquet/overview)
and [memory/performance guidance](https://duckdb.org/docs/1.4/guides/performance/how_to_tune_workloads).
The 52-column Parquet contract and existing DataFrame APIs are unchanged.
A local EXPLAIN of the complaint-count query confirmed READ_PARQUET projection
of complaint_type and pushed borough/created_day predicates (Brooklyn, March–June).

FilterSpec supplies the same normalized category selections and inclusive New
York calendar-day bounds to Pandas and SQL. Values, paths, and limits are bound
parameters; SQL expressions and columns come from allowlists. Query methods
return exact counts/aggregates or explicitly limited ordered previews. NULL-key
groups and censored/unknown rows remain in population counts. Duration statistics
have a valid_closures denominator; long-closure rates have a known_long_labels
denominator. No unknown duration is filled with zero.

## Reproduce the measurements

From the repository root, using the project's Python 3.12 environment:

```text
python -m benchmarks.query_benchmark --output benchmarks/local/demo.json
python -m benchmarks.query_benchmark --synthetic-rows 100000 --output benchmarks/local/synthetic.json
```

`--input` can name another Parquet artifact; defaults to the real demo. No API
request or full ingestion occurs. Synthetic data is generated in a temporary
directory, explicitly marked synthetic in its provenance, and deleted afterward.
It repeats demo profiles with artificial unique IDs; it is **not 100,000 genuine
NYC observations**. Only small benchmark JSON reports are committed.

Workers run in separate processes for the two backends. Pandas loads/validates the
complete artifact once (setup time reported separately), then applies filters
and aggregates in memory. DuckDB checks the footer at setup, then opens a fresh
connection for each query. Each operation is repeated three times; tables report
median milliseconds. OS file caches are not flushed; this is not a cold-storage
benchmark. Background host activity is uncontrolled. Pandas queries reapply the
filter per operation; an app that shares an already-filtered frame across several
charts could reduce that cost further.

All workloads filter borough=Brooklyn and created_day inclusively between
2025-01-01 and 2025-12-31. They measure exact filtered count, counts grouped by
borough/day/complaint, and a 200-row projection of unique_key, borough,
complaint_type, closure_hours ordered by created_day and unique_key. Both backend
results are compared exactly before a benchmark report is accepted. The benchmark
does not time full statistical validation in SQL; that remains an offline task.

Memory is worker peak resident memory, including imports and native allocations.
On Linux this uses /proc/self/status VmHWM, which resets on exec so the parent's
synthetic generation is not attributed to a worker. On macOS it uses getrusage;
on Windows memory is recorded as unavailable rather than guessed. This is not a
per-query allocation measurement or a process RAM limit. JSON reports include
baseline peaks, setup times, minimum times, versions, and row-group metadata.

## Historical Phase 1.5 measured results

Measured on November 11, 2026: Ubuntu/WSL2 Linux x86_64, Python 3.12.3,
pandas 2.2.3, PyArrow 19.0.1, DuckDB 1.4.5; 12 logical CPUs reported. DuckDB
used two threads and a 512 MB buffer-manager limit. See the exact platform strings
and timestamps in [demo_results.json](../benchmarks/demo_results.json) and
[synthetic_results.json](../benchmarks/synthetic_results.json).

### Real demo: 2,400 rows

Parquet: 560,131 bytes; 24 row groups. Exact result parity passed.

| Workload | Cached Pandas median ms | Parquet/DuckDB median ms |
| --- | ---: | ---: |
| filtered_count | 4.640 | 17.722 |
| borough | 6.925 | 25.566 |
| created_day | 10.309 | 21.918 |
| complaint_type | 10.091 | 24.032 |
| preview_200 | 17.214 | 23.171 |

| Backend | Setup ms | Process peak RSS MiB |
| --- | ---: | ---: |
| pandas | 98.168 | 166.75 |
| duckdb | 5.460 | 155.04 |

### Synthetic replicated profiles: 100,000 rows

Parquet: 2,853,619 bytes; 10 row groups. Exact result parity passed.

| Workload | Cached Pandas median ms | Parquet/DuckDB median ms |
| --- | ---: | ---: |
| filtered_count | 90.636 | 14.796 |
| borough | 75.188 | 19.562 |
| created_day | 89.320 | 18.846 |
| complaint_type | 73.680 | 25.088 |
| preview_200 | 131.706 | 30.012 |

| Backend | Setup ms | Process peak RSS MiB |
| --- | ---: | ---: |
| pandas | 798.694 | 369.80 |
| duckdb | 1.555 | 153.48 |

Cached Pandas was faster on this tiny demo. DuckDB was faster and used less peak
memory on this synthetic experiment. This is evidence for workload-based API
selection, **not a claim that DuckDB is always faster**. The synthetic data has
only the demo's category/text diversity, compresses readily, and has ten 10,000-row
groups; the demo has 24 100-row groups. These differences also affect timings.
Those Phase 1.5 experiments did not verify performance on millions of real requests;
Phase 2A measurements below now cover the three Member 1 workloads. Neither phase verifies
complex high-cardinality aggregates, concurrent users, or deployment hardware.

## Memory and deployment guidance

- Use load_data/apply_filters for small data and notebooks needing all request rows.
  The full-mode app uses ParquetQuery exclusively for catalog, summary, and preview.
- Each SQL operation gets a fresh connection with two threads and a 512 MB default
  buffer-manager budget; override with memory_limit_mb and threads when measured.
  Some allocations and aggregate state can exceed that budget. See DuckDB's memory
  guidance; do not equate it to a hard total-process ceiling.
- Supported operators may spill to a private temporary directory; ensure OS temp
  storage has space. The directory is removed after closing the connection, including
  failures. Exact distinct counts and high-cardinality grouping can still be costly
  or fail with an out-of-memory error. No automatic sampling fallback occurs.
- At most 10,000 request rows per preview, and at most 100,000 output groups. An
  excessive grouping raises instead of truncating. Group count bounds limit returned
  Pandas objects, not necessarily engine intermediate state. Prefer low-cardinality
  aggregate tables for maps, networks, calendars, and district profiles.
- Full-mode Streamlit caches only catalogs (8 entries) and summaries/200-row previews
  (32 entries), with ten-minute TTL and path/mtime/size fingerprint keys. Connections
  are not cached/shared across users. Multiple concurrent users still multiply query
  memory/thread use. Measure on the intended host before raising concurrency.
- Keep served snapshots immutable. Query objects check mtime, size, and inode before
  and after execution; this detects normal replacements, not every possible race or
  malicious tampering. Build a new artifact and switch paths at a controlled time.
- Run offline quality validation first. Query footer validation intentionally does
  not reread every value or recompute the full checksum per interaction. Retain
  quality reports/manifests and verify checksums when moving artifacts between hosts.
- DuckDB timezone-aware timestamps have microsecond precision; verified source
  timestamps are millisecond precision, and extraction cutoff is microsecond
  precision. Future finer-grained timestamps need Arrow for exact preservation.

## Full ingestion readiness audit

No full download was executed in Phase 1.5. Existing real smoke artifacts were
re-audited locally; deterministic mocked full-mode and interrupted/resume tests
exercise the full code path without live API dependency.

| Capability | Inspection / bounded evidence | Remaining risk |
| --- | --- | --- |
| Deterministic pagination | Composite created_date/lexical unique_key cursor, monthly scope; tie and decreasing-ID tests pass. | Live edits behind the cursor can be missed. |
| Checkpoints/resume | Matching configuration, page SHA-256 and row counts; Phase 1.5 adds cursor/content and completed audit-count comparisons. | Resume validation rereads committed pages, so large resumes can be slow. |
| Unique identifiers | Disk-backed SQLite audit across all pages; builder also excludes/counts missing or repeated IDs. | SQLite disk use and total audit time grow with row count. |
| Partial extraction | Build rejects incomplete manifest; committed pages survive interrupts. | Never manually mark a partial run complete. |
| Memory-bounded build | One raw page/clean batch at a time; fixed Arrow schema; SQLite uniqueness index. | Very large page sizes increase Python string/DataFrame memory. |
| Atomic output | Completed Parquet replaces target after writer closes; failed-build preservation test. | Sidecar report is a separate atomic write; compare checksum after a crash. |
| Metadata and cutoff | Raw schema, page retrieval timestamps, original extraction-start cutoff, manifest and geographic hashes retained. | Long resumed runs combine later states with the original cutoff; after-cutoff outcomes remain unknown. |
| Quality reporting | Raw/clean missingness, exclusions, flags, outcome invariants, joins, source-count difference, final uniqueness. | Equal start/end counts do not prove a transactional snapshot. |
| Query access | Footer validation, projection/predicate pushdown, exact aggregates and bounded previews; parity tests. | Phase 2A chart timings are below; concurrent-user behavior remains unbenchmarked. |

### Disk and row groups

The real smoke JSONL pages total **1,797,289 bytes**, about **748.87 bytes per row**;
its Parquet is **560,131 bytes**. These ratios are illustrative only: full data
text/category distributions and larger row groups can differ substantially. No
full population row count was fetched during Phase 1.5, so no total-size claim is
made. Reserve space for raw pages, schema/manifests, temporary SQLite indexes, the
new Parquet .part file, any previous Parquet, and possible query spill files.
Workspace and temp volume both had about **809.46 GiB free** at the local check;
that is an environment measurement, not a guarantee for another machine.

Portable local preflight:

```text
python -c "from pathlib import Path; import shutil,tempfile; print(shutil.disk_usage(Path.cwd())); print(shutil.disk_usage(tempfile.gettempdir()))"
```

Full-mode default page_size=5000 produces at most 5,000-row Parquet row groups
(one per retained page), with min/max statistics written by Arrow. Date predicates
can skip groups when their bounds permit; borough filters may touch most groups.
Many small row groups increase footer/scan overhead. The existing layout is retained
to avoid unbenchmarked build changes. After measuring a real full snapshot, compare
bounded coalescing into larger row groups or partitioning as a separate reviewed
optimization. Do not assume the demo's tiny groups predict full-dataset behavior.

### Separate full-ingestion command

From the repository root, after ensuring disk space and installing requirements:

```text
python -m pipeline ingest --mode full --page-size 5000
python -m pipeline geography
python -m pipeline build --run-dir data/raw/full --output data/processed/requests.parquet --geography data/geographic/community_districts.geojson
python -m pipeline quality --input data/processed/requests.parquet
python -m streamlit run app.py
```

The full-mode CLI path is covered with mocked data; **these full-download commands
were not run against NYC in Phase 1.5**. Repeat identical ingest arguments to resume.
Use a new --run-dir for a fresh extraction or changed page size. An optional
SOCRATA_APP_TOKEN can improve quotas. Retries handle 429/transient HTTP failures
and read/connect timeouts, but several attempts can take minutes per page. Keep
logs and review source_count_at_start versus downloaded count. Do not run concurrent
writers, and do not treat daily-changing API pages as a transactionally consistent
snapshot. Preserve the original cutoff on resume rather than relabelling outcomes.

## Phase 2A: measured real full-data chart workloads

The earlier Phase 1.5 sections are historical. The full extraction now exists
locally and has passed streaming validation; it was **not** downloaded or rebuilt
by Phase 2A. Details: [DATA_QUALITY.md](DATA_QUALITY.md).

Reproduce without ingestion:

```text
python -m benchmarks.member1_benchmark --dataset full --output benchmarks/local/member1.json
```

The recorded run is [member1_results.json](../benchmarks/member1_results.json),
2026-11-11T14:55:20.712942+00:00, Linux/WSL2 x86_64, Python 3.12.3, DuckDB 1.4.5,
two query threads, 512 MB buffer-manager setting. Parquet: **327,286,299 bytes**,
**737 row groups**, **3,652,435 genuine requests**. No synthetic expansion or
request sampling was used. Three repetitions per workload, fresh embedded
connections, no Streamlit cache; OS caches and host activity are uncontrolled.
Timing includes query and helper transformations, excludes figure construction,
HTML serialization, filter-option loading and the app's diagnostic queries.

| Cohort | District preparation median ms | Daily counts/median/calendar median ms | Exact streamed KM preparation median ms |
| --- | ---: | ---: | ---: |
| All requests, no filters (3,652,435) | 157.077 | 240.319 | 3,981.067 |
| Brooklyn, Jan 1–Mar 31 inclusive (260,034) | 167.939 | 131.955 | 493.830 |

Unrestricted outputs: **59** district rows, **365** calendar rows and **2,977** KM
plotting rows. KM processed **1,287,252** distinct borough/time groups; 2,972 retained
time points plus five origins were stored. All times contribute to exact estimates
and pointwise intervals; omitted display steps are disclosed in the UI. Filtered
Brooklyn Q1 outputs: 59 district rows, 90 days and 978 KM points. Population
reconciliation assertions passed for both cohorts and all three preparations.

Whole benchmark-process peak RSS was **373.91 MiB**, measured using Linux
`/proc/self/status` VmHWM. This includes imports, query operations, all rendering
and six HTML exports; it is not a per-query memory attribution, a cold-start
baseline comparison, or a strict upper memory guarantee. The initial exploratory
run overlapped full validation and was slower (0.557 / 0.623 / 4.173 seconds);
benchmark repetitions above were measured separately. Browser/WebGL memory and
concurrent-user capacity have not been measured. The new measurements cover these
specific workloads only, not all nine future charts or arbitrary full-data SQL.

The daily exact median aggregate keeps observations in engine state; returned
results are small but engine intermediates are not bounded by 365. Survival groups
and sorts high-cardinality times within DuckDB, then fetches batches of 4,096 tuples.
Its Python estimator retains at most 1,024 points per borough by deterministic
**display** thinning. It does not collect millions of observations in Pandas.
The old 100,000-group cap remains for ordinary aggregate DataFrames; the dedicated
context-managed stream avoids truncating survival input. The 52-column artifact,
row groups, preprocessing and historical outcome definitions are unchanged.

Streamlit caches four small chart tables with eight entries and a ten-minute TTL,
using FilterSpec plus Parquet/geography fingerprints. Confidence/trend controls
rerender cached aggregates. Full-request DataFrames and database connections are
not cached. First-time filters still trigger exact scans; budgets multiply across
concurrent sessions. Keep snapshots immutable, preserve spill space, and benchmark
on the deployment host before increasing concurrency or launching all nine charts
at once. Geometry is local and needs no map key or tile service.

The benchmark writes ignored HTML reviews under `benchmarks/local/member1/`, with
embedded Plotly JavaScript and explicit limitations. Their size is dominated by
Plotly/geometry, not raw request rows. See [VISUALIZATION_SPEC.md](VISUALIZATION_SPEC.md)
for the browser review procedure. No native Windows or macOS benchmark is claimed.

# Project status — Phase 1.5 engineering handoff

Updated November 11, 2026. **Phase 1.5 is implemented locally; the full course
assignment is not complete.** The project is now published at
[emrehann17/urbanpulse](https://github.com/emrehann17/urbanpulse). Work began on a
clean `main` branch at `ab86841` (Phase 1). No commits, pushes, remote branch changes,
or remote workflow runs were initiated during Phase 1.5.

## CI diagnosis and repair

The reported Windows Actions failure was `pipx 1.18.12 has requirement
packaging>=26.3, but you have packaging 24.2`. Project installation had succeeded;
`pip check` saw a globally installed runner tool in the same interpreter environment.
The existing Streamlit dependency set permits/pins packaging 24.2. Upgrading project
packages to accommodate the unrelated runner tool would not address isolation.

The workflow now creates `.venv-ci` in **each Ubuntu and Windows job**, uses Python
3.12, and invokes that environment's interpreter explicitly for install, pip check,
Ruff, formatting, and pytest. The matrix selects `./.venv-ci/bin/python` on Ubuntu
and `./.venv-ci/Scripts/python.exe` on Windows. GitHub-hosted runners provide Bash
on both platforms, so no activation script or PowerShell policy change is needed.
An isolation assertion checks sys.prefix/base_prefix and disabled user site packages;
PYTHONNOUSERSITE is set. **pip check remains enabled; packaging remains 24.2.**

The user reports that the earlier Ubuntu workflow passed and Windows failed.
The repaired workflow has **not been run remotely**, and no native Windows run
was available locally. Its isolated Ubuntu equivalent passed below. Further
Windows-specific failures, if any, must be diagnosed from the next actual run.
macOS runtime and package resolution remain unverified.

## Implemented incremental changes

- New `pipeline/query.py`: local DuckDB 1.4.5 LTS queries, parameterized values/paths,
  column/metric allowlists, projected previews, exact counts and grouped metrics,
  NULL-safe duration and label denominators, memory/thread settings, and output caps.
- Shared immutable `FilterSpec` in filters.py. The four existing public functions
  and valid filter semantics remain compatible; Pandas/SQL parity is tested.
- Footer-only `inspect_data()` shared by the original DataFrame loader and query
  layer. Full global quality checks remain offline, not repeated at app startup.
- Full-mode Streamlit now obtains catalog/options, exact summary, and at most 200
  selected preview rows through SQL. Demo/smoke behavior stays in memory. Full-mode
  caches are bounded and fingerprinted; snapshot replacement raises a clear error.
- Ingestion resume now rejects key-audit failures, changed completed audit counts,
  and a saved cursor that disagrees with the corresponding checksummed raw page.
- Reproducible benchmarks with isolated backend processes, exact output comparisons,
  real demo measurements, and a temporary explicitly synthetic 100,000-row experiment.
- Updated README, pipeline/architecture, team guide, derived-query output dictionary,
  decisions, performance/readiness guide, and this status report.

The stored **52-column schema 1.0.0**, source scope, cleaning rules, historical
outcome definitions, demo data, and geographic artifacts are unchanged. No chart,
model training, new full snapshot, or dashboard redesign is included.

## Executed checks

Local runtime: Ubuntu under WSL2, Python **3.12.3**, pandas **2.2.3**, PyArrow
**19.0.1**, Streamlit **1.45.1**, DuckDB **1.4.5**. The initial Phase 1 suite passed
**81 tests** before changes. A fresh `.venv-ci` was then created and installed from
requirements-dev.txt. Network-restricted installation initially could not resolve
packages; approved package-index access completed without changing existing pins.

| Actual command/check | Observed result |
| --- | --- |
| `python3 -m venv .venv-ci` | Fresh isolated environment created. |
| `.venv-ci/bin/python -m pip install -r requirements-dev.txt` | Installation succeeded; only new runtime dependency is DuckDB. |
| Interpreter/user-site/pipx assertions | Venv interpreter, user site disabled, pipx absent. |
| `.venv-ci/bin/python -m pip check` | No broken requirements. |
| `.venv-ci/bin/python -m ruff check .` | Passed. |
| `.venv-ci/bin/python -m ruff format --check .` | 24 Python files formatted. |
| `.venv-ci/bin/python -m pytest -q` | **126 passed in 8.44 seconds** in the final complete suite. |
| Real raw-page audit | 2,400 downloaded/unique, 0 duplicates/missing IDs; checksums/cursors valid. |
| Bounded build into ignored `data/tmp/phase15-smoke.parquet` | 2,400 processed, 0 excluded; original demo untouched. |
| Streaming check_parquet on rebuilt file | Schema, uniqueness, outcomes: passed. |
| README and team guide executable data examples | Executed successfully against the real demo. |
| Real demo Streamlit AppTest | No exceptions; 2,400 overall, 710 Brooklyn, preview agrees with the selected borough. |
| Extra bounded future-input queries | Brooklyn survival frequencies: 662 groups; complaint/duration frequencies: 690 groups. These are input tables, not fitted curves or charts. |
| Real/synthetic benchmark output parity | Passed for all five workloads and both artifacts. |
| EXPLAIN on filtered complaint counts | READ_PARQUET showed column projection and pushed borough/date predicates. |
| Contract/artifact/docs audit | 52 columns, original demo checksum unchanged, local Markdown links valid, git diff --check passed. |

Tests include all pre-existing coverage plus single/combined/All/empty/unknown
filter parity, inclusive dates and timezone conversion, NULL categories/dates,
aggregation denominators, safe identifier rejection, parameter injection attempts,
column projection, row/group caps, empty files, path quoting/CWD independence,
schema/version and snapshot-change guards, query resource-error cleanup, and
completed-checkpoint corruption. Full-mode AppTest explicitly fails if load_data
or pq.read_table is called; SQL counts and previews still render and filters work.
All network behavior in tests is mocked. No NYC API calls are required by CI.

## Benchmark findings

Three repetitions per workload, median latency; cached Pandas setup is reported
separately from query time. DuckDB creates a connection per operation.

| Dataset | Pandas filtered count | DuckDB filtered count | Pandas peak RSS | DuckDB peak RSS |
| --- | ---: | ---: | ---: | ---: |
| Real demo, 2,400 records | 4.640 ms | 17.722 ms | 166.75 MiB | 155.04 MiB |
| **Synthetic**, 100,000 replicated profiles | 90.636 ms | 14.796 ms | 369.80 MiB | 153.48 MiB |

Cached Pandas was faster on the tiny demo; SQL was faster and used less memory in
the synthetic experiment. These are not full-scale guarantees. Synthetic profile
repetition, differing row-group sizes, warm filesystem caches, and uncontrolled
host activity limit generalization. Detailed daily/category/borough/preview results,
methodology, exact versions, and raw JSON reports are in [PERFORMANCE.md](PERFORMANCE.md).
No large benchmark dataset is committed.

## Full ingestion readiness and remaining risks

Full 2025 ingestion is prepared but **not executed**. See
[PERFORMANCE.md](PERFORMANCE.md) for the readiness audit and separate commands.
Resumable pages, SHA-256 checks, disk-backed global ID checks, bounded transforms,
atomic Parquet output, quality reports, and extraction provenance are present.

API throttling/read timeouts and live source changes remain possible. Resume uses
the original observation cutoff; later updates are not silently backdated. Start/end
row-count equality is not proof of a transactional snapshot. Disk space must cover
raw data, SQLite indexes, old/new Parquet, and query spill; local free space is not
a guarantee on deployment machines. Full-mode 5,000-row pages yield relatively small
row groups, which should be benchmarked before changing the build layout.

Queries avoid unconditional full DataFrame loading, but high-cardinality grouping,
exact distinct counts, concurrency, and large row groups can still consume substantial
memory. The 512 MB DuckDB setting is not a hard total-process RAM cap. Unknown/censored
outcomes retain their existing meaning. Future exact survival/density input may
require a reviewed streaming or binning extension if it exceeds the group limit.
Timestamp precision and snapshot-replacement limits are documented in PERFORMANCE.md.

The sample still has 2,388 valid closures, 7 censored, 5 unknown outcomes, and
99.3333% geographic matching; see the unchanged measured [quality report](DATA_QUALITY.md).
It emphasizes early-month/night-time requests and cannot support population estimates.
The current boundary release has not been reconciled against historical 2025 geometry.

## Next steps for the three students

1. Review this local diff, then authorize committing/pushing it and run the repaired
   Ubuntu/Windows workflow. No remote success is claimed here.
2. Execute a separate full ingestion/build/quality audit when disk/time/network
   resources are allocated. Benchmark the real resulting artifact on the deployment host.
3. Use one FilterSpec from the app shell. Small-data charts can keep filtered request
   DataFrames; full-data charts should consume small exact aggregate tables from
   ParquetQuery. Follow [TEAM_GUIDE.md](TEAM_GUIDE.md), including denominator rules.
4. Each student develops three assigned visualizations. Do not implement independent
   ingestion, cleaning, global filters, or ad hoc SQL. Treat previews as previews.
5. Complete historical geography/creation-time feature reviews, future K-Means and
   logistic regression, nine final charts, the English report/presentation, and rubric
   validation before November 15, 2026, 23:59.

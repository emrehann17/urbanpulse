# Project status — Phase 1 engineering handoff

Updated November 11, 2026. **Phase 1 is implemented; the full UrbanPulse course
assignment is not complete.** No commits, pushes, PRs, or remote GitHub changes
were made during this implementation. Existing repository identity was preserved.

## Completed

- Verified live NYC 311 and Community District schemas and official documentation;
  recorded the December 2025 display/API-name distinction and current dataset ID.
- Implemented token-optional HTTP ingestion, retries, timeouts, chronological
  composite-key pagination, atomic raw-page checkpoints, checksums, and disk-backed
  global uniqueness auditing. Smoke and full modes are separate.
- Retrieved **2,400 real records** across 24 pages and all 12 months; preserved raw
  originals locally and distributed a compact demo with schema/manifest metadata.
- Implemented conservative New York date parsing, DST uncertainty flags, identifier
  preservation, coordinate checks, duplicate rules, and nullable outcomes.
- Implemented mutually exclusive duration buckets, right censoring, mature seven-day
  labels, and a creation-time feature allowlist. No final model trained.
- Prepared **71 validated GeoJSON features** (59 districts and 12 JIAs), explicit
  board-code joins, unmatched classifications, and borough disagreement flags.
- Built a **52-column Parquet contract**, version checks, local loader, shared filters,
  summaries, streaming quality checks, and a minimal sample-aware Streamlit app.
- Wrote README, source notes, data dictionary, pipeline/architecture guide, student
  integration guide, measured quality report, ML designs, and decisions.
- Added pinned dependencies/constraints, portable paths, ignore rules, line-ending
  policy, and Ubuntu/Windows GitHub Actions configuration.

## Executed validation

Local environment: Linux / Ubuntu, Python **3.12.3**, pandas **2.2.3**, Arrow
**19.0.1**, Streamlit **1.45.1**. Commands used the repository `.venv/bin/python`;
activated-shell equivalents are shown below.

| Executed command/check | Observed result |
| --- | --- |
| `python -m pipeline --help` | CLI displayed ingest, geography, build, quality commands. |
| `python -m pipeline ingest --mode smoke --per-month 200 --page-size 100` | 2,400 rows; 2,400 unique IDs; 0 duplicates; 0 missing IDs. |
| Repeat identical completed ingestion | Successful checkpoint verification, no new download. |
| `python -m pipeline geography` | 71 features validated. |
| `python -m pipeline build --run-dir data/raw/smoke --output data/demo/requests.parquet --geography data/geographic/community_districts.geojson` | 2,400 processed; 0 excluded. |
| `python -m pipeline quality --input data/demo/requests.parquet` | Schema, unique IDs, and outcome validation passed. |
| `python -m pytest -q` | 81 tests passed in 3.82 seconds (final complete suite). |
| `python -m ruff check .` | Passed. |
| `python -m ruff format --check .` | 20 Python files already formatted. |
| `python -m pip check` | No broken requirements. |
| `git diff --check` | Passed. |
| Documentation/artifact audit | All 52 columns documented; local Markdown links and Parquet/manifest/geography checksums passed. |
| Streamlit AppTest on synthetic fixtures | Shared filtering, empty results, and missing-dataset handling passed. |
| Streamlit AppTest on real demo | No app exceptions; 2,400 overall and 710 Brooklyn records; preview agrees. |
| Headless Streamlit on 127.0.0.1:8501 | Health endpoint 200 `ok`; root endpoint 200; server stopped after verification. |

Tests cover null/invalid parsing, IDs, schema drift, duplicate handling, exact duration
boundaries, DST fold/gap and elapsed hours, censoring, immature labels, borough and
coordinate normalization, geographic mappings/JIAs, filter combinations/dates/empty
results, checkpoint resume, retries/HTTP policy, raw checksums, Parquet builds,
atomic preservation on failed rebuild, loader paths/version guards, and app behavior.
Network tests use mocks and labelled synthetic data. They do not claim to exercise
live throttling; the initial live run did exercise read-timeout retry behavior.

## Actual sample findings

2,388 valid closures, 7 censored requests, 5 unknown outcomes; two DST-ambiguous
closure timestamps; one valid >365-day closure retained. Geographic matches:
2,378 ordinary district requests + 6 JIA requests = 2,384 (99.3333%). Sixteen
requests lack matches/coordinates; two board/request borough disagreements are
flagged. See [DATA_QUALITY.md](DATA_QUALITY.md) for all measured counts and denominators.

## Failures encountered and resolved

- Sandbox DNS blocked initial public requests and dependency installation; approved
  network access succeeded. No dependency install failure remains.
- ID-only ordering caused repeated 120-second read timeouts. A bounded comparison
  supported creation-time ordering; composite creation/key pagination completed
  the final sample. The abandoned 800-row partial run remains locally for audit.
- Initial automated tests caught a cutoff timestamp precision mismatch; explicit
  nanosecond UTC construction fixed it.
- Sandboxed Streamlit could not create sockets. The approved localhost startup and
  health check succeeded. This was an environment permission issue, not an app error.

## Platform status

Linux execution is verified. Windows CI is **configured, not executed here**; no
remote workflow has been triggered by this implementation. macOS runtime execution
is unverified. Essential commands use Python modules and pathlib; no WSL dependency
or machine-specific paths are committed. Windows/Linux instructions are complete;
macOS setup is documented. CI must confirm package resolution and runtime behavior
on an actual Windows runner before claiming cross-platform certification.

## Pending and next steps

1. Team review the contract, source assumptions, and sample quality report.
2. Run and audit full 2025 ingestion before citywide inference or final ML fitting.
   Memory/runtime performance at full scale has not been benchmarked; the loader
   and Streamlit hold the selected dataset in RAM.
3. Verify the boundary vintage appropriate for 2025, and add topology/spatial
   membership validation if required by final geographic questions.
4. Confirm creation-time availability of planned ML features and choose leakage-safe
   temporal cohorts. Train K-Means and logistic regression in a later phase.
5. Each student implements three complementary final visualizations using
   `create_visualization(filtered_df) -> plotly.graph_objects.Figure`. Reuse the
   shared loader and `apply_filters`; agree on any schema change before coding.
6. Run actual Windows CI and test macOS when available. Review dependency updates
   through tests and regenerated constraints.
7. Complete the final dashboard, English one-page report, English presentation,
   repository publication/documentation review, and final course rubric validation
   before November 15, 2026, 23:59.

The smoke sample emphasizes early-month/night-time requests and is unsuitable for
population estimates. The live API is not a transactional snapshot. Snapshot
status cannot reconstruct reopenings or prove real-world issue resolution.
No final visualization, ML training, report, or presentation completion is claimed.

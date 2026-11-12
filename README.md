# UrbanPulse — Where Do Public Service Requests Wait?

**An Interactive Exploration of Urban Service Demand, Closure Times, and Neighborhood Patterns.**

CEN445 — Introduction to Data Visualization. Three students will each develop
three visualizations. Submission deadline: **November 15, 2026, 23:59**.

UrbanPulse asks: Which service requests take longest to close? How do service
profiles differ across boroughs and community districts? How much apparent delay
reflects still-open requests, request mix, or incomplete records?

**Current phase: Phase 2A — Member 1 advanced visualizations.** Three interactive
charts now use the shared filtered Parquet architecture: a bivariate community
district map, borough Kaplan–Meier curves, and a linked daily time-series explorer.
The pipeline, 52-column contract, diagnostics, and Phase 1.5 query APIs remain intact.
The other six visualizations, two final ML models, report, and presentation remain
pending. Diagnostics do not count as final charts.

## Data and scope

- [NYC 311 Service Requests from 2020 to Present, erm2-nwe9](https://data.cityofnewyork.us/d/erm2-nwe9)
- [NYC Community Districts, 5crt-au7u](https://data.cityofnewyork.us/d/5crt-au7u)

Requests created from January 1, 2025 inclusive to January 1, 2026 exclusive,
restricted to Manhattan, Brooklyn, Queens, Bronx, and Staten Island. The pipeline
retrieves 15 primary fields and two auxiliary audit fields. The cleaned contract
has 52 columns. Source schema and December 2025 dataset changes are verified and
explained in [SOURCES.md](docs/SOURCES.md).

`data/demo/requests.parquet` is a **real, bounded sample**, selected by the earliest
200 creation timestamps in each calendar month (lexical ID tie-break). It is not representative in a
statistical sense. Counts and rates describe only selected records. The local full 2025
extraction contains **3,652,435 real requests**; its large Parquet remains ignored by Git.
Measured full and sample counts are distinguished in
[DATA_QUALITY.md](docs/DATA_QUALITY.md) and the adjacent machine-readable quality
report. The app defaults explicitly to the demo; it never substitutes it for full data.

## Requirements and installation

Use **64-bit Python 3.12**, Git, and a local virtual environment. Internet is
needed for installation and fresh downloads; the included demo runs offline.
No API token, GeoPandas, GDAL, database server, or WSL installation is required.
Direct versions and resolved dependency constraints are committed. See
[TEAM_GUIDE.md](docs/TEAM_GUIDE.md) for complete Windows, WSL/Linux, and macOS setup.

```bash
git clone https://github.com/emrehann17/urbanpulse.git
cd urbanpulse
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-dev.txt
```

Windows PowerShell:

```powershell
git clone https://github.com/emrehann17/urbanpulse.git
cd urbanpulse
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements-dev.txt
```

If activation is restricted, call `.\.venv\Scripts\python.exe` directly. Runtime
only installation can use `requirements.txt`. `.env.example` documents optional
settings; `.env` is **not** automatically loaded. Export `SOCRATA_APP_TOKEN` to
raise API quotas if desired; basic public access works without it.

## Run the demo

```text
python -m streamlit run app.py
```

Choose a dataset, then use borough, complaint type, agency, and created-date
filters. Counts, quality indicators, and the record preview consume the exact
same filtered population (DataFrame for demo/smoke, SQL for full mode). The record preview is limited to 200 rows; summary
metrics use all matching rows. Missing files and empty results have explicit messages.

## Ingest, preprocess, and validate

Run from the repository root. The module help lists every supported option.

```text
python -m pipeline --help
python -m pipeline ingest --mode smoke --per-month 200 --page-size 100
python -m pipeline geography
python -m pipeline build --run-dir data/raw/smoke --output data/processed/smoke.parquet --geography data/geographic/community_districts.geojson
python -m pipeline quality --input data/processed/smoke.parquet
```

For full ingestion, explicitly use:

```text
python -m pipeline ingest --mode full --page-size 5000
python -m pipeline build --run-dir data/raw/full --output data/processed/requests.parquet --geography data/geographic/community_districts.geojson
python -m pipeline quality --input data/processed/requests.parquet
```

Full extraction can take substantial time and disk space. Ingestion and processing
are bounded by page size; loading the full DataFrame still needs enough RAM; full-mode Streamlit now uses the query layer. Resume an
interrupted download by repeating identical arguments. To refresh or change
sampling settings, use a new `--run-dir`. Never run concurrent writers on the same
run/output paths. See [PIPELINE.md](docs/PIPELINE.md) for recovery and artifact details.

## Shared API

```python
from pipeline import load_data, apply_filters, get_filter_options, get_data_summary

df = load_data(dataset="demo")  # explicitly choose "full" after a full build
options = get_filter_options(df)
filtered_df = apply_filters(
    df, borough=["Brooklyn", "Queens"], agency="All",
    start_date="2025-01-01", end_date="2025-12-31",
)
summary = get_data_summary(filtered_df)
```

No Streamlit dependency is required by these functions. Missing values use
`pd.NA`/`NaT`, not invented zeros. All student visualization modules receive
`filtered_df` and return a Plotly figure without modifying the data. See the
[team integration examples](docs/TEAM_GUIDE.md).

## Scalable access for full data

DuckDB **1.4.5 LTS** is the only new runtime dependency, installed by the existing
requirements command. It queries local Parquet directly; no database server or
persistent copy is created. Existing public DataFrame APIs and the 52-column
contract remain unchanged.

```python
from pipeline.filters import FilterSpec
from pipeline.query import ParquetQuery

query = ParquetQuery(dataset="demo")  # choose "full" for the locally validated full artifact
filters = FilterSpec(borough=["Brooklyn", "Queens"], start_date="2025-01-01", end_date="2025-12-31")
count = query.count(filters=filters)
by_day = query.aggregate("created_day", filters=filters)
closures = query.aggregate("borough", metrics=("closure_mean_hours", "censored", "unknown_outcomes"), filters=filters)
preview = query.preview(("unique_key", "created_day", "borough"), filters=filters, limit=200)
```

SQL values are parameters, columns/metrics are allowlisted, and filters use the
same `FilterSpec` normalization as `apply_filters()`. Aggregates are exact and
include population/valid-observation denominators; null durations stay null.
The preview is limited and must not be used as a representative sample. See the
[team query examples](docs/TEAM_GUIDE.md) for all planned chart input patterns.

```text
python -m benchmarks.query_benchmark --output benchmarks/local/demo.json
python -m benchmarks.query_benchmark --synthetic-rows 100000 --output benchmarks/local/synthetic.json
```

The measured demo favors cached Pandas latency; the bounded synthetic experiment
favors DuckDB latency and memory. Neither verifies full 2025 performance. Details,
limits, and reproducible reports are in [PERFORMANCE.md](docs/PERFORMANCE.md).

## Tests and style

```text
python -m pytest -q
python -m ruff check .
python -m ruff format --check .
python -m pip check
```

Tests use labelled synthetic fixtures and mocked API responses. They do not rely
on live NYC availability. GitHub Actions is configured for Ubuntu and Windows,
Python 3.12, with a fresh `.venv-ci` in each job. This isolates project packages
from runner tools such as pipx; `pip check` remains enabled. Local executed checks and platform limitations are recorded in
[PROJECT_STATUS.md](docs/PROJECT_STATUS.md); configured CI is not a claim that
remote workflows have run.

## Repository structure

```text
urbanpulse/
├── app.py
├── requirements.txt / requirements-dev.txt / constraints.txt
├── pyproject.toml / .env.example / .gitignore / .gitattributes
├── config/                 # repository-anchored paths and source constants
├── pipeline/
│   ├── __init__.py / __main__.py
│   ├── ingest.py / preprocess.py / features.py / build.py
│   ├── contract.py / loader.py / filters.py / query.py / quality.py / geography.py
├── data/
│   ├── raw/                # ignored original JSONL pages and run checkpoints
│   ├── processed/          # ignored full/smoke Parquet artifacts
│   ├── demo/               # small real sample + provenance + measured quality
│   ├── geographic/         # validated GeoJSON + retrieval metadata
│   └── metadata/           # source schema snapshots
├── visualizations/         # Member 1 map, survival, time series, shared app section
├── ml/                     # design reference; trained models pending
├── tests/                  # deterministic offline tests and app integration
├── benchmarks/             # reproducible script and small measured JSON reports
├── docs/                   # data dictionary, pipeline, quality, team and ML guides
└── .github/workflows/ci.yml
```

## Team workflow and reproducibility

Create one feature branch per visualization, keep changes within your assigned
module, run tests/lint, and request a pull request review before integration.
Agree on schema changes with all three students. Do not duplicate ingestion,
preprocessing, or global filters. Do not commit credentials, virtual environments,
or full datasets. The included demo and metadata are intended for Git distribution.

Original raw pages remain locally for audits; another teammate or grader can
retrieve the exact scope with the commands above. Selection is reproducible, but
live source edits mean freshly downloaded values need not be byte-identical.
Use the included demo's checksum to identify the exact shared demonstration
artifact. Record fresh manifests and quality reports when publishing new snapshots.

## Known limitations and further documentation

311 measures reported service requests, not all underlying service needs. Closure
records are administrative outcomes, not proof of satisfactory resolution. Current
statuses do not reveal reopening history. DST ambiguity, invalid timestamps,
status/date conflicts, and immature censoring produce unknown outcomes. Current
2026 district boundaries have not been reconciled against 2025 historical geometry.
Coordinate checks are a conservative envelope, not spatial membership validation.
The live API is not a transactionally consistent snapshot. The demo is not suitable
for population inference or model training.

- [Data dictionary and contract](docs/DATA_DICTIONARY.md)
- [Pipeline architecture and reruns](docs/PIPELINE.md)
- [Team guide and examples](docs/TEAM_GUIDE.md)
- [Measured data quality](docs/DATA_QUALITY.md)
- [Source verification](docs/SOURCES.md)
- [Future ML design](docs/ML_DESIGN.md)
- [Decisions and trade-offs](docs/DECISIONS.md)
- [Project status and remaining work](docs/PROJECT_STATUS.md)

- [Query performance and full-ingestion readiness](docs/PERFORMANCE.md)

## Member 1 visualizations and review

Run `python -m streamlit run app.py`, choose **full**, and use the shared sidebar.
The demo retains diagnostics; its biased first-of-month records are not shown as
population trends. The full artifact must exist locally; startup never ingests it.
The map uses the committed validated GeoJSON with a blank MapLibre background;
no external tile service or API key is required.

```text
python -m benchmarks.member1_benchmark --dataset full --output benchmarks/local/member1.json
```

This queries existing data, measures the three workloads, and writes six standalone
HTML files under `benchmarks/local/member1/` for all requests and Brooklyn Q1.
Open them in a browser to review map hover/zoom, the 3×3 key, survival legend toggles,
and linked daily axes. See [visualization specifications](docs/VISUALIZATION_SPEC.md),
[statistical methods](docs/CHART_METHODS.md), and [performance](docs/PERFORMANCE.md).

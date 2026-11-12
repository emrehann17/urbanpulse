# Team guide: one pipeline, three contributors

Each student owns three final visualizations. All nine must share the same data
artifact, definitions, and filter result. Member 1’s three charts are implemented in Phase 2A. The other six charts and
final models remain pending; preserve the assigned research questions.

## Clone and create an environment

Do not create a second Git repository inside the clone. Install 64-bit Python
3.12 and Git using your platform's normal installer/package manager.

### WSL / Ubuntu / Linux

```bash
git clone https://github.com/emrehann17/urbanpulse.git
cd urbanpulse
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-dev.txt
python -m pytest -q
python -m streamlit run app.py
```

On Ubuntu, install the matching `python3.12-venv` package if venv reports that
ensurepip is missing. In WSL, keep the clone on the Linux filesystem for better
file performance. Do not reuse a Windows virtual environment inside WSL.

### Windows PowerShell

```powershell
git clone https://github.com/emrehann17/urbanpulse.git
cd urbanpulse
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements-dev.txt
python -m pytest -q
python -m streamlit run app.py
```

Activation is optional. If PowerShell's script policy blocks it, use:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m streamlit run app.py
```

No policy change or administrator session is required. WSL is optional, not a
prerequisite. Never commit `.venv` or share it across operating systems.

### macOS

Install Python 3.12 (python.org or your package manager), then:

```bash
git clone https://github.com/emrehann17/urbanpulse.git
cd urbanpulse
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-dev.txt
python -m streamlit run app.py
```

Use a native arm64 interpreter on Apple Silicon or a native x86_64 interpreter on
Intel. If pip tries to compile Arrow, check Python version and architecture first;
supported Python 3.12 platforms normally use binary wheels. There is no GDAL
installation requirement. macOS execution has not been verified locally.

### Optional settings

Unix shells: `export SOCRATA_APP_TOKEN='your-token'`.
PowerShell: `$env:SOCRATA_APP_TOKEN='your-token'`.
Keep actual credentials out of committed files. Copying `.env.example` to `.env`
does not load it: export values explicitly. `URBANPULSE_DATA_DIR` can point to an
absolute shared data root containing `demo/`, `processed/`, and `geographic/`.
Set it before importing pipeline modules. Repository-default loading works from
other current working directories when the repository is on Python's import path.
For notebooks, start Jupyter from this repository using the same Python environment;
Jupyter is optional and is not a project runtime dependency.

## Retrieve or use shared data

The included real demo is for integration and demonstrations only. Full data must
be built explicitly with the commands in [PIPELINE.md](PIPELINE.md). Share a
manifest, Parquet checksum, and quality report when agreeing on a team snapshot.
Never compare chart outputs generated from different snapshot versions as if
those were the same observations.

```python
from pipeline import load_data, apply_filters, get_filter_options, get_data_summary

df = load_data(dataset="demo")
print(df.attrs["urbanpulse"])
options = get_filter_options(df)
filtered_df = apply_filters(
    df,
    borough=["Manhattan", "Bronx"],
    complaint_type="All",
    agency=None,
    start_date="2025-01-01",
    end_date="2025-06-30",
)
print(get_data_summary(filtered_df))
```

`load_data(path=None, *, dataset='demo') -> pandas.DataFrame`. Named modes are
`demo`, `smoke`, `full`; no fallback occurs. An explicit relative path is relative
to the configured data root; absolute pathlib paths work too. Example:
`load_data('demo/requests.parquet')`.

`apply_filters(df, *, borough=None, complaint_type=None, agency=None,
start_date=None, end_date=None) -> pandas.DataFrame`. Strings and lists/tuples are
accepted for categories. Values match canonical cleaned labels exactly. Within a
category OR applies; across categories AND applies. `None` or `'All'` (including
`['All']`) is unrestricted. `[]` means no records. Date bounds are inclusive New
York calendar dates, accepting ISO strings, Python dates/datetimes, or pandas
Timestamps. A reversed range raises ValueError. No in-place mutation occurs.

`get_filter_options(df) -> dict`: sorted non-null category lists and ISO
`start_date`/`end_date` (None for no valid dates). `get_data_summary(df) -> dict`:
rows, unique_requests, valid_closures, censored, unknown_outcomes,
geographic_matches, valid_coordinates, created_min, created_max. Counts use the
passed DataFrame, including empty results. These APIs do not import Streamlit.

## Visualization interface

Each module should export:

```python
import pandas as pd
import plotly.graph_objects as go


def create_visualization(filtered_df: pd.DataFrame) -> go.Figure:
    """Create a figure from shared, already-filtered data without modifying it."""
    figure = go.Figure()
    if filtered_df.empty:
        figure.add_annotation(text="No requests match the shared filters.", showarrow=False)
        return figure
    # Add your assigned chart's aggregation and traces here in the next phase.
    # Use a local copy if adding intermediate columns.
    figure.update_layout(title="Assigned visualization — implementation pending")
    return figure
```

This is an interface example, not one of the nine deliverable charts. Specify
required columns, units, denominator, null exclusions, and what an interaction
reveals in your module docstring. `closure_hours` describes validated completed
observations only; analyses of all requests need censoring-aware measures. Never
fill missing closure durations with zero. Aggregate only validated `boro_cd`
values for maps, normally `geography_status == 'community_district'`. A geographic
match is not a point-in-polygon validation. Review flagged borough disagreements.

In the next phase, connect a module after `filtered` is computed in `app.py`:

```python
# Once visualizations/student_one_chart.py exists:
from visualizations.student_one_chart import create_visualization

figure = create_visualization(filtered)
st.plotly_chart(figure, use_container_width=True, key="student_one_chart")
```

For DataFrame modules, other components receive that same `filtered` object.
For full-data modules, pass one shared FilterSpec through the query layer as shown
below. Keep global filter widgets and normalization in the app shell. Current widget keys are
`{dataset}_borough`, `{dataset}_complaint_type`, `{dataset}_agency`, and
`{dataset}_dates`. Future cross-chart selections should use a separate namespaced
session-state dictionary, convert selections into shared filter arguments, and
apply them once at the app boundary. Do not add hidden per-chart global filters.
Chart-specific controls are allowed when labelled and documented.

A non-Plotly component may expose `render_visualization(filtered_df) -> None` with
an explicitly documented Streamlit dependency and a unique widget-key namespace.
Its statistical transformation should remain a pure testable function. Agree on
such exceptions before integration; the default interface stays Plotly.

## Branches and pull requests

1. Update your local main branch from the shared repository, preserving your work.
2. Create a descriptive branch, e.g. `git switch -c viz/student1-demand-profile`.
3. Implement your assigned module and test meaningful data logic, empty results,
   and input immutability. Use the shared artifact and contract.
4. Run `python -m pytest -q`, `python -m ruff check .`, and
   `python -m ruff format --check .`.
5. Commit only relevant source/docs and approved small artifacts. Review `git diff`.
6. Push your branch and open a PR when authorized by the team. Ask another student
   to review interpretation, usability, filtering, and integration.

The repository is published on GitHub. Engineering work does not push or create remote PRs on your behalf. All
three students must review schema/target definition changes. Follow semantic
versioning and explicit rebuild requirements in [PIPELINE.md](PIPELINE.md).

## Troubleshooting

| Symptom | Action |
| --- | --- |
| `python` not found on Unix | Use `python3.12` to create venv, then activate it. |
| Module import error | Use the same venv, run from the clone, verify `python -m pip --version`. |
| Dataset missing | Select demo or run ingestion/build; the app intentionally never downloads automatically. |
| Sample rejected as full | Build from a full-mode manifest; never rename a smoke file to bypass provenance. |
| API timeout / 429 | Let retries finish; rerun identical arguments to resume; optionally export an app token. |
| Checkpoint mismatch | Restore the original arguments or select a new run directory. |
| Checksum failure | Preserve the suspect run for inspection; retrieve into a new directory. |
| Schema mismatch | Pull matching code and rebuild; do not drop validation or edit Parquet manually. |
| Empty dashboard | Clear restrictive filters or select All; an empty multiselect intentionally matches nothing. |
| Unknown outcomes | Inspect status/date/DST flags and raw audit values; do not infer an outcome. |
| Full dataset exceeds RAM | Use ParquetQuery for aggregates and bounded projections; retain Pandas for small data. |
| Windows file cleanup issue | Close notebooks/apps using artifacts before replacement; recreate venv if necessary. |

`python -m ruff format .` formats source. Tests are offline; a public API outage
should not prevent local development. Report actual source failures separately
from mock-test results. See [PROJECT_STATUS.md](PROJECT_STATUS.md) for what has
actually been executed on each platform.

## Phase 1.5: choose the access API by workload

Use the existing `load_data()` + `apply_filters()` workflow for the 2,400-row demo
and small notebook experiments. Use **`ParquetQuery` for the full dataset**. It
reads selected Parquet columns and returns exact aggregates or bounded previews;
it never calls `load_data()` internally. `FilterSpec` normalizes the same public
filter arguments as `apply_filters`; category values remain exact, case-sensitive
cleaned labels. NULLs remain in unrestricted populations and NULL-key groups.

The following example runs against the real demo without a download. After a
separate full build and quality audit, change only `dataset="demo"` to `"full"`.

```python
from pipeline import load_data, apply_filters
from pipeline.filters import FilterSpec
from pipeline.query import ParquetQuery

shared = dict(
    borough=["Brooklyn", "Queens"], complaint_type="All", agency=None,
    start_date="2025-01-01", end_date="2025-12-31",
)
filters = FilterSpec(**shared)
query = ParquetQuery(dataset="demo")

# The same filtered population through both APIs (parity check for small data only).
small = apply_filters(load_data(dataset="demo"), **shared)
assert query.count(filters=filters) == len(small)

by_borough = query.aggregate("borough", filters=filters)
by_day = query.aggregate("created_day", filters=filters)
complaints = query.aggregate("complaint_type", filters=filters)
agency_complaints = query.aggregate(("agency", "complaint_type"), filters=filters)
closures = query.aggregate(
    "borough", filters=filters,
    metrics=("requests", "valid_closures", "closed", "censored", "unknown_outcomes",
             "closure_mean_hours", "closure_min_hours", "closure_max_hours"),
)
districts = query.aggregate(
    ("boro_cd", "geography_status"), filters=filters,
    metrics=("requests", "closure_mean_hours", "long_closure_rate"),
)
outcomes = query.aggregate(metrics=("closed", "censored", "unknown_outcomes"), filters=filters)
preview = query.preview(
    ("unique_key", "created_day", "complaint_type", "closure_hours", "closure_event"),
    filters=filters, limit=200,
)
assert outcomes.requests.iloc[0] == outcomes[["closed", "censored", "unknown_outcomes"]].sum(axis=1).iloc[0]
```

These operations are exercised in offline tests, including empty populations,
NULL categories, unknown outcomes, time-zone date bounds, and combined filters.
Do not copy the small-data parity check into full-mode application startup.

### Query interfaces

```text
FilterSpec(borough=None, complaint_type=None, agency=None, start_date=None, end_date=None)
ParquetQuery(path=None, *, dataset="demo", memory_limit_mb=512, threads=2)
query.count(*, filters=None) -> int
query.summary(*, filters=None) -> dict
query.filter_options() -> dict
query.aggregate(group_by=(), *, metrics=("requests",), filters=None) -> DataFrame
query.preview(columns, *, filters=None, limit=200) -> DataFrame
```

Paths follow the loader: relative paths resolve under the configured data root;
explicit absolute pathlib paths also work. Constructor checks only schema/provenance
in the footer. Run `python -m pipeline quality --input ...` once offline before
serving a newly built artifact. Do not replace an artifact while queries are using
it; the query object rejects detected size/mtime/inode changes. Build snapshots
under new filenames and switch during a quiet period if serving multiple users.

Only contract column names and registered metric names are accepted. Values are
SQL parameters, not interpolated text. Do not write chart-specific SQL, WHERE
clauses, category normalization, or date conversion. Use one `FilterSpec` constructed
by the app shell for all nine components. `None` and `"All"` are unrestricted,
`[]` means no matches, selections OR within a category and AND across categories,
and dates are inclusive local days, exactly as in the DataFrame API. Category
selection elements must be strings; None is an unrestricted **selection**, not
an explicit NULL category token. Unrestricted and All selections retain null rows.

Every aggregate includes `requests`. Duration summaries automatically include
`valid_closures`; their means/min/max ignore null closure hours. A requested
`long_closure_rate` automatically includes `known_long_labels` and `long_closures`.
That rate uses **known labels**, including mature censored positives, not every
request or only completed requests. A zero denominator gives null, never zero.
Request totals include censored and unknown outcomes. NULL grouping keys are
retained. Use `geography_status` to distinguish district, JIA, and unmatched groups;
do not silently drop them before reporting exclusions.

Previews require explicit column projection and `0 <= limit <= 10000`. They sort
by local created_day and unique_key (null days last). A preview is a deterministic
limited listing, **not a random or representative sample**. Exact counts and
aggregates always use the whole matching population. More than 100,000 grouped
results raises a clear error rather than truncating exact aggregates. Narrow an
explicit cohort or agree on a reviewed streaming/binned design if this is exceeded.

### Integration of future charts

For small-data modules, keep `create_visualization(filtered_df) -> Figure`.
For full-data modules, have the app shell fetch a **small, named aggregate table**
and pass it to a pure figure function with documented required columns:

```python
# After a future module exists; do not implement the chart in the query layer.
# from visualizations.student_one_chart import create_visualization
# by_day = query.aggregate("created_day", filters=filters)
# st.plotly_chart(create_visualization(by_day), key="student_one_chart")
```

Document whether a figure accepts request rows or an aggregate table; these have
different schemas. Never pass a truncated preview to a function expecting the
entire population without visibly labelling its limited scope. Chart-specific
transformations such as pivoting exact counts into proportions may happen locally
on aggregate results. Common filters remain exclusively in the shared layer.

| Planned visualization | Shared query inputs / caution |
| --- | --- |
| Bivariate Choropleth | District/geography-status aggregates, counts and duration/known-label denominators; separate JIAs and unmatched rows. |
| Calendar Heatmap | Exact created_day request counts; missing-day group reported separately. |
| Sankey Diagram | Exact agency × complaint_type counts, retaining missing-category groups. |
| Survival Curve | Group by observed_hours and closure_event with requests as frequency weights; report unknown-outcome exclusions. Never fit from a preview. |
| Ridgeline Density Plot | Exact complaint_type × closure_hours frequencies within a reviewed cohort, or a separately designed and labelled sampling/binning method. |
| Bipartite Network Graph | Exact agency × complaint_type edge counts; document any display-only edge threshold. |
| Parallel Coordinates | District aggregate profiles and explicit support/denominators, normalized later under the ML design. |
| PCA Cluster Explorer | District × complaint counts plus district outcome summaries; fit transformations/models later. |
| Linked Time-Series Explorer | Exact created_day × agency or complaint_type aggregates with the same FilterSpec. |

High-cardinality duration/time combinations may exceed the group limit. Phase 2A supplies a streamed exact survival estimator (below); density sampling
and final model designs still require review. Do not
solve a group-limit error by silently limiting or sampling statistical input.

Full-mode Streamlit uses bounded caches: eight catalog entries and 32 filtered
summary/200-row preview entries, each with a ten-minute TTL and file fingerprint.
It does not cache DuckDB connections or full request frames. See
[PERFORMANCE.md](PERFORMANCE.md) for memory limits and benchmark evidence.

## Phase 2A: Member 1 integration and examples

Member 1 owns `visualizations/bivariate.py`, `survival.py`, `timeseries.py`, and the
modular `member1.py` Streamlit section. Members 2 and 3 should follow the same
separation: common FilterSpec → reviewed query helper → bounded aggregate → pure
renderer. Keep global filters in app.py. Do not clone the sidebar or independently
normalize categories/dates. The original DataFrame interface above remains useful
for small, complete cohorts; never use full `load_data()` or a preview for population
statistics. No additional dependency or schema migration is required.

This example runs on the existing real full artifact. Using `dataset="demo"` is
permitted for module development only: explicitly label outputs as a biased sample.
The app intentionally reserves these population charts for full mode.

```python
from config.settings import DATA_DIR
from pipeline.filters import FilterSpec
from pipeline.query import ParquetQuery
from pipeline.geography import load_geography
from pipeline.chart_data import district_data, daily_data, survival_data
from visualizations import bivariate, survival, timeseries

query = ParquetQuery(dataset="full")
filters = FilterSpec(borough="Brooklyn", start_date="2025-01-01", end_date="2025-03-31")
geojson = load_geography(DATA_DIR / "geographic" / "community_districts.geojson")
districts = district_data(query, filters, geojson)
days = daily_data(query, filters)
curves, outcomes = survival_data(query, filters)
map_figure = bivariate.create_visualization(districts, geojson=geojson)
km_figure = survival.create_visualization(curves, outcomes=outcomes)
daily_figure = timeseries.create_visualization(days, rolling=True)
assert districts.attrs["population"] == query.count(filters=filters)
assert days.requests.sum() + days.attrs["unknown_created_day"] == query.count(filters=filters)
assert outcomes.requests.sum() == query.count(filters=filters)
```

These same operations and reconciliation assertions are executed by
`python -m benchmarks.member1_benchmark`. All three figure functions return Plotly
Figures and are independent of Streamlit. Required schemas and attrs are listed
in [CHART_METHODS.md](CHART_METHODS.md); do not substitute request-level frames.
A Streamlit component renders an already-prepared figure as follows:

```python
import streamlit as st
# map_figure is produced by the shared preparation example above.
st.plotly_chart(map_figure, use_container_width=True, key="member1_districts")
```

The actual app calls `render_member1(path, filters, is_full=..., fingerprint=...)`
after diagnostics with the **same** FilterSpec and artifact fingerprint. Preparation
caches four small tables, not request records or DuckDB connections. Confidence and
trend switches only rerender these tables; they do not define new global populations.
Other chart owners should use distinct Streamlit keys. Preserve diagnostic table
ordering and empty-state behavior when adding sections.

For record-level work, continue using `query.preview(explicit_columns, filters=filters,
limit=...)` only as a labeled preview. If another advanced chart requires a density
or individual-point sample, agree on a sampling design and disclose it; do not
use the ordered first 200 records as a representative sample. For exact grouped
metrics, `closure_median_hours` now complements the existing mean/min/max and
includes the valid denominator automatically. High-cardinality survival inputs
have a dedicated streaming interface; do not bypass aggregate caps by requesting
millions of DataFrame rows.

Review: run pytest and Ruff; select full in Streamlit; follow the interaction checklist
in [VISUALIZATION_SPEC.md](VISUALIZATION_SPEC.md). `benchmarks/local/member1/`
contains reproducible HTML reviews after the benchmark command. Full Parquet/raw
files and generated reviews remain ignored; share the immutable artifact separately
with its SHA-256 and local quality report, or use the documented explicit ingestion
commands to retrieve a fresh snapshot. Live-source values can change between runs.

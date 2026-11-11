# Team guide: one pipeline, three contributors

Each student owns three final visualizations. All nine must share the same data
artifact, definitions, and filter result. No final visualization is implemented
in Phase 1. Agree on complementary research questions before starting chart work.

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

All other components receive that same `filtered` object. Keep global filter
widgets and `apply_filters` in the app shell. Current widget keys are
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

Phase 1 implementation does not push or create remote PRs on your behalf. All
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
| Full dataset exceeds RAM | Use demo for development, Arrow batches offline, or plan a shared query layer. |
| Windows file cleanup issue | Close notebooks/apps using artifacts before replacement; recreate venv if necessary. |

`python -m ruff format .` formats source. Tests are offline; a public API outage
should not prevent local development. Report actual source failures separately
from mock-test results. See [PROJECT_STATUS.md](PROJECT_STATUS.md) for what has
actually been executed on each platform.

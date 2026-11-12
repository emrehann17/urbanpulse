# Project status — Member 1 and Member 3 visualization integration

Updated November 12, 2026. Member 1's and Member 3's **six advanced interactive
charts are implemented locally** on the shared pipeline. Reproducible K-Means and
Logistic Regression baselines are complete. Member 2's three charts, final report,
and presentation remain pending. The full course assignment is not complete.
Repository: [emrehann17/urbanpulse](https://github.com/emrehann17/urbanpulse).
Work began on clean branch `viz/member1-geography-waiting`. No commits, pushes,
remote branches, CI runs or dataset rebuilds/downloads were initiated in Phase 2A.

## Phase 3B Member 3 update

- Assigned final charts: agency × complaint Bipartite Network, district Parallel
  Coordinates, and PCA Cluster Explorer. The earlier heatmap remains supplemental.
- Bipartite data comes from an exact shared-filter DuckDB aggregate. The all-borough
  2025 review shows 2,229,352 of 3,651,639 requests (61.1%) through twelve displayed
  links. The graph discloses top-category and maximum-edge display rules.
- Parallel Coordinates and PCA use the persisted 59-district K-Means export without
  retraining. Parallel axes retain raw units; PCA uses saved coordinates explaining
  77.43% of processed variance. Cluster IDs are nominal and never rankings.
- Streamlit full mode now renders three Member 1 plus three Member 3 charts. An empty
  shared filter suppresses cohort charts but retains the two explicitly fixed
  district-model views. Demo mode retains diagnostics without population charts.
- Browser review found and repaired a Parallel Coordinates title/axis/color-key
  collision. Bipartite and PCA layouts were also reviewed from local HTML exports.
- Latest Windows/Python 3.12 checks: **235 tests passed**, Ruff and format passed,
  and `pip check` reported no broken requirements. Five upstream ML/joblib warnings
  remain visible. No model was retrained and no data artifact was committed.

See [MEMBER3_VISUALIZATIONS.md](MEMBER3_VISUALIZATIONS.md) for the complete Member 3
specification, findings, limitations, review files, and presentation outline. The
remaining sections preserve the earlier detailed Member 1 handoff evidence.

## Phase 2A.1 visual polish

- Larger, closer-framed map with a separate square 3×3 key and external threshold
  table. Labels now read Low / Medium / High; classification is unchanged.
- Survival defaults to the first 30 days. Plotly buttons provide 7/30/90 days and
  full follow-up through axis-only relayout. Short borough legends, distinct
  dashes, and a separate exact cohort/censoring summary improve readability.
- Taller daily panels, more spacing, a top two-row legend and slim bottom slider;
  synchronized date axes and original counts/medians/rolling definitions retained.
- Responsive standalone HTML cards, modern system typography, readable methods and
  caveat sections, threshold/cohort tables and expandable JSON. All six reviews
  regenerated from full local data; new logs remain ignored under benchmarks/local.
- Modified only presentation/export/test/documentation files. app.py, query,
  filtering, contract, chart preparation and full Parquet SHA-256 are unchanged
  from the beginning of this polish task. Existing uncommitted work was preserved.
- Full-data old/new renderer comparison: identical numeric traces and statistical
  hover values for all requests and Brooklyn Q1. All prior benchmark cohort
  counts, cutpoints, exclusions, denominators and output bounds match.
- Programmatic camera/key containment checked at 1024/1440/1920px, plus window
  button semantics, default ranges, empty states, tables and HTML structure.
  Browser review remains pending: no installed or connected browser was available.
  No screenshot, cross-platform or remote CI validation is claimed.

The current task modified `visualizations/{bivariate,survival,timeseries,member1}.py`,
`benchmarks/member1_benchmark.py`, `tests/test_member1.py`, and
`docs/{VISUALIZATION_SPEC,CHART_METHODS,PROJECT_STATUS}.md`; it added
`benchmarks/review_html.py`. The following sections also retain the earlier Phase 2A
implementation and full-data evidence.

## Implemented

- `pipeline/chart_data.py`: exact district counts/known-label rates, complete daily
  calendar/exact completed median/rolling trends, and streamed exact Kaplan–Meier
  with Greenwood log-log pointwise intervals and bounded display buffers.
- `pipeline/query.py`: reviewed exact median metric with denominator; context-managed
  ordered survival frequency stream in 4,096-row batches. Existing APIs, parameter
  safety, filters, footer checks, snapshot guards and ordinary output caps preserved.
- `visualizations/bivariate.py`, `survival.py`, `timeseries.py`: pure interactive
  Plotly renderers accepting documented small aggregate tables. Genuine 3×3 map
  key; valid right censoring; linked daily date axes and optional trends.
- `visualizations/member1.py` and `app.py`: one shared FilterSpec; cached aggregate
  tables; exclusions, confidence/trend controls and errors; diagnostics in an
  expander. The biased demo retains diagnostics without population charts.
- `benchmarks/member1_benchmark.py`: repeatable real-data timings, population
  reconciliation and six HTML review exports. Small measured JSON is included for review;
  HTML, raw and full Parquet artifacts remain ignored.
- Synthetic analytical/statistical/renderer/filter/app tests; full local quality
  validation summary; documentation of definitions, input schemas, exclusions,
  measured full quality and performance, plus working team examples.

The stored **52-column schema 1.0.0**, original filters, label/censoring definitions,
cutoff, source scope, dependencies, demo and GeoJSON are unchanged. The map uses
all 59 validated districts and reports excluded JIAs/unmapped requests. No other
member's charts or final model training was added.

## Full data and measured performance

Start count = downloaded = processed = **3,652,435**, difference **0**, duplicate
and missing IDs **0**. A fresh streaming Parquet validation passed in **41.258 s**;
its SHA-256 matches the build report. Valid closures **3,593,599**, censored **47,756**,
unknown outcomes **11,080**. District matches **3,596,942**, JIA **15,408**, unmatched
**40,085**. See [DATA_QUALITY.md](DATA_QUALITY.md) for invalid date/duration counts,
percentages, timestamps, all flags and snapshot limitations. No ingestion was needed.

Three-run median preparation times on the real full artifact: map **157.077 ms**,
daily **240.319 ms**, exact survival **3,981.067 ms**. Whole benchmark process peak
RSS including HTML export: **373.91 MiB**. Brooklyn Q1 medians: **167.939 / 131.955 /
493.830 ms** respectively. Every query used all matching requests. See
[PERFORMANCE.md](PERFORMANCE.md) for environment, caveats and raw results.

## Executed verification

Local Python 3.12.3 on Ubuntu/WSL2, existing pinned dependencies. The Phase 1.5
baseline had 126 passing tests. Phase 2A added 35 tests; Phase 2A.1 adds eight presentation tests.
Final local results are recorded below. No CI test calls the live NYC API or requires the large local artifact.

- Full streaming `check_parquet(Path("data/processed/requests.parquet"))`: passed
  schema, global uniqueness and outcome validation for 3,652,435 rows. Persisted
  local report `data/processed/requests.validation.json`; small evidence summary
  [full-validation-summary.json](../data/metadata/full-validation-summary.json).
- Full SHA-256 independently recomputed and matched existing quality report.
- `python -m benchmarks.member1_benchmark --dataset full --output benchmarks/member1_results.json`:
  completed three repetitions, two cohorts, all reconciliations and six figure exports.
- Actual full-data Streamlit AppTest: no exceptions/errors, three plots; default
  date-filtered count **3,651,639**. Brooklyn: **1,078,061**, three plots. Empty borough
  selection: **0**, no plots and no errors. The default date range excludes the
  artifact's 796 unresolved creation dates consistently in every component.
- Pure figure serialization and input immutability tests passed. Browser screenshot,
  accessibility and pixel-level review were not executed; reproducible HTML/manual
  interaction procedure is in [VISUALIZATION_SPEC.md](VISUALIZATION_SPEC.md).


| Final command | Result |
| --- | --- |
| `.venv/bin/python -m pytest -q` | **169 passed in 28.12 seconds**, no pytest warnings |
| `.venv/bin/python -m ruff check .` | All checks passed |
| `.venv/bin/python -m ruff format --check .` | 33 files already formatted |
| `.venv/bin/python -m pip check` | No broken requirements |
| `git diff --check` | Passed |

New tests cover analytic KM probabilities/Greenwood bounds and tied censoring,
zero-time/all-censored/all-event cases, malformed streams, fixed fetch batches,
bounded exact retained points, all nine bivariate classes, tie-preserving bins,
59-district inclusion/JIA exclusions, missing/zero denominators, exact even-sample
medians, zero days and rolling windows, shared filter propagation, empty selections,
renderer serialization/immutability, full-mode app controls and demo restrictions.

## CI and cross-platform status

The earlier Windows failure involved global runner `pipx` requiring packaging>=26.3
while the project pins packaging24.2. Phase 1.5 repaired isolation, creating an
explicit Python3.12 `.venv-ci` in both Ubuntu/Windows jobs; pip check, Ruff and pytest
remain enabled inside it. Project dependencies were not upgraded for runner tools.
That workflow is preserved. No remote workflow result or native Windows/macOS
execution was verified during Phase 2A; local Linux/WSL results do not establish
remote success. No OS-specific runtime path or new dependency was introduced.

## Remaining limitations and next steps

1. Review local changes, authorize a commit/push when ready, then inspect Ubuntu
   and Windows CI. No remote success is claimed here.
2. Follow the HTML/Streamlit visual-review checklist; inspect narrow filters,
   sparse districts, tiny tail risk sets, zoom and tooltips on the presentation host.
   Bivariate palette accessibility has not been formally audited.
3. KM estimates/intervals are exact at retained times; intermediate plotting steps
   are omitted. Censor marks are omitted; intervals are pointwise and rely on
   independence assumptions. No causal comparison or actual resolution is inferred.
4. Closed-only daily medians omit pending/unknown outcomes. Known long-label rates
   include mature open positives. The biased sample cannot estimate population
   trends. Historical 2025 boundary agreement remains unverified.
5. Members 2 and 3 should use the same FilterSpec and immutable Parquet through
   reviewed small aggregates, following [TEAM_GUIDE.md](TEAM_GUIDE.md). No independent
   ingestion/preprocessing/global-filter implementations. Keep chart input contracts
   explicit and do not substitute a limited preview for a statistical population.
6. Benchmark concurrent users, combined nine-chart workloads and memory on the
   deployment host; a DuckDB buffer limit is not a whole-process RAM limit. Keep
   local data/temporary spill space available. Share full artifacts outside Git
   with their checksums or use the explicit documented ingestion workflow for a
   separate fresh snapshot. Do not reingest/rebuild this validated artifact needlessly.
7. Complete the other six charts, two final ML tasks, English report/presentation
   and final integration before November 15, 2026, 23:59.

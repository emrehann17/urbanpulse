# Phase 3A: reproducible ML baselines

K-Means and Logistic Regression are implemented and have been run against the
local full 2025 Parquet snapshot. They are descriptive university-project baselines;
no dashboard, final ML visualization, or deployment is included. Methodology and
predictor provenance are in [ML_DESIGN.md](../docs/ML_DESIGN.md).

## Run and reproduce

Use the project's Python 3.12 virtual environment and the existing full dataset:

```bash
python -m pip install -r requirements-dev.txt
python -m ml.train --dataset full --output ml/local
python -m pip check
python -m ruff check .
python -m ruff format --check .
python -m pytest -q
```

On Windows, activate `.venv\Scripts\Activate.ps1` or call
`.venv\Scripts\python.exe`; on Linux activate `.venv/bin/activate`.
Training is offline. It fails if the full Parquet, matching quality report, or
required provenance is missing; it never substitutes demo data or downloads data.
The source must remain immutable during a run. The CLI verifies the 52-column
schema, full/unsampled provenance, SHA256, count, unique IDs, and extraction cutoff.

Defaults: seed 2025, 512 MB DuckDB buffer, one SQL/numerical thread, train cap 200k,
validation/test caps 60k each. `--train-limit`, `--validation-limit`, `--test-limit`
accept 1..1,000,000; they change only deterministic within-partition sampling.
`--memory-limit-mb` controls the DuckDB buffer, not process RSS. No dense one-hot
matrix or full-dataset DataFrame is built. Use a separate result directory for
experiments to preserve the reviewed default outputs:

```bash
python -m ml.train --dataset full --output ml/local/small --results ml/local/small/results --train-limit 50000 --validation-limit 20000 --test-limit 20000
```

`ml/local/` is ignored and contains serialized estimators/preprocessors, copies of
outputs, and run/cohort metadata. Default reviewable outputs are:

- `ml/results/district_clusters.csv`: 59 district rows, no individual requests.
- `ml/results/kmeans_metrics.json`: candidates, selected solution, cluster summaries,
  feature/category mapping, PCA variance, preprocessing, source identity, and runtime.
- `ml/results/logistic_metrics.json`: cohort audit, sample fractions, validation/test
  metrics, baselines, coefficients, sparse encoding, provenance, and runtime.

Completed K-Means outputs are saved before Logistic Regression begins. If a later
stage fails, its traceback is the failure record and earlier files remain; check
run timestamps/source hashes before combining files from separate runs. Only load
local joblib artifacts you trust, using the pinned package environment. Models
contain no request-level training table; request samples are never written.

## Member 3 cluster CSV contract

```python
import json
import pandas as pd

clusters = pd.read_csv("ml/results/district_clusters.csv", dtype={"boro_cd": "string"})
with open("ml/results/kmeans_metrics.json", encoding="utf-8") as handle:
    metadata = json.load(handle)
assert len(clusters) == 59
assert clusters.source_sha256.eq(metadata["source"]["parquet_sha256"]).all()
# Join boro_cd to GeoJSON properties.boro_cd. Use cluster_id as a categorical color.
# pca_x/pca_y already exist; do not refit or rescale them for the saved solution.
```

| Columns | Meaning |
| --- | --- |
| `boro_cd` | Validated three-character ordinary district code; unique key. |
| `cluster_id` | Zero-based nominal cluster, remapped by smallest member district code. IDs are not ranks and need not match across refits. |
| `pca_x`, `pca_y` | First two PCA coordinates of the identical processed matrix fitted by K-Means; arbitrary axes/signs, not hours or counts. |
| `request_count` | All full-scope requests assigned to this ordinary district. |
| `valid_closures` | Number of valid completed durations contributing to the median. |
| `median_closure_hours` | Exact median valid completed duration in hours; missing stays blank/NaN. Closed-only, not a censoring-adjusted estimate. |
| `known_long_labels`, `long_closures` | Rate denominator and numerator under the unchanged strict >168-hour target. |
| `long_closure_rate` | Numerator/known denominator; missing if undefined, never silently zero. Includes eventual late closures and mature open positives. |
| `borough_mismatch_count` | Board/borough disagreements retained for geographic audit. |
| `complaint_share_0` through `complaint_share_7` | District proportions; names mapped in companion JSON `complaint_categories`. |
| `complaint_share_other` | All other complaint types, including missing, divided by all district requests. |
| `duration_imputed`, `rate_imputed` | Whether model preprocessing imputed a missing/low-support statistic; raw exported values remain unchanged. |
| `selected_k`, `seed`, `model_version`, `schema_version`, `source_sha256` | Model/source identity repeated to make the CSV usable independently. Full settings are in JSON. |

Use categorical legends and fixed cohort labels. Do not call clusters “best/worst”
or causal service-quality measures. Keep JIAs/unmatched areas outside this 59-row
join and disclose their excluded counts. Displaying filters must not imply that a
saved full-year solution was refitted to filtered requests.

## Measured default run: 2026-11-12

Source SHA256:
`8b2c29b7e860a344f29e53834dc36093feb3aa1bc873a69a2f00e9184810821a`.
The source contains **3,652,435 rows / 52 columns**, cutoff
`2026-11-11T13:05:11.985204+00:00`. Package pins: scikit-learn 1.7.2, SciPy 1.16.3,
joblib 1.5.2, threadpoolctl 3.6.0; existing dependency pins were preserved.
Installation and imports succeeded on Linux/Python 3.12.3. A Python 3.12
Windows-wheel resolution smoke check also succeeded (`ml/local/windows-resolution.json`);
this is not Windows execution and does not validate platform-specific runtime behavior.
Existing Ubuntu/Windows CI configuration is unchanged.

K-Means used 59 full-dataset district aggregates representing **3,596,942 requests**.
Excluded: **15,408 JIA** and **40,085 unmatched** requests. No feature required
imputation in this run. All 2,530 board/borough disagreement flags remain auditable
in the source; the district CSV reports those among ordinary districts.

| K | Silhouette | Candidate cluster sizes (original sklearn IDs) | Accepted |
| ---: | ---: | --- | --- |
| 2 | 0.326748 | 23, 36 | Yes; selected maximum |
| 3 | 0.268555 | 21, 16, 22 | Yes |
| 4 | 0.264866 | 20, 22, 16, 1 | No: singleton |
| 5 | 0.219378 | 14, 16, 19, 1, 9 | No: singleton |
| 6 | 0.223692 | 8, 17, 13, 14, 6, 1 | No: singleton |

Exported IDs have sizes **cluster 0: 36; cluster 1: 23**. PCA explains 49.70% and
27.73% of processed variance (77.43% together). These clusters have similar median
district volumes but different complaint composition and closure statistics:

| Descriptive statistic | Cluster 0 | Cluster 1 |
| --- | ---: | ---: |
| Total requests | 2,225,959 | 1,370,983 |
| Median district request count | 56,248.5 | 55,674 |
| Median of district completed-duration medians, hours | 4.12 | 18.44 |
| Pooled known-label denominator | 2,219,391 | 1,368,304 |
| Pooled beyond-seven-day rate | 14.53% | 20.83% |
| Mean district Illegal Parking share | 20.39% | 9.66% |
| Mean district HEAT/HOT WATER share | 5.49% | 13.31% |
| Mean district UNSANITARY CONDITION share | 2.09% | 5.11% |

Cluster 0 has more parking-related reporting and shorter completed-duration
medians; cluster 1 has more heat/hot-water and sanitation reporting and a larger
known-label long-closure fraction. These describe mix and administrative outcomes,
not causal differences or rankings. Full membership and remaining shares are in JSON.

Logistic Regression used **channel + creation hour/weekday/month**. Complaint type,
borough, and other uncertain mutable snapshot fields were excluded after reviewing
source metadata. Channel had no missing values; the 796 missing calendar rows were
invalid creation dates and were excluded. Cohort counts are exact SQL aggregates:

| Partition | Valid-date rows | Unknown labels excluded | Eligible | Used | Eligible not sampled | Used fraction |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Jan–Aug train | 2,376,996 | 8,291 | 2,368,705 | 200,000 | 2,168,705 | 8.4434% |
| Sep–Oct validation | 638,857 | 802 | 638,055 | 60,000 | 578,055 | 9.4036% |
| Nov–Dec test | 635,786 | 1,191 | 634,595 | 60,000 | 574,595 | 9.4548% |

Separately excluded **796 invalid creation dates**, all with unknown labels; zero
out-of-year valid dates. Total distinct exclusions: **11,080**, not 11,876.
Eligible but unsampled across partitions: **3,321,355**. Sampling is independent of
labels, ordered by seeded SHA256 and ID, without balancing. Train prevalence was
17.2155%; validation 17.0383%; test **15.8883% (9,533/60,000)**.

Validation F1 selected threshold **0.2381669074**. Fixed test results:

| Metric | Logistic Regression | Majority class | Training prevalence |
| --- | ---: | ---: | ---: |
| Average Precision / PR-AUC | 0.321784 | 0.158883 | 0.158883 |
| ROC-AUC | 0.747003 | 0.500000 | 0.500000 |
| Precision | 0.325874 | 0 | 0 |
| Recall | 0.551453 | 0 | 0 |
| F1 | 0.409663 | 0 | 0 |
| Brier score | 0.120602 | 0.158883 | 0.133816 |

Test confusion matrix `[[TN, FP], [FN, TP]]`:
`[[39592, 10875], [4276, 5257]]`. Both baseline matrices are
`[[50467, 0], [9533, 0]]` at their fixed threshold 0.5. Baseline probabilities
are derived from training alone. PR-AUC here means non-interpolated Average
Precision, not trapezoidal integration. The estimator is fitted to **200,000
sampled rows**, not the full dataset.

Final measured wall times: verification **1.64 s**, district aggregation/fitting
**2.86 s**, classifier extraction/fitting/evaluation **7.43 s**, total **11.94 s**.
Process peak RSS was **660.68 MiB**, exceeding the 512 MB DuckDB buffer setting as
expected because it also includes Python/Arrow/sklearn allocations. K-Means-stage
process high-water RSS was 510.93 MiB. The train encoding was CSR **200,000 × 44**,
800,000 nonzeros, **10,400,004 bytes** of sparse storage. No out-of-memory or
convergence failure occurred. Timings are machine-specific and include extraction;
RSS is cumulative process high-water memory, not incremental per-model allocation.
The first successful run took 12.23 s / 660.54 MiB. Repeating the default run
produced a byte-identical district CSV and identical selected K, candidate scores,
cluster profiles, PCA variance, classifier coefficients, threshold, and all
validation/test/baseline metrics; only run metadata/timing and added explicit
exclusion reporting differ.

This is a retrospective single-snapshot evaluation, not a prospective backtest.
Unseen September–December month categories have no learned month-specific effect.
Historical feature revisions, related requests, temporal drift, censored closure
bias, geography vintage, and only 59 district observations limit conclusions.
Stability, uncertainty intervals, prospective validation, and final visuals remain
future work. Do not tune subsequent choices on these published test metrics.

## Verification outcome

The final local checks passed: `pip check`, `ruff check .`, `ruff format --check .`
(39 Python files), and `pytest -q` (**202 tests**, including 33 ML tests). The
saved-model round-trip test emits four upstream joblib/NumPy 2.5 deprecation
warnings about array-shape assignment; predictions after reload are identical.
No warning is suppressed and no existing dependency pin was changed.
`git diff --check` also passed. No remote CI run, commit, push, or merge was performed.

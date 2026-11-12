# Phase 3A — implemented ML baselines

`ml/` implements two offline, reproducible baselines against the shared 52-column
contract. No pipeline API, target, dashboard, or final visualization is changed.
See [training and export instructions](../ml/README.md) and the measured aggregate
outputs in `ml/results/`. Neither model uses the biased integration demo.

## Source verification and reproducibility

The CLI requires `--dataset full`, resolves `data/processed/requests.parquet`
through the existing loader, checks the exact Arrow schema and full/unsampled
provenance, and hashes the entire file in streaming chunks. Its SHA256, row count,
and provenance must match the adjacent `requests.quality.json`. A DuckDB scan
checks distinct nonnull IDs and a single extraction cutoff matching provenance.
This relies on the pipeline's existing outcome quality audit; it does not redefine
or repair outcomes. File size, inode, and mtime are checked around each SQL query.
Do not replace source files during a run.

Both results record source/manifest/geography hashes, cutoff, feature names, seed
2025, package versions, and run timings. One DuckDB thread, one numerical thread,
explicit K-Means `n_init=50`, deterministic PCA SVD, and seeded Logistic Regression
support repeatability on the pinned environment. Floating-point coordinates may
differ slightly across platforms; elapsed times and run timestamps will differ.

DuckDB projects and aggregates directly from Parquet with a default 512 MB buffer
limit and temporary spill directory. This is not a total-process RAM cap. Only 59
district rows and at most 200k/60k/60k projected request rows enter Pandas by default.
No full 52-column DataFrame or dense request-level one-hot matrix is constructed.
NY calendar split boundaries are converted to UTC epoch microseconds in Python;
DuckDB does no timezone conversion or extension download. Large serialized models
remain under ignored `ml/local/`; shared CSV/JSON contain only aggregates.

## A. K-Means district profiles

**Question:** Which NYC community districts have similar reported service request
profiles? Full-scope SQL aggregates use every request assigned to the validated 59
ordinary codes, with `geography_status='community_district'`. JIA and unmatched/
invalid geography counts are exported separately. All 59 must have requests or
fitting fails explicitly. Invalid creation dates remain in descriptive counts
because the ingestion scope is already 2025; Logistic Regression excludes them.
Borough mismatch counts accompany the district rows. Boundary release 26c (2026)
is not verified historical 2025 geography; a board-code join is not a spatial join.

The fitted features are:

- `log1p(request_count)`; reported volume, without a population denominator.
- Eight most frequent nonnull complaint types among ordinary districts (count
  descending, alphabetical tie-break), plus Other including all remaining and null
  types. These are proportions of **all** requests in each district. This full
  descriptive reference window is separate from classifier preprocessing.
- `log1p(median_closure_hours)`, the exact median of valid completed durations,
  accompanied by `valid_closures`. It excludes censored observations and can be biased.
- `long_closure_rate = long_closures / known_long_labels`. This uses the existing
  nullable label: valid completed negatives/positives and sufficiently mature open
  positives; no immature open request is treated as negative. It is not the fraction
  currently open or a rate over all requests.

Raw undefined medians/rates stay null in exports. Before distance calculations,
statistics with fewer than 30 supporting observations become missing, are imputed
with the reference districts' feature medians, and receive missingness indicators.
An entirely unsupported feature fails rather than becoming zero. Counts of missing
features and the learned medians are recorded. An empty district fails. No missing
feature required imputation in the measured full run; sensitivity to imputation in
other snapshots remains future work.

After standardizing each column, all columns in each of four blocks (composition,
volume, duration, rate, including any corresponding missing indicators) receive
weight `1/sqrt(number of columns in block)`. Thus nine composition columns do not
get nine times the nominal squared-distance weight of volume. Correlations still
exist; this is an explicit practical weighting choice, not a discovered metric.

Fit K=2..6 using Euclidean distance, seed 2025, `n_init=50`, Lloyd iterations. Reject
any candidate with a cluster smaller than three districts or fewer than K distinct
clusters. Choose the remaining maximum silhouette, breaking exact ties toward
smaller K. Record every candidate's silhouette, inertia, sizes, and eligibility.
The selected solution and raw cluster summaries are in `kmeans_metrics.json`.
PCA fits the **identical imputed, standardized, weighted matrix** and exports two
coordinates plus explained-variance ratios. PCA is a projection for Member 3;
K-Means does not fit on the two-dimensional projection.

Cluster IDs are remapped to ascending minimum district code, start at zero, and
have no ordinal meaning. Summaries report district membership, typical district
volume/median duration, pooled known-label rate, and mean district complaint
shares. Clusters are **descriptive, not rankings or causal conclusions**. There are
only 59 observations. Bootstrap/time-window/seed stability, alternate feature
weighting, and demographic adjustment are future work, not validated claims.

## B. Logistic Regression: administratively unclosed beyond seven days

**Question:** Can creation-time attributes predict whether a request exceeds 168
hours before recorded administrative closure? The unchanged nullable target is
`is_long_closure`:

| Existing evidence | Label |
| --- | --- |
| Valid consistent completed duration <=168 hours | False |
| Valid consistent completed duration >168 hours | True, even if eventually closed |
| Non-closed without closure date, observed age >168 hours | True |
| Immature open, invalid times, missing status, or inconsistent outcome | Unknown; exclude |

Exactly 168 hours is not beyond seven days. Labels are never imputed. Administrative
closure does not establish actual problem resolution or capture reopening history.

### Predictor review

The local source snapshot [`erm2-nwe9-schema.json`](../data/metadata/erm2-nwe9-schema.json)
and [publisher metadata](https://data.cityofnewyork.us/api/views/erm2-nwe9.json)
identify the creation timestamp and how a request was originally submitted.
The implemented allowlist is the following conservative subset of
`pipeline.features.CREATION_FEATURES`; the public pipeline allowlist is unchanged.

| Field | Decision and limitation |
| --- | --- |
| `open_data_channel_type` | Include: documented submission channel, an origin attribute; snapshot corrections still cannot be reconstructed. |
| `created_hour`, `created_weekday`, `created_month` | Include: derived by the existing pipeline from the creation timestamp in New York time; invalid timestamps are excluded. |
| `borough` | Exclude: submitter location is geovalidated; no version history proves current values are the creation-time values. |
| `complaint_type`, `descriptor`, `agency`, `location_type`, `community_board` | Exclude: current classification/assignment/geography is not established as immutable creation-time information. |
| `created_quarter` | Exclude: redundant with month. |

This deliberately narrower baseline sacrifices predictive power to avoid assuming
that mutable snapshot fields are historical predictors. Full-data nonnull counts
and distinct counts for included predictors are recorded as availability diagnostics,
not fitted encodings. No outcome, resolution field, status, unique ID, cutoff, audit
flag, or duration enters the feature matrix. IDs are used only for sampling.
The fitted pipeline rejects any extra/missing predictor columns.

### Cohorts, sampling, and fitting

New York calendar boundaries, start inclusive and end exclusive:

| Partition | Start | End | Default maximum |
| --- | --- | --- | ---: |
| Train | 2025-01-01 | 2025-09-01 | 200,000 |
| Validation | 2025-09-01 | 2025-11-01 | 60,000 |
| Test | 2025-11-01 | 2026-01-01 | 60,000 |

Exclusions are disjoint: invalid/missing creation time first, out-of-year dates
second, then unknown labels within valid partitions. Cohort JSON reports original
counts, known/unknown labels, and positives; explicit exclusion totals are also saved.
Invalid-date unknowns overlap the overall unknown total and must not be counted
twice. Empty train/validation/test partitions fail explicitly; single-class train
or validation fails. Single-class test returns null ranking metrics with a reason.

Within each eligible partition, order by hex `SHA256(str(seed) + ':' + unique_key)`,
then lexical ID, and keep at most its cap. This approximates uniform selection
without replacement, is independent of outcomes and physical row order, and
uses a stable hash rather than engine-version-specific random sampling. Actual
fractions and eligible-but-unsampled counts are recorded. Evaluation sets retain
natural sampled prevalence; there is no class balancing or stratification.
The classifier is trained on a subset, **not all 3.65 million requests**.

The sklearn Pipeline normalizes missing inputs, imputes an explicit Missing
category, uses sparse OneHotEncoder with training-only rare grouping
(`min_frequency=20`, `max_categories=32` per field), and fits L2 Logistic Regression
(`C=1`, `solver='liblinear'`, `tol=1e-6`, `max_iter=1000`, no class weights).
Calendar values are nominal categories. All preprocessing fits only on train.
Unseen categories map to a learned infrequent bin if present, otherwise an all-zero
block. In particular, September–December month effects cannot be learned from
January–August; these months receive no fitted month-specific effect in this run.
No hyperparameter search or test-based feature selection is implemented.
Convergence warnings cause failure instead of silently publishing an unfinished fit.

Select the threshold maximizing validation F1, choosing the largest threshold on
an exact tie. This weights precision/recall through F1 and is not a validated
operational cost function. Only then score the untouched test sample. Report
non-interpolated Average Precision (the chosen PR-AUC convention), ROC-AUC,
precision, recall, F1, confusion matrix, Brier score, prevalence, and sizes.
Precision/recall/F1 use zero on zero-division; ranking metrics are null for a
single-class cohort. Compare to the training majority class (constant probability
0 or 1) and training prevalence (constant probability), both classified at 0.5.
Constant scores have AP equal to evaluation prevalence and ROC-AUC 0.5 when both
classes occur. Coefficients are descriptive conditional associations, not effects.

This is a **retrospective single-snapshot evaluation, not a true prospective
backtest**. A late-2026 snapshot supplies outcomes that were not necessarily known
at the historical training cutoff. A deployment study would need historical
feature versions, label availability cutoffs, maturation embargoes, related-request
grouping, drift/uncertainty/subgroup audits, and calibration/threshold validation.
These are future work; no deployment readiness is claimed.

## Deferred Member 3 integration

Use the persisted 59-row cluster CSV and companion metadata without refitting.
Dashboard filters must not silently retrain the models. Final cluster/scatter
visualizations, model-driven dashboards, prospective evaluation, stability studies,
and survival models remain outside Phase 3A. See `ml/README.md` for column semantics.

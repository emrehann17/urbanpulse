# Future ML design — no models trained in Phase 1

Both future models consume the versioned shared Parquet contract. Fit models on
a reviewed full-scope snapshot, not the integration demo. The current data describes
administrative records, not causal service quality or all neighborhood needs.

## A. K-Means district profiles

**Question:** Which of the 59 community districts have similar reported request
profiles? Use validated `boro_cd`, `geography_status='community_district'`, and
report excluded unmatched requests and JIAs separately. Audit borough-mismatch
flags. Boundary vintage and geographic join uncertainty must accompany results.

One row per district in a fixed analysis window. Candidate blocks:

- Complaint-category proportions, combining rare categories into a training-defined
  Other group; proportions distinguish composition from volume.
- `log1p(request_count)` as a separate volume feature. It is not population-adjusted
  demand. Add population denominators only from a separately verified source.
- Median and upper-quantile valid closure hours, valid closure fraction, and
  mature long-closure rate with explicit known-label denominator.
- Agency proportions, only if they add information beyond complaint mix.

Report observations supporting every district statistic. Censored requests do not
have observed completion times; closed-only medians can be biased. Prefer later
censoring-aware summaries when implemented, or label those medians explicitly.
Do not replace undefined district statistics with zero. Set minimum support,
exclude unsupported districts transparently or impute training-set medians and
include missingness indicators in a sensitivity analysis.

Complaint and agency proportions overlap; concatenating all columns can overweight
the same composition signal. Consider one composition block first, group weights,
and sensitivity to including both. Transform skewed counts/durations with log1p,
then standardize numeric columns; fit scaling/imputation only on the reference
window. Explain that standardized features, not raw hour/count units, determine
distance. A future scikit-learn Pipeline should make this reproducible.

Evaluate several small K values using silhouette scores, within-cluster variation,
minimum cluster size, and domain interpretability. With only 59 districts, do not
claim a statistically established taxonomy. Inspect stability under bootstrapped
requests, different time windows, and random seeds; document seed and n_init.
Translate cluster centers back to interpretable profiles. Clusters are descriptive,
not district rankings or causal effects. Persist model metadata and input snapshot
hashes, then add the final chart in a later phase.

## B. Logistic regression: unresolved beyond seven days

**Prediction time:** request creation. **Target:** whether the request's recorded
closure duration exceeds 168 elapsed hours. The label is `is_long_closure`:

| Evidence at extraction cutoff | Label |
| --- | --- |
| Valid consistent closure, duration <=168 hours | False |
| Valid consistent closure, duration >168 hours | True |
| Non-closed with no closure date, observed age >168 hours | True |
| Non-closed, age <=168 hours | Unknown; exclude from supervised labels |
| Invalid timestamps, missing status, or status/date conflict | Unknown; investigate/exclude |

At exactly seven days an open observation is still unknown under this strict
“beyond” definition. A completed event at exactly seven days is negative. This
predicts unresolved status **in the dataset**, not whether the underlying issue
was actually solved. Current snapshots cannot reconstruct repeated reopening
history. Preserve `closure_event` and `observed_hours` for future survival work;
logistic regression is the specified classifier, not a survival estimator.

Creation-time candidate columns are centralized in
`pipeline.features.CREATION_FEATURES`: borough, community_board, complaint_type,
descriptor, agency, open_data_channel_type, location_type, created_hour,
created_weekday, created_month, created_quarter. Candidate availability is a design
assumption to verify with source semantics: agency or classifications may be
reassigned after creation. Exclude such fields if reliable creation-time values
cannot be established. ZIP and coordinates are optional reviewed additions, not
currently in the allowlist; high cardinality and missingness need care.

**Never use as predictors:** closed_date, closure_hours, duration_bucket,
is_long_closure, closure_event, observed_hours, current status/is_closed,
resolution_description, resolution_action_updated_date, extraction_cutoff,
after-cutoff/outcome-quality flags, or unique_key. `created_date` may be used for
temporal splitting and derived calendar predictors, never as a future lookup key.
Do not impute labels. Do not use full-dataset target encodings or aggregates that
include test-window outcomes. Exclude raw audit columns from the feature matrix.

Fit preprocessing only on training rows: explicit Missing category for nullable
categoricals; one-hot encoding with unknown-category handling and a documented
rare-category threshold; sensible median imputation for numeric calendar fields
(or exclude invalid creation times); scale numeric values if appropriate for
regularization. Avoid including redundant month and quarter features blindly;
compare a simple specification to alternatives. Validate models through a
scikit-learn Pipeline once the ML phase begins, without hand-encoding the full
DataFrame before splitting.

Use chronological cohorts: for example January–August train, September–October
validation, November–December test. Finalize dates after checking support. The
late-2026 snapshot supports retrospective cohorts, not a true historical deployment
backtest. A prospective backtest would require labels available by each training
cutoff, a seven-day maturation embargo, and historical feature snapshots. Do not
claim that this single snapshot supplies those. Group related duplicates if
identifiable, and inspect distribution drift between cohorts.

Evaluate against majority-class and prevalence baselines. Report PR-AUC, ROC-AUC,
precision, recall, F1, confusion matrix, and calibration/Brier score with class
prevalence and sample sizes. Pick a threshold using validation data and the intended
cost of missed long cases versus false alarms; hold test data untouched. Consider
balanced class weights as a tunable option, not an automatic improvement. If
resampling is tested, do it only inside training folds. Report subgroup metrics
with adequate support and uncertainty; avoid interpreting coefficients as causal.

## Readiness and future integration

Phase 1 supplies nullable targets, censoring features, a creation-feature allowlist,
shared filters, and provenance. It does not supply trained estimators, fitted
preprocessors, model files, predictions, or final ML visualizations. Add those
under `ml/` after review. Global filters should control the displayed population;
models should have an explicit stable training cohort and not silently retrain
whenever a dashboard widget changes. Persist feature schema, target definition,
training range, package versions, evaluation results, and source checksum with
each future model artifact.

# Member 1 statistical methods and aggregate contracts

These are **transient chart inputs**, not additional columns in schema 1.0.0.
`load_data`, `apply_filters`, `get_filter_options`, `get_data_summary`, `FilterSpec`
and existing query interfaces keep their prior behavior. Creation dates are New
York calendar dates; durations remain elapsed hours across timezone transitions.
No outcome definition, label threshold or extraction cutoff was changed.

## Query and memory boundaries

`ParquetQuery.aggregate(..., metrics=("closure_median_hours",), filters=spec)` adds
one reviewed metric: SQL `median(closure_hours)`, exact, ignoring nulls, automatically
accompanied by `valid_closures` and `requests`. Even-sized groups use the mean of
the two central observations. Zero valid closures produce null, never zero hours.

`ParquetQuery.survival_counts(*, filters=None)` is a context manager yielding tuples
`(borough: str, observed_hours: float, events: int, censored: int)` ordered by
borough then exact time. SQL groups tied values and selects known outcomes with
finite nonnegative observed hours. Consume it inside `with` to release connections
on exceptions/early exits. `fetchmany(4096)` bounds Python input batches. There is
no LIMIT on statistical input. SQL may sort/group millions of times; DuckDB's
512 MB setting bounds its buffer manager, not total process allocations. Temporary
spill storage and two threads follow the existing query policy. No SQL expressions
or identifiers are provided by chart users; filters and paths remain parameters.

A separate borough aggregate supplies cohort totals and unknowns. Validated contract
invariants make `closed + censored` exactly the stream population. Missing or
malformed life-table observations cause the estimator's exhaustion checks to fail,
not silently disappear. The existing snapshot fingerprint is checked across each
operation. Serving artifacts must remain immutable.

## District table and binning

`district_data(query, filters, geojson, *, min_known=30) -> DataFrame`

| Column | Type / meaning |
| --- | --- |
| boro_cd | String; one of exactly 59 verified ordinary district identifiers |
| requests | Integer; all matching requests assigned to that district |
| known_long_labels | Integer; nonnull seven-day labels |
| long_closures | Integer; true labels, including sufficiently mature censored positives |
| long_closure_rate | Nullable float fraction: long_closures / known_long_labels |
| eligible | Boolean; known_long_labels >= min_known |
| support | Eligible, Insufficient known labels, or No matching requests |
| volume_bin, rate_bin | Integer 0/1/2 for low/middle/high; -1 if ineligible |
| bivariate_class | 3 * rate_bin + volume_bin, or -1 if ineligible |

DataFrame attrs: `population`, `excluded` (JIA/unmatched request counts), `min_known`,
`cuts` (count and rate lower/upper tertile cutpoints). Quantiles use linear
interpolation over eligible district values at 1/3 and 2/3. Bins are <= lower,
> lower and <= upper, and > upper. Equal cuts may leave a tier empty; identical
values are never arbitrarily separated to fill colors. No eligible districts
produces null cuts and an entirely gray map. No-data rows retain zero count but
unknown rate. Cutpoints change with filters. The palette is descriptive, not a
rank of causal service quality.

## Exact Kaplan–Meier and confidence limits

`kaplan_meier(counts, totals, *, max_points=1024) -> DataFrame` is a pure streaming
estimator over ordered aggregate tuples. `survival_data(query, filters,
*, max_points=1024) -> (curve_df, outcomes_df)` supplies its full-data input.

At distinct observed time t_i, let n_i be the risk set immediately before t_i,
d_i the closures, and c_i the censors. Starting with S=1 and n=N:

```text
S(t) = product over t_i <= t of (1 - d_i / n_i)
n_(i+1) = n_i - d_i - c_i
G(t) = sum over t_i <= t of d_i / (n_i * (n_i - d_i))
```

Closures and censors tied at the same time are both in n_i. Apply closures before
removing censors. Zero-duration closures occur at t=0; the initial plotting origin
is the left limit 1, followed by the estimated S(0). There is no delayed entry.
Unknown outcomes do not enter N; valid censors contribute risk until their
extraction-cutoff observation time. S(t) estimates P(T > t), not problem resolution.

For 0 < S < 1, let a=log(-log S), b=1.95996398454 * sqrt(G)/abs(log S).
Pointwise 95% bounds are exp(-exp(a+b)) and exp(-exp(a-b)). At S=1 and S=0,
reported bounds equal S by boundary convention; this is not certainty about the
population. Greenwood's independent-observation/non-informative-censoring assumptions
may fail for 311 data. These are pointwise intervals, not simultaneous confidence
bands or adjusted borough comparisons. The method follows the exponential Greenwood
construction described by [Sawyer](https://www.math.wustl.edu/~sawyer/handouts/greenwood.pdf)
and used in [lifelines](https://lifelines.readthedocs.io/en/stable/fitters/univariate/KaplanMeierFitter.html).
No new survival-library dependency is required.

Curve columns: `borough` string; `hours`, `survival`, `lower`, `upper` floats;
`at_risk`, `events`, `censored` integers. Risk is before the exact plotted time;
event/censor counts belong to that time alone. Outcomes columns: `borough`,
`requests`, `closed`, `censored`, `unknown_outcomes` (nullable integer aggregate
dtypes, nonnull counts). The separate cohort table's valid N is closed+censored.

### Bounded display, not sampled estimation

After all updates at a time, the estimator may retain its exact point. Whenever
the retained buffer approaches its cap, it keeps every second point and doubles
the future retention stride. The initial origin and final observation are retained.
Every intervening time still updates S, G and n. At most `max_points` rows per
borough (allowed 4..4096), at most five boroughs, and a 4,096-tuple input batch are
held in Python. There is no request/time-bin sampling in the estimator.

The drawn horizontal steps skip intermediate jumps, so interpolation between
retained points is a **display simplification**. Probability and CI values at the
retained times are exact; they do not reconstruct all omitted event times. Zoom
cannot reveal omitted points. attrs expose `input_time_groups`,
`plotted_time_groups`, `display_thinned`, `max_points`. This distinction is stated
in the UI and exported reviews. There are no censor tick marks at full scale.

## Complete daily table and rolling trends

`daily_data(query, filters, *, rolling_days=7) -> DataFrame`

| Column | Meaning |
| --- | --- |
| created_day | ISO New York calendar date, selected range intersected with 2025 |
| requests | Exact count, including open/unknown outcomes with valid dates |
| valid_closures | Count of nonnull closure_hours in that creation cohort |
| closure_median_hours | Exact median valid completed duration; NaN without observations |
| request_trend | Trailing rolling_days mean of daily counts, including zero days |
| closure_trend_hours | Trailing median of nonnull daily medians, **not** pooled median |
| trend_valid_days | Number of contributing nonnull daily medians in that window |

There are at most 365 rows. Reindex onto the complete requested 2025 calendar;
only counts become zero. Invalid creation dates are excluded from the calendar
and counted in attrs `unknown_created_day`. With explicit date filters they already
fall outside the population, consistent with `apply_filters`. attrs also include
`population` and `rolling_days`. Windows are trailing, include the current day,
allow partial initial windows (`min_periods=1`), and range from 1 to 31 days.
An all-null median window stays null. Empty selections yield zero counts over
the calendar and null duration statistics; a range outside 2025 yields no rows.

## Pure renderer interfaces

```python
bivariate.create_visualization(chart_df, *, geojson) -> plotly.graph_objects.Figure
survival.create_visualization(chart_df, *, outcomes, confidence=True) -> Figure
timeseries.create_visualization(chart_df, *, rolling=True) -> Figure
```

Each receives its documented aggregate table including attrs; none filters, loads,
queries, trains models or mutates inputs. They specialize the shared
`create_visualization(filtered_df) -> Figure` interface: `chart_df` here means
already-filtered **aggregate** rows, not request-level contract rows. Do not pass
a preview or drop attrs during serialization. Member 1 caches its four small tables
(8 entries, 10-minute TTL); Member 2 separately caches its three exact chart tables
(32 entries, 10-minute TTL). Both key filtered results by FilterSpec and Parquet
path/mtime/size. Existing diagnostics caches remain unchanged. Plotly map rendering uses the documented
[Choroplethmap API](https://plotly.com/python/maplibre-migration/).

## Member 2 chart inputs and display

Member 2 uses the same immutable snapshot and shared `FilterSpec` as the other
dashboard sections. The calendar uses `daily_data(query, filters)`: request counts
are exact by New York creation day, and null creation dates remain a separate
reported total. The Sankey receives exact
`query.aggregate(("agency", "complaint_type"), metrics=("requests",), filters=filters)`
rows. Null category groups are rendered with explicit missing labels; every edge
is retained, and the count total reconciles to the filtered request population.

The ridgeline first ranks complaint types by exact `valid_closures` in the filtered
population, then obtains exact `(complaint_type, closure_hours)` request frequencies
for the six largest cohorts. Null durations and missing complaint labels are not
closure observations. It uses frequency-weighted Gaussian KDE, with one ridge
normalized to unit maximum within each complaint type so shapes can be compared.
The shared x-axis ends at the weighted 98th percentile across the plotted cohorts;
observations beyond that display limit still contribute to each KDE and their exact
count is reported. Exact duration-frequency aggregation uses the normal 100,000
group guard; an over-limit cohort must be narrowed rather than sampled or truncated.
All three visualizations accept exact prepared aggregates and do not read request
previews.

## Phase 2A.1 display-only refinements

All preparation functions, stored data, filter semantics, KM estimates and
confidence intervals are unchanged. The first 30 days is only an initial viewport.
The four Plotly time-window buttons use `relayout` on `xaxis.range` and
`xaxis.autorange`; they never alter trace arrays or censoring. Full observed period
restores the maximum retained observation time (with a minimum one-day span for
degenerate cohorts). Display thinning still applies; zoom does not recover omitted
intermediate steps or censor marks.

`bivariate.classification_thresholds(chart_df) -> DataFrame` formats the existing
cutpoints into Dimension / Low / Medium / High columns for a separate table. It
rounds counts to two decimal places and rates to two percentage decimals **only
for display**. It does not rebin records, change eligibility or replace null rates.
`survival.cohort_summary(outcomes) -> DataFrame` presents exact counts with readable
column labels; Valid observations is closed+censored. Both helpers return new
objects. The chart legend uses short borough names; cohort counts remain accessible.

The seven-day duration trend remains the median of daily medians, not a pooled
seven-day median. Styling, legend placement, axis spacing, window buttons and HTML
structure are presentation changes only. Tests and full-data pre/post comparisons
confirm identical numerical trace values and denominators.

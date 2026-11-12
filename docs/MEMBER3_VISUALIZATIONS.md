# Member 3 visualization specification and presentation notes

Member 3 owns three final interactive Plotly visualizations: the Bipartite Network
Graph, Parallel Coordinates, and PCA Cluster Explorer. They use the shared verified
2025 source and do not retrain either ML model. The former agency × complaint heatmap
is a supplemental prototype and is not counted among the nine final charts.

## Shared scope and integration

Run `python -m streamlit run app.py` and select **full**. The demo is deliberately
not used for population graphics. The bipartite network consumes the same app-owned
`FilterSpec` as diagnostics and Member 1 charts. Its exact small aggregate is queried
from Parquet; no request preview or full request DataFrame is passed to the renderer.

Parallel Coordinates and PCA consume the persisted 59-row
`ml/results/district_clusters.csv` plus `kmeans_metrics.json`. They always describe
the reviewed full-year model. Sidebar filters do not subset, recolor, or refit them.
The app states this distinction explicitly.

## 1. Bipartite Network Graph

**Research question:** Which agencies and complaint types form the strongest
reported-request relationships in the selected 2025 cohort?

**Input:** exact `agency × complaint_type` request counts produced by
`ParquetQuery.aggregate(..., filters=shared_filter_spec)`. Missing category groups
remain in the population denominator but cannot appear as named nodes.

**Display design:** blue agency nodes on the left, orange complaint nodes on the
right, and links whose widths scale with the square root of exact request count.
For readability, the graph retains the top eight agencies, top twelve complaint
types, and at most forty strongest links in their intersection. The title reports
displayed-link count and population coverage; this is a display threshold, not
statistical sampling.

**Measured all-borough 2025 view:** twelve qualifying links show **2,229,352 of
3,651,639 date-filtered requests (61.1%)**. The three largest links are NYPD–Illegal
Parking (**577,131**), NYPD–Noise - Residential (**463,018**), and HPD–HEAT/HOT
WATER (**315,882**). Other prominent links include NYPD–Noise - Street/Sidewalk,
NYPD–Blocked Driveway, and HPD–UNSANITARY CONDITION.

**Interpretation limits:** link volume measures reports, not underlying incidence,
service quality, staffing, or causality. Global filters can change which categories
enter the display. A missing link may fall below the top-category/top-edge display
rule and does not necessarily mean zero requests.

## 2. Parallel Coordinates

**Research question:** How do the 59 ordinary community districts compare across
request volume, administrative closure outcomes, and complaint composition?

**Input:** persisted raw district summaries from the saved K-Means export. Eight
axes show district code, request count, median completed-closure hours,
beyond-seven-day rate, Illegal Parking share, Noise - Residential share, HEAT/HOT
WATER share, and all-other complaint share. Axes retain their original units; the
renderer does not normalize, impute, or mutate exported values.

**Interaction:** drag on any axis to brush districts and double-click an axis to
clear its selection. Line color duplicates the nominal K-Means cluster category.

**Measured profile contrast:** Cluster 0 has a lower median of district completed-
closure medians (**4.12 hours**) than Cluster 1 (**18.44 hours**) and a lower pooled
beyond-seven-day rate (**14.53% vs 20.83%**). Cluster 0 has a larger mean Illegal
Parking share (**20.39% vs 9.66%**); Cluster 1 has larger HEAT/HOT WATER
(**13.31% vs 5.49%**) and UNSANITARY CONDITION (**5.11% vs 2.09%**) shares.

**Interpretation limits:** crossing lines are descriptive profiles, not rankings.
Closure medians use valid completed requests only. Complaint shares reflect reporting
and classification patterns, not population-adjusted need. Brushing changes only the
view; it does not refit the model.

## 3. PCA Cluster Explorer

**Research question:** How are the saved district profiles arranged in the first two
principal-component dimensions, and how do the two descriptive clusters separate?

**Input:** the persisted `pca_x`, `pca_y`, and `cluster_id` values. K-Means was fitted
on the identical processed 12-feature matrix, not on the two-dimensional projection.
The renderer never refits or rescales coordinates.

**Display and interaction:** all 59 districts appear as hoverable points. Hover shows
district code, nominal cluster, request count, median closure hours, and
beyond-seven-day rate. The first two components explain **49.70%** and **27.73%**
of processed variance (**77.43% combined**). The saved solution contains 36 districts
in Cluster 0 and 23 in Cluster 1.

**Interpretation limits:** PCA axes and their signs have no direct hour/count meaning.
Two-dimensional distance is an approximate projection of the processed feature
space. Cluster IDs are arbitrary nominal labels—not best/worst classifications,
causal effects, or validated service-quality tiers. Only 59 observations and one
retrospective snapshot are available; stability and uncertainty are not established.

## Visual review and verification

Local standalone reviews are Git-ignored:

- `ml/local/member3_bipartite_network.html`
- `ml/local/member3_parallel_coordinates.html`
- `ml/local/member3_pca_clusters.html`

The Bipartite and PCA layouts were reviewed in a browser. Parallel Coordinates was
revised after browser review to separate its title, axis labels, and color key.
Programmatic tests cover schemas, exact counts, display coverage, all 59 districts,
metadata compatibility, raw-value preservation, invalid/empty inputs, Plotly
serialization, shared-filter integration, and Streamlit chart counts.

Latest local Windows/Python 3.12 verification:

| Command | Result |
| --- | --- |
| `python -m pytest -q` | **235 passed**, 5 upstream ML/joblib warnings |
| `python -m ruff check .` | Passed |
| `python -m ruff format --check .` | 48 files already formatted |
| `python -m pip check` | No broken requirements |

## Short presentation outline

1. Start with the bipartite graph: explain that it reveals the strongest agency–
   complaint relationships under shared filters and disclose the 61.1% display
   coverage before discussing NYPD/parking/noise and HPD/housing-condition links.
2. Move to Parallel Coordinates: brush high closure-time/rate axes and compare how
   complaint composition differs; stress that colors are descriptive cluster labels.
3. Finish with PCA: explain that the same district profiles are projected into two
   components explaining 77.43% of processed variance; hover representative points
   without calling either cluster better or worse.
4. Close with limitations: reported requests are not service need, administrative
   closure is not verified resolution, the model is one retrospective snapshot, and
   no chart supports causal or performance-ranking conclusions.

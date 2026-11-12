# Member 1 visualization specification — Phase 2A.1

Three of the nine project charts are implemented. These are interactive Plotly
figures, distinct from the existing diagnostic metrics and record preview. No
Member 2/3 visualization or final ML model is implemented here.

## Shared interaction and data scope

`app.py` constructs one immutable `FilterSpec`: borough, complaint type, agency,
and inclusive New York creation dates. Every helper uses this same object through
`ParquetQuery`. None/All is unrestricted; an empty category list selects nothing;
OR operates within categories and AND across categories. Unknown categories yield
empty results. Dates with invalid/DST-unresolved creation timestamps cannot pass
a date filter. The default full-year date widget therefore selects 3,651,639 rows,
796 fewer than the unrestricted artifact. This is the existing filter contract.

No chart loads the entire request DataFrame or derives a statistic from preview
rows. Exact population counts retain unknown and censored records; outcome-specific
statistics name their valid denominators. Sample mode retains diagnostics and
explains why the biased demo cannot estimate population trends. Pure renderers
also support synthetic/demo tables for tests and explicitly labeled development.

Charts are followed by their exclusions and limitations. Empty global selections
show the existing no-results message. Missing geometry or query errors show a
Member 1 error while diagnostics remain accessible. The local GeoJSON must contain
all 59 verified ordinary districts. The stored 52-column schema remains 1.0.0.

## 1. Bivariate community district choropleth

**Question:** Which community districts combine high reported request volume with
high rates of requests remaining unclosed beyond seven days?

- Preparation: exact `boro_cd` counts and long-label numerators/denominators;
  left join onto the verified 59 districts. Exclude and count JIAs and unmapped
  requests; do not fabricate polygons or coordinate assignments for them.
- Rate: positive `is_long_closure` / known `is_long_closure`, including mature
  censored positives. It is not the proportion among completed requests alone.
- Minimum support: 30 known labels (a transparent display threshold, not a formal
  precision guarantee). No requests and insufficient known labels use gray;
  hover distinguishes them. Unmatchable requests appear in the exclusion caption.
- Genuine 3×3 encoding: current-cohort tertiles of count and rate among eligible
  districts, combined as nine colors. Cyan/magenta/purple avoids red/green
  opposition; legend axes and hover labels duplicate the color information.
  This is colorblind-conscious, not a claim of certified universal accessibility.
  Ties stay together, so fewer than nine occupied combinations is legitimate.
- A separate band below the larger map contains both legend axes and all nine
  square swatches, labeled Low / Medium / High. Numeric cuts appear in a separate
  threshold table, rounded only for display. Cuts may
  change after filtering: colors are relative to the current cohort, not fixed
  cross-filter performance standards. Gray is outside the nine classes.
- Hover: district identifier, request count, rate, positive count, known-label
  denominator, support status and both tiers. Pan/zoom is available. Boundaries
  use `Choroplethmap` with local polygons and white background, no API key/tiles.
- Limits: counts are not population-adjusted. Reporting propensity, request mix,
  exposure and administrative practice differ. Associations cannot establish
  unequal service quality or causality. Current 2026 polygons are not historically
  validated for 2025. Flagged board/borough disagreements remain mapped by the
  existing board-derived identifier; the filter still uses request borough.

## 2. Kaplan–Meier survival curves

**Question:** How does elapsed time to recorded administrative closure vary across
boroughs in the selected creation cohort?

- Up to five curves, using valid `observed_hours` and `closure_event`, including
  all valid right censoring. Unknown outcomes are excluded from the estimator and
  counted overall and by borough. The outcome table includes complete request counts.
- SQL streams exact borough/time event and censor frequencies. The estimator
  processes every frequency; no request sampling or grouped-time approximation.
- Vertical axis: estimated probability of still being administratively unclosed
  beyond elapsed time. Horizontal axis: elapsed days since creation, which can
  extend beyond 2025. The legend contains borough names only. A separate cohort
  table reports requests, valid observations, closures, censor counts and unknowns;
  it is expandable in Streamlit and initially expanded in standalone reviews.
- At most 1,024 stored points per borough, including endpoints. Intermediate
  time steps are omitted for display only. Every plotted probability and CI
  includes all preceding event times; the line between retained times simplifies
  the full step function. The UI reports retained versus input time counts.
- Hover reports duration, probability, risk set immediately before the time,
  events/censors **at that exact time**, and pointwise 95% Greenwood log-log CI.
  They are not counts accumulated over a skipped display interval. An initial
  origin shows probability one before any time-zero events.
- The default x-axis shows **0–30 days**. Native Plotly buttons offer First 7 days,
  First 30 days, First 90 days and Full observed period. Each button uses only
  `relayout` to change the x-axis range; all tail observations and confidence
  bounds remain in the figure. No button filters or refits any observation.
- Color plus distinct line patterns distinguish boroughs. Confidence toggle,
  zoom/pan and grouped legend visibility toggles are provided. No
  individual censor marks are plotted at full scale. Tail risk sets are available
  in hover; sparse tails and degenerate boundary CIs demand caution.
- Limits: administrative closure is not actual verified resolution. Censoring
  independence and request independence are assumptions, not verified facts.
  Repeated reports, selection, changing complaint mix and cohort age can distort
  comparisons. No causal interpretation or unadjusted significance claim is made.

## 3. Linked time-series explorer

**Question:** How do daily request volumes and recorded closure times vary across
2025 creation cohorts?

- Exact daily request counts, including valid-date open and unknown-outcome rows.
- Exact median elapsed closure hours for valid completed requests created that
  day, displayed as days. Hover reports both total and valid-closure denominators.
  This is a creation-cohort series, not a calendar of closure events.
- Complete calendar within selected dates intersected with 2025. Zero-request
  days have count zero and duration null. Days without valid closures have a gap
  in the median line. Unknown creation days are reported separately when present
  in the filtered population; no arbitrary day is imputed.
- Two aligned panels share date-range zoom. A range slider, hover, and optional
  trailing seven-day trend support exploration. Count trend is the mean including
  zeros; duration trend is the median of available daily medians, not a pooled
  request median. Daily lines are thin and colored; trends are thicker and dashed.
  The two-row legend sits above the panels, away from the slim bottom slider.
  Increased panel height/spacing and formatted dates improve readability.
  Initial partial windows are allowed; hover gives contributing
  days for duration smoothing. A trend may persist across a daily median gap.
- Limits: closed-only medians omit outstanding and unknown outcomes, can understate
  wait times, and are sensitive to complaint mix and unequal follow-up. The
  survival chart supplies complementary censoring-aware evidence. No population
  trends are presented from the earliest-200-per-month demo.

## Reproducible visual review

```text
python -m streamlit run app.py
python -m benchmarks.member1_benchmark --dataset full --output benchmarks/local/member1.json
```

Choose **full** in Streamlit, try Brooklyn, an agency, a complaint and a narrow date
range, then clear a category to check the no-results state. Diagnostics and all
three charts must use the same cohort. Inspect long-tail KM risk sets and toggle
confidence/trends. Drag the daily range slider and verify both panels zoom.

The benchmark also exports six HTML figures (all requests and Brooklyn Q1) to
`benchmarks/local/member1/`, with embedded Plotly JavaScript, cohort details and
limitations. Open `all_requests_district.html`, `all_requests_survival.html`, and
`all_requests_daily.html` in a modern browser. Check the 3×3 legend, gray districts
under narrow filters, hover denominators and district/JIA exclusion. The benchmark
reconciles each helper's population to an exact count before exporting. The files
are ignored by Git and contain aggregates, not individual request records.

Automated figure serialization and Streamlit execution have been checked; browser
pixel-level screenshot/accessibility review is not claimed. This procedure supplies
the reproducible visual review method. Statistical details: [CHART_METHODS.md](CHART_METHODS.md).

## Responsive presentation and review status — Phase 2A.1

The map is 900px tall with a full-width map area and a separate legend band.
Its camera is closer, north-up, with zero pitch; original polygon coordinates and
geographical proportions are unchanged. A separator keeps the key apart from the
map, and the square legend cells use a locked axis ratio. Numeric cutpoints no
longer compete with legend cells. Gray support rules and exact hover denominators
are unchanged. Threshold precision is presentation rounding only.

Survival is 660px tall, with short labels and dedicated room for view buttons and
borough legend. Daily panels occupy an 890px figure with a larger inter-panel gap,
a two-row top legend and a slim slider beneath the shared date axis. All figures
use consistent 14px base typography, larger titles and readable hover labels.

Standalone reviews embed the same figures in a centered responsive container
(maximum 1760px). System typography, readable headings, chart cards, threshold or
cohort tables, and separate Explore / Methods sections replace the dense opening
paragraph. Methodological caveats remain visible; raw cohort JSON is expandable.
Viewport metadata, responsive Plotly sizing and a 1100px CSS breakpoint support
laptop widths. Table overflow scrolls within its container. No external fonts,
stylesheets, map keys or tile requests are introduced.

Streamlit uses native container sizing, its existing shared filters, a threshold
table below the map, and an expandable survival cohort summary. It keeps the
confidence and trend checkboxes; standalone reviews use their default enabled
states and native Plotly legend toggles. Both have the same survival range buttons.
No duplicate filters or heavy data loads were introduced; app.py and all pipeline
modules were unchanged during this polish phase.

**Verification:** all six full-data HTML files were regenerated. Exact trace x/y/z,
locations and statistical hover values were compared with saved pre-polish
renderers for all 3,652,435 requests and Brooklyn Q1 (260,034 requests); they match.
Cohort counts, denominators, cutpoints, exclusions and output bounds match the
original benchmark. Source Parquet and pipeline checksums are unchanged.
Programmatic map containment/layout checks pass at 1024, 1440 and 1920px widths.
These checks do not establish absence of browser font/WebGL layout differences.

**Browser visual verification remains pending:** no Chromium, Chrome, Firefox,
Playwright, Selenium or connected browser tool was available. Open the six files
at 1024, 1440 and 1920px and check all labels and the camera, then click every KM
range button, hide/show a borough, hover a denominator, and drag the linked slider.
Repeat in Streamlit with the sidebar open. Screenshots, native Windows/macOS and
accessibility certification are not claimed.

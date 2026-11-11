# Shared data dictionary — contract 1.0.0

Every original and derived column is listed below. The Parquet contract has **52 columns**.
API source types are verified in [SOURCES.md](SOURCES.md); cleaned types are enforced by
`pipeline.contract.SCHEMA`. Rows with bad analytical values remain, except explicitly
counted missing/duplicate request IDs. Raw JSONL retains original downloaded values.

`string`, `Float64`, `Int64`, and `boolean` are pandas nullable extension types.
Float64 maps to Arrow float64, Int64 to int64, boolean to bool. Missing values are
`pd.NA`; missing timestamps are `NaT`. New York dates have
`datetime64[ns, America/New_York]`; cutoff has `datetime64[ns, UTC]`.
No numerical missing value is silently replaced by zero. Arrow permits nulls in
all columns except unique_key; “No” below describes produced-data semantics.

| Name | Cleaned type | Source | Meaning | Units | Nullable | Cleaning / calculation | Analytical use |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `unique_key` | string | 311 API | Source request identifier | none | No | Preserve text and leading zeros; exclude missing IDs and later duplicates with counts | Row identity, joins, auditing; never an ML predictor |
| `status` | string | 311 API | Current source status at extraction | none | Yes | Preserve source text; only comparisons strip/casefold; blank becomes NA | Audit and outcome consistency; never creation-time predictor |
| `complaint_type` | string | 311 API | Problem category (display label Problem) | none | Yes | Source text; blank becomes NA; no category consolidation | Request composition, global filter, candidate creation feature |
| `descriptor` | string | 311 API | Problem detail (display label Problem Detail) | none | Yes | Source text; blank becomes NA | Detail analyses; candidate creation feature subject to availability audit |
| `agency` | string | 311 API | Responding agency abbreviation | none | Yes | Source text; blank becomes NA | Shared agency filter; candidate feature subject to reassignment audit |
| `agency_name` | string | 311 API | Responding agency name | none | Yes | Source text; blank becomes NA | Readable labels and audit |
| `borough` | string | 311 API | Canonical request borough | none | Yes | Trim/title-case; The Bronx becomes Bronx; noncanonical borough becomes NA | Shared borough filter and geographic comparison |
| `community_board` | string | 311 API | Source board label including borough | none | Yes | Retain source string; geography parser trims/uppercases a copy | Validated district join; potential creation feature |
| `incident_zip` | string | 311 API | Source incident ZIP value | none | Yes | Preserve string and leading zeros; no numerical coercion or invented ZIP | Location audit; optional future feature after review |
| `open_data_channel_type` | string | 311 API | Request intake channel | none | Yes | Source text; blank becomes NA | Channel comparisons and candidate creation predictor |
| `location_type` | string | 311 API | Source location classification | none | Yes | Source text; blank becomes NA | Context and candidate creation predictor |
| `resolution_description` | string | 311 API | Current agency resolution narrative | none | Yes | Optional audit field; preserve text; absent/blank becomes NA | Audit only; post-outcome leakage if used for prediction |
| `created_date_raw` | string | 311 audit copy | Original created_date source representation | source text | Yes | Copied before normalization/coercion; blank becomes NA; exact API values also remain in raw JSONL | Audit and reproducible cleaning investigation |
| `closed_date_raw` | string | 311 audit copy | Original closed_date source representation | source text | Yes | Copied before normalization/coercion; blank becomes NA; exact API values also remain in raw JSONL | Audit and reproducible cleaning investigation |
| `resolution_action_updated_date_raw` | string | 311 audit copy | Original resolution_action_updated_date source representation | source text | Yes | Copied before normalization/coercion; blank becomes NA; exact API values also remain in raw JSONL | Audit and reproducible cleaning investigation |
| `borough_raw` | string | 311 audit copy | Original borough source representation | source text | Yes | Copied before normalization/coercion; blank becomes NA; exact API values also remain in raw JSONL | Audit and reproducible cleaning investigation |
| `latitude_raw` | string | 311 audit copy | Original latitude source representation | source text | Yes | Copied before normalization/coercion; blank becomes NA; exact API values also remain in raw JSONL | Audit and reproducible cleaning investigation |
| `longitude_raw` | string | 311 audit copy | Original longitude source representation | source text | Yes | Copied before normalization/coercion; blank becomes NA; exact API values also remain in raw JSONL | Audit and reproducible cleaning investigation |
| `schema_version` | string | Pipeline derived | UrbanPulse contract version | none | No | Constant 1.0.0 | Compatibility checking |
| `created_day` | string | Pipeline derived | Local creation calendar day | YYYY-MM-DD | Yes | Format parsed New York created_date; invalid creation gives NA | Inclusive date filtering and daily aggregation |
| `duration_bucket` | string | Pipeline derived | Exclusive outcome category | category label | No | See exact six-bucket rules below; always a label, including Unknown or invalid | Consistent duration summaries; never predictor |
| `boro_cd` | string | 311 + verified DCP boundaries | Validated district or JIA identifier | three-character string | Yes | Parse explicit board number/borough, use official codes, require membership in loaded boundaries | Future choropleth join key; not guessed for missing boards |
| `geography_status` | string | 311 + verified DCP boundaries | Geographic join classification | category label | No | community_district, joint_interest_area, or unmatched | Separate 59 districts from JIAs and unmatched requests |
| `created_date` | datetime64[ns, America/New_York] | 311 API | Recorded request creation time | New York timestamp | Yes | Parse floating ISO time; localize America/New_York; malformed/fold/gap becomes NaT | Scope, calendar features, elapsed-time origin |
| `closed_date` | datetime64[ns, America/New_York] | 311 API | Recorded administrative closure time | New York timestamp | Yes | Same date parsing; keep valid timestamp even if status disagrees; flags restrict outcomes | Outcome construction only; never creation-time predictor |
| `resolution_action_updated_date` | datetime64[ns, America/New_York] | 311 API | Recorded resolution-action update time | New York timestamp | Yes | Optional audit field; same conservative timestamp parsing | Audit only; not used as closure or predictive feature |
| `extraction_cutoff` | datetime64[ns, UTC] | Pipeline derived | Conservative observation cutoff | UTC timestamp | No | Run extraction-start timestamp, same for all rows, stored at ns precision | Censoring and future timestamp validation; not predictor |
| `latitude` | Float64 | 311 API | Validated incident latitude | decimal degrees | Yes | Numeric coercion; retain pair only within lat 40.45–40.95 and lon -74.30–-73.65 | Future point maps; envelope does not prove geographic membership |
| `longitude` | Float64 | 311 API | Validated incident longitude | decimal degrees | Yes | Same pair validation as latitude; invalid or incomplete pair becomes null | Future point maps; missing coordinates never remove a request |
| `closure_hours` | Float64 | Pipeline derived | Validated elapsed time to recorded closure | hours | Yes | Timezone-aware (closed-created)/3600 seconds only for consistent, nonnegative closed events by cutoff | Completed-case durations; missing for open/unknown |
| `observed_hours` | Float64 | Pipeline derived | Observed event or right-censored duration | hours | Yes | Event: closure_hours; valid open: (cutoff-created)/3600 seconds; otherwise NA | Future survival analysis |
| `created_hour` | Int64 | Pipeline derived | Local creation hour | 0–23 | Yes | New York created_date hour | Hourly demand and candidate predictor |
| `created_weekday` | Int64 | Pipeline derived | Local creation weekday | Monday=0 … Sunday=6 | Yes | New York created_date dayofweek | Weekly seasonality and candidate predictor |
| `created_month` | Int64 | Pipeline derived | Local creation month | 1–12 | Yes | New York created_date month | Seasonality, smoke coverage, candidate predictor |
| `created_quarter` | Int64 | Pipeline derived | Local creation quarter | 1–4 | Yes | New York created_date quarter | Quarterly comparisons and candidate predictor |
| `is_duplicate_key` | boolean | Pipeline derived | Batch-local duplicate source key flag | boolean | No | True for all repeated non-null IDs within a preprocess call; build deduplicates globally first | Diagnostic; output normally False; global exclusions live in report |
| `missing_unique_key` | boolean | Pipeline derived | Missing source key flag | boolean | No | True when source key is blank/null; build excludes such records first | Diagnostic; output False; exclusion count in report |
| `dst_unresolved` | boolean | Pipeline derived | At least one unresolved DST timestamp | boolean | No | Any parseable source date localizes to NaT due to fall ambiguity or spring gap | Audit; inspect per-date flags for outcome relevance |
| `invalid_created_date` | boolean | Pipeline derived | Nonblank creation value could not be localized | boolean | No | Nonblank raw creation and cleaned NaT; includes malformed/offset-bearing/DST values | Audit and outcome uncertainty |
| `invalid_closed_date` | boolean | Pipeline derived | Nonblank closure value could not be localized | boolean | No | Nonblank raw closure and cleaned NaT; includes malformed/offset-bearing/DST values | Audit and exclusion from valid outcomes |
| `invalid_resolution_action_updated_date` | boolean | Pipeline derived | Nonblank resolution-update value could not be localized | boolean | No | Nonblank raw update and cleaned NaT | Audit only; does not itself invalidate closure outcomes |
| `invalid_borough` | boolean | Pipeline derived | Borough missing or outside five canonical names | boolean | No | True when normalized value not in borough allowlist | Cleaning audit |
| `has_valid_coordinates` | boolean | Pipeline derived | Complete coordinate pair within NYC envelope | boolean | No | Numeric latitude/longitude both satisfy documented envelope | Safe coordinate availability indicator |
| `invalid_coordinates` | boolean | Pipeline derived | Present coordinate data failed pair validation | boolean | No | At least one source coordinate present and has_valid_coordinates False | Distinguishes invalid/incomplete from wholly missing pairs |
| `negative_duration` | boolean | Pipeline derived | Closure precedes creation | boolean | No | Both cleaned timestamps exist and closed_date<created_date | Invalid sequence; no derived outcome assigned |
| `status_date_inconsistent` | boolean | Pipeline derived | Status and closure evidence conflict or status missing | boolean | No | Closed without valid close; non-Closed with any raw close; or missing status | Conservative unknown-outcome policy |
| `after_cutoff` | boolean | Pipeline derived | Creation or closure timestamp exceeds cutoff | boolean | No | Valid created_date>cutoff OR valid closed_date>cutoff | Unknown outcomes; extraction is not a historical status snapshot |
| `duration_outlier` | boolean | Pipeline derived | Valid closure exceeds one 365-day year | boolean | No | closure_hours>8760; missing duration gives False; no removal or clipping | Review unusually long administrative durations |
| `board_borough_mismatch` | boolean | 311 + verified DCP boundaries | Board borough differs from request borough | boolean | No | Compare parsed board borough to non-null canonical request borough | Review service/legal borough differences; preserve verified board code |
| `is_closed` | boolean | Pipeline derived | Whether current source status says Closed | boolean | Yes | Strip/casefold equals closed; missing status gives NA | Status audit; may be True even when closure_event is NA |
| `closure_event` | boolean | Pipeline derived | Whether observed_hours ends in a valid closure | nullable boolean | Yes | True for valid closure; False for valid censoring; NA for unknown/invalid | Future survival event indicator; not synonymous with status |
| `is_long_closure` | boolean | Pipeline derived | Unresolved beyond seven elapsed days | nullable boolean | Yes | Event: closure_hours>168; censored age>168: True; immature/unknown: NA | Future classifier target; no negative label for young open requests |

## Exclusive duration buckets

| Label | Exact condition |
| --- | --- |
| Closed within 24 hours | Valid closure: 0 <= hours <= 24 |
| Closed after 24 hours and within 7 days | Valid closure: 24 < hours <= 168 |
| Closed after 7 days and within 30 days | Valid closure: 168 < hours <= 720 |
| Closed after 30 days | Valid closure: hours > 720 |
| Still open / censored | Valid creation by cutoff, non-Closed status, no source closure date |
| Unknown or invalid | Remaining cases: malformed/missing times, conflicts, negative durations, etc. |

Hours are elapsed hours, so DST changes do not shift bucket boundaries. A closure
at 168 hours is not long; an open record at exactly 168 hours has an unknown
classifier label. These semantics are shared by every consumer.

## Geographic artifact fields

GeoJSON feature `id` and `properties.boro_cd` are matching three-character strings;
`properties.district_kind` is community_district or joint_interest_area. Geometry
is the original polygon/multipolygon coordinate arrays in WGS84 longitude/latitude,
without reprojection or simplification. Null/invalid geometry is rejected. Source
area/length fields are not extracted. No geometry columns are duplicated per request.

## Provenance and compatibility

Parquet metadata key `urbanpulse` stores a JSON object: schema_version, mode,
source_url, extraction_cutoff, extraction_finished, sampling, manifest_sha256,
built_at, and geography_sha256 (null if no boundaries supplied). The loader places
it in `df.attrs["urbanpulse"]`. The quality report adds exact counts, exclusions,
raw/cleaned missingness, flags, matching rates, and artifact checksum.
Filtered frames retain provenance, but their summaries always count only their own rows.
See [PIPELINE.md](PIPELINE.md) for schema-change review and rebuild requirements.

## Phase 1.5 query outputs (not new stored columns)

The stored 52-column schema and `1.0.0` version are unchanged. `ParquetQuery`
returns projected source columns with nullable pandas types, or aggregate tables
whose grouping columns are named source columns and whose metric columns are:

| Query metric | Type | Units / meaning | Null/denominator policy |
| --- | --- | --- | --- |
| requests | Int64 | Exact matching record count | Always included; includes all outcome states and NULL groups. Zero for an empty ungrouped result. |
| valid_closures | Int64 | Non-null closure_hours count | Automatically included with duration summaries; their valid denominator. |
| closed | Int64 | closure_event=True count | Uses validated events, not current status alone. |
| censored | Int64 | closure_event=False count | Included in population counts; never treated as zero duration. |
| unknown_outcomes | Int64 | closure_event is null count | Retained and reported. |
| closure_mean_hours | Float64 | Mean validated closure_hours | Ignores nulls; null if no valid closures. Not a mean over all requests. |
| closure_min_hours | Float64 | Minimum validated closure_hours | Same valid denominator/null policy. |
| closure_max_hours | Float64 | Maximum validated closure_hours | Same valid denominator/null policy; outliers are preserved. |
| known_long_labels | Int64 | Non-null is_long_closure count | Includes mature censored positives; excludes unknown/immature labels. |
| long_closures | Int64 | is_long_closure=True count | Includes valid long completions and mature censored observations. |
| long_closure_rate | Float64 | long_closures / known_long_labels, fraction 0–1 | Null for zero denominator; both counts are automatically included. |

NULL grouping keys form their own group. Empty grouped results have no rows;
empty ungrouped aggregation returns one row with zero counts and null statistics.
Every aggregate includes requests even if omitted in the metric selection.
`summary()` retains the existing get_data_summary field meanings and Python dict
return types. `filter_options()` retains the existing get_filter_options contract.
Previews are limited projections, not statistically representative samples.

[DuckDB TIMESTAMPTZ](https://duckdb.org/docs/1.4/sql/data_types/timestamp) uses microsecond precision. The verified NYC timestamps have
millisecond precision and the recorded extraction cutoff has microsecond precision,
so those inputs are preserved, with query output converted back to the documented
pandas timezone/ns dtype. Arbitrary future sub-microsecond timezone-aware input
would be rounded/truncated by DuckDB; use Arrow/the original loader for exact such
values. The stored Parquet timestamps are never rewritten by queries.

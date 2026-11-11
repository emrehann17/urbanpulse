# Data quality — measured real smoke sample

**Full ingestion has not run. Every request count and rate in this document refers
only to the 2,400-record real smoke/demo sample**, not the complete 2025 population.
Tests use separate labelled synthetic fixtures; their counts are not mixed here.

## Extraction and identity

- Source: [NYC 311, erm2-nwe9](https://data.cityofnewyork.us/d/erm2-nwe9).
- Extraction start / observation cutoff: `2026-11-11T11:42:54.693956+00:00`.
- Extraction completed: `2026-11-11T11:43:05.089075+00:00`.
- Build timestamp: `2026-11-11T11:43:41.552885+00:00`.
- Downloaded: **2,400** rows in **24** pages.
- Processed: **2,400** rows, **52** columns.
- Raw unique keys: **2,400**; duplicate keys: **0**; missing keys: **0**.
- Output unique keys: **2,400**; duplicate keys: **0**; missing keys: **0**.
- Excluded rows: **0** (missing ID 0; duplicate ID 0). No other rows were dropped.
- All 15 primary fields and both optional audit fields were available.
- Parquet size: **560,131 bytes**.
- Parquet SHA-256: `79c630d7f9eac22e6ba040d53c327d1e0aa6287b403f52e599624488c9b01f51`.
- Manifest SHA-256: `f5e7540c35374c8eab703d5f06f360af2c6f6f9fac64bd4c127b74911599b655`.

Raw pages and the original run checkpoint remain in ignored `data/raw/smoke/`.
The distributed `data/demo/ingestion-manifest.json` records page hashes and cursors;
its page paths refer to the original raw run, not files inside data/demo.
The Parquet demo contains the original requested fields plus audit representations.

## Selection and coverage

Exactly 200 earliest creation timestamps per month were selected, ordered by
`created_date, unique_key` with lexical ID ties. All 12 months and five boroughs
appear. This deterministic sample concentrates on the first day and early hours
of each month (including New Year), so it is strongly biased by time and complaint
mix. It is neither random nor weighted by monthly population volume. Do not use
it to estimate citywide demand, typical closure performance, or train the final models.
Observed local creation-day range: **2025-01-01 to 2025-12-01**.

| Borough | Sample requests |
| --- | ---: |
| Bronx | 488 |
| Queens | 670 |
| Brooklyn | 710 |
| Manhattan | 469 |
| Staten Island | 63 |

## Missing values

Percentages use all **2,400** records as denominator. Raw missingness counts
absent/null/empty values; cleaned missingness also includes invalidated values.
Whitespace-only inputs are separately counted by `blank_string_counts` in the
JSON report. No whitespace-only source values were present in this extraction.

| Field | Raw missing | Raw missing % | Cleaned missing | Cleaned missing % |
| --- | ---: | ---: | ---: | ---: |
| `unique_key` | 0 | 0.0000 | 0 | 0.0000 |
| `created_date` | 0 | 0.0000 | 0 | 0.0000 |
| `closed_date` | 9 | 0.3750 | 11 | 0.4583 |
| `status` | 0 | 0.0000 | 0 | 0.0000 |
| `complaint_type` | 0 | 0.0000 | 0 | 0.0000 |
| `descriptor` | 2 | 0.0833 | 2 | 0.0833 |
| `agency` | 0 | 0.0000 | 0 | 0.0000 |
| `agency_name` | 0 | 0.0000 | 0 | 0.0000 |
| `borough` | 0 | 0.0000 | 0 | 0.0000 |
| `community_board` | 0 | 0.0000 | 0 | 0.0000 |
| `incident_zip` | 9 | 0.3750 | 9 | 0.3750 |
| `latitude` | 16 | 0.6667 | 16 | 0.6667 |
| `longitude` | 16 | 0.6667 | 16 | 0.6667 |
| `open_data_channel_type` | 0 | 0.0000 | 0 | 0.0000 |
| `location_type` | 136 | 5.6667 | 136 | 5.6667 |
| `resolution_description` | 10 | 0.4167 | 10 | 0.4167 |
| `resolution_action_updated_date` | 3 | 0.1250 | 5 | 0.2083 |

| Derived field | Missing | Missing % |
| --- | ---: | ---: |
| `closure_hours` | 12 | 0.5000 |
| `observed_hours` | 5 | 0.2083 |
| `closure_event` | 5 | 0.2083 |
| `is_long_closure` | 5 | 0.2083 |
| `boro_cd` | 16 | 0.6667 |

Full counts/percentages for all 52 columns are in
[`requests.quality.json`](../data/demo/requests.quality.json).

## Cleaning and validation

| Rule / indicator | Affected rows |
| --- | ---: |
| `is_duplicate_key` | 0 |
| `missing_unique_key` | 0 |
| `dst_unresolved` | 2 |
| `invalid_created_date` | 0 |
| `invalid_closed_date` | 2 |
| `invalid_resolution_action_updated_date` | 2 |
| `invalid_borough` | 0 |
| `has_valid_coordinates` | 2,384 |
| `invalid_coordinates` | 0 |
| `negative_duration` | 0 |
| `status_date_inconsistent` | 5 |
| `after_cutoff` | 0 |
| `duration_outlier` | 1 |
| `board_borough_mismatch` | 2 |
| `borough_values_changed` | 2,400 |
| `created_date_parsed` | 2,400 |
| `closed_date_parsed` | 2,389 |
| `resolution_action_updated_date_parsed` | 2,395 |

Flags can overlap and must not be summed as distinct affected records. The two
invalid closure timestamps are DST-ambiguous `2025-11-02T01:24:50.000` and
`2025-11-02T01:26:43.000`; the same two records also have ambiguous resolution
update timestamps. They are retained with raw values, cleaned NaT, and unknown
outcomes. There were no invalid creation timestamps or negative durations.

The five status/date inconsistencies comprise two Closed records without closure
dates, two Closed records with the ambiguous DST closure times, and one Open
record with a closure timestamp. No artificial closure or censoring outcome is
assigned to those five. All 2,400 source borough names were converted from their
original capitalization into the shared title-case vocabulary.

## Duration, censoring, and target validation

- Valid completed observations: **2,388**.
- Valid right-censored observations: **7**.
- Unknown outcomes: **5**.
- Valid closure range: **0.0000–10232.8647 hours**.
- Long-closure labels: **171 True**, **2,224 False**, **5 unknown**.
- Open/censored requests have null closure_hours; none is assigned zero.
- One valid duration exceeds 8,760 hours and is retained, not clipped or removed.

| Exclusive duration category | Records |
| --- | ---: |
| Closed within 24 hours | 1,994 |
| Closed after 24 hours and within 7 days | 230 |
| Closed after 30 days | 75 |
| Closed after 7 days and within 30 days | 89 |
| Still open / censored | 7 |
| Unknown or invalid | 5 |

The >1-year closure belongs to request `65420194`, created July 1, 2025 and
closed August 31, 2026. The cutoff is later than that closure, and the record
passes sequence/status validation. It is an unusual administrative observation,
not proof of uninterrupted real-world service delay. Requests created in 2025
can legitimately close after the analysis year.

## Geographic matching

- Boundary source: [Community Districts, 5crt-au7u](https://data.cityofnewyork.us/d/5crt-au7u).
- Verified geometry: **71** features = **59** districts + **12** joint interest areas.
- Successful request matches: **2,384 / 2,400 = 99.3333%**.
- Ordinary district matches: **2,378**; JIA matches: **6**; unmatched: **16**.
- Valid coordinate pairs: **2,384**; both coordinates missing: **16**.
- Present-but-invalid coordinate pairs: **0** under the conservative NYC envelope.
- Board/request borough disagreements: **2** (Manhattan request borough, Bronx board 08).
  The explicit verified board mapping is retained with a flag; no spatial claim is made.

Unmatched requests remain available to nongeographic analyses. Counts of matched
IDs do not prove point-in-polygon agreement. Structural polygon/ring validation
passed; geometry topology, individual address placement, and historical 2025
boundary agreement have not been tested. The boundary artifact is release 26c,
with retrieval metadata in `data/geographic/community_districts.metadata.json`.

## Verification and limitations

`python -m pipeline quality --input data/demo/requests.parquet` passed schema,
global uniqueness, and outcome invariant checks. The completed ingestion command
was rerun successfully without downloading again. The app loaded the real demo,
showed 2,400 records and 2,388 valid closures, and filtered to **710 Brooklyn**
records consistently in both metrics and preview. Local HTTP health and root
checks returned 200. Offline unit/integration results are in PROJECT_STATUS.md.

The first ID-only query strategy repeatedly timed out; its incomplete 800-row
run is preserved locally in `data/raw/smoke-key-order-abandoned/` and contributes
**no rows** to these final sample metrics. Creation-time ordering completed the
final 2,400-row extraction. Initial sandbox DNS and local socket restrictions
were resolved by approved network/socket access; no API outage is being hidden.

Live data can change during and after extraction. The snapshot is not transactional;
a full start-count comparison has not been measured because full ingestion was
not run. Historical status, reopenings, unreported needs, reporting propensity,
and actual satisfaction are not observable from these fields. The latest boundary
release need not match 2025 boundaries. Unknown outcomes and sampling bias must
remain visible in subsequent analyses.

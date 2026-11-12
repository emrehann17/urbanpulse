# Architectural and data decisions

Recorded for Phase 1, November 11, 2026. These decisions describe implemented
behavior; planned model work is identified separately in ML_DESIGN.md.

| Decision | Rationale and consequence |
| --- | --- |
| Keep the initialized repository | Existing README and ignore rules were inspected; project context preserved and expanded. No nested Git repository or remote writes. |
| Python 3.12, pandas + Arrow + requests | Clear tabular transformations, portable Parquet, reliable HTTP; no server, ORM, GDAL, or orchestration framework needed. |
| Pinned direct requirements plus resolved constraints | Repeatable installations; Linux resolution is recorded, Windows/macOS remain subject to actual CI/runtime verification. |
| Public SODA 2.x GET endpoint | Verified token-free access fulfills the requirement; current SODA3 query docs require auth/token. Track future endpoint retirement rather than silently adding a secret requirement. |
| Verify API names and types | Problem/Problem Detail are display labels; complaint_type/descriptor remain API fields. Fail on primary field drift, document absent auxiliary fields. |
| Monthly creation/key keyset pagination | Creation-time order with lexical text-key ties avoids large offsets and bounded pages control memory. Live ID-only ordering timed out; creation/key ordering completed the final sample. Does not guarantee a live transactional snapshot. |
| Smoke uses 200 earliest creations per month | Exercises all months and provides >2,000 real records for demo; deterministic seasonal coverage, not random or proportional sampling. No citywide estimates or model training from demo. |
| Immutable JSONL pages + atomic manifest | Preserve source values, retry safely, audit with SHA-256, and resume without re-downloading committed pages. Single writer per run. |
| Temporary SQLite ID index | Exact cross-page uniqueness checks without memory growth proportional to all IDs. Explicitly close handles for Windows cleanup. |
| One compressed Parquet file with fixed Arrow schema | Stable null-only batch behavior and one shared artifact; batch writes are memory-bounded. App convenience loading still needs enough RAM. |
| Preserve bad records, nullable outcomes | Only missing/duplicate IDs are excluded and counted. Keep valid long closures; flag >8,760-hour values. Analysts see quality flags rather than silent row removal. |
| New York wall-time interpretation | Verified floating source timestamps lack offsets; publisher-local timezone is an explicit assumption. DST ambiguity/gaps become NaT; no guessed fold or UTC assumption. |
| Status/date consistency required | Administrative closure dates conflicting with current status cannot safely define completed events. is_closed retains status interpretation; closure_event captures trustworthy outcome evidence. |
| Extraction-start cutoff | One conservative observation window across all pages. Late updates/closures can become unknown rather than be backdated. Historical statuses are not reconstructed. |
| Strict >168-hour classifier target | Completed <=168 is negative, completed >168 or mature open >168 positive; immature open remains NA. Matches “beyond seven days”. |
| Board-derived IDs require verified polygons | Official DCP borough encoding, explicit district/JIA sets, validated membership. Preserve service/legal borough differences with flags, never fabricate a join. |
| Preserve current boundary vintage | Downloaded 26c (2026) boundaries support future integration; historical consistency with 2025 remains unverified and documented. |
| No spatial stack in Phase 1 | Structural polygon and coordinate-envelope validation suffice for contract integration; topology and point-in-polygon checks are clearly not claimed. |
| Pure public data API | load_data, apply_filters, get_filter_options, get_data_summary work in scripts/notebooks; charts receive a shared filtered frame. |
| Explicit sample default | Demo runs offline; choosing full cannot silently fall back to smoke. File metadata and UI display the scope. |
| Strict contract version acceptance | Every change is reviewed, versioned, documented, and tested; consumers rebuild or explicitly add compatibility. |
| Mock network for tests | Fast deterministic CI; live smoke and boundary checks are separate evidence. No CI dependency on NYC availability. |
| Phase boundaries | No final visualization or fitted ML model; architecture, targets, examples, and design documents support the next phase. |

The initial test run revealed a pandas scalar timestamp precision mismatch;
extraction_cutoff now explicitly uses nanosecond UTC dtype, matching Parquet.
Synthetic boundary fixtures now use standard-library datetime arithmetic to
provide an independent expected result and avoid pandas/NumPy fixture warnings.
Dependency upgrades should rerun the full suite and regenerate constraints deliberately.

## Phase 1.5 additions

- CI now uses a fresh venv per Ubuntu/Windows job and explicit interpreter paths.
  The reported pipx/packaging conflict belongs to runner-global tooling; project
  pins are retained and pip check remains active.
- DuckDB 1.4.5 LTS is the only new runtime package. PyArrow still owns the stored
  schema and offline build; DuckDB adds exact SQL grouping and projection without
  implementing an aggregation engine or a database service.
- FilterSpec centralizes normalization for both backends. Existing function
  signatures and valid filter semantics stay compatible; values are parameterized
  and output identifiers are allowlisted.
- Full-mode Streamlit now queries bounded outputs. This supersedes Phase 1's
  full-frame app-memory limitation; the original loader still materializes its
  selected artifact for small-data compatibility.
- Exact aggregates retain NULL groups and include denominators. Output cardinality
  caps raise errors rather than silently sample/truncate statistical populations.
- Preview ordering is created_day then unique_key; previews are not representative
  samples. No sampling API or final statistical estimator is introduced.
- One embedded connection per query avoids shared mutable connections in Streamlit.
  Default two threads/512 MB and bounded caches are conservative starting settings,
  not measured full-scale deployment limits. Private temp directories permit spill.
- Full ingestion/build layout is retained; only genuine checkpoint-validation gaps
  were repaired. Row-group coalescing/partitioning is deferred until measured on a
  real full snapshot.
- Benchmark peak RSS on Linux uses VmHWM rather than getrusage, avoiding a parent's
  synthetic-generation high-water mark being inherited across process execution.
  Demo and synthetic results are reported separately, with no population claims.

## Phase 2A — exact preparation with bounded display

Use reviewed Parquet metrics and a context-managed ordered frequency stream for
Member 1. Exact KM needs more than the ordinary aggregate group limit, so stream
4,096 tuples at a time and compute every event/censor update. Bound plotted points
by explicit display thinning; disclose omitted jumps while retaining exact values
at plotted times. This avoids statistical sampling and an additional dependency.
The daily median is exact in DuckDB and reports completed-observation denominators.

Map tertiles describe relative current-cohort count/rate combinations, with 30 known
labels as a display support threshold and all nine legend categories retained.
Show 59 verified districts on a local blank MapLibre background; exclude/count JIAs
and unmatchable requests. Do not force equal-valued districts into different bins.
Population charts require full mode in the app because the demo is temporally biased.
Keep diagnostics, stored schema and outcome/filter definitions unchanged.

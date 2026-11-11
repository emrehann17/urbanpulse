# Real NYC 311 integration sample

This is **not the full 2025 dataset** and is not a probability sample.

- 2,400 real requests, 52 cleaned columns, schema 1.0.0.
- Earliest 200 creation timestamps per month of 2025, lexical unique_key tie-break.
- Five canonical NYC boroughs; observed requests concentrate on early hours of each month's first day.
- Observation cutoff: `2026-11-11T11:42:54.693956+00:00`.
- Source: https://data.cityofnewyork.us/d/erm2-nwe9
- Parquet SHA-256: `79c630d7f9eac22e6ba040d53c327d1e0aa6287b403f52e599624488c9b01f51`.

`requests.parquet` is ready for `load_data(dataset="demo")` and Streamlit.
`requests.quality.json` contains measured missingness, exclusions, flags, and matching rates.
`ingestion-manifest.json` records original raw-page hashes/cursors; those pages remain
locally in ignored data/raw/smoke and are not distributed in this folder.
`source-schema.json` is the actual ingestion schema snapshot.

See [pipeline commands](../../docs/PIPELINE.md), [quality analysis](../../docs/DATA_QUALITY.md),
and [source verification](../../docs/SOURCES.md). Reruns use the same selection rule,
but live edits mean fresh values/hashes may differ. This sample is for interface
integration and demonstration, not citywide estimates or model training.

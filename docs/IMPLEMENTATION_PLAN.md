# Phase 1 implementation plan

Repository inspection found only README.md and .gitignore, with no uncommitted changes.
Python 3.12.3 is available as python3. Existing repository identity is preserved.

1. Verify live schema, public endpoint behavior, timestamps, and DCP identifiers.
2. Implement bounded smoke and full keyset ingestion, atomic page checkpoints, audit metadata.
3. Process one page at a time into one Parquet file with a fixed Arrow schema; retain raw pages.
4. Centralize quality flags, DST-safe dates, outcomes, validated geographic joins, and filters.
5. Add an explicit sample-aware Streamlit integration and offline synthetic-fixture tests.
6. Run a real smoke extraction, publish a compact demo and measured quality report.
7. Finalize developer contracts, source notes, ML design, and Windows/Linux CI.

No final charts, trained models, commits, or remote repository changes are in scope.

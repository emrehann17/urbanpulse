# Shared visualization integration

Member 1 implements `bivariate.py`, `survival.py`, and `timeseries.py`, with the
Streamlit section in `member1.py`. Six other assigned charts remain pending.

Pure renderers return Plotly Figures from documented **already-filtered aggregate
tables**. `pipeline.chart_data` prepares those small tables via ParquetQuery and
one app-owned FilterSpec. Neither renderers nor individual team members ingest,
clean, redefine outcomes or duplicate global filters. The stored 52-column contract
remains unchanged. The small-cohort request-DataFrame chart interface is still valid,
but aggregate inputs and raw request inputs must not be confused.

See [TEAM_GUIDE](../docs/TEAM_GUIDE.md), [specifications](../docs/VISUALIZATION_SPEC.md),
[methods/input schemas](../docs/CHART_METHODS.md) and
[performance](../docs/PERFORMANCE.md). Use the benchmark module to export reproducible
HTML reviews; do not infer population estimates from preview rows or the biased demo.

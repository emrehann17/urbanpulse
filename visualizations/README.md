# Visualization integration

Reserved for the three students' nine final visualizations. Phase 1 implements no
final charts. See [the team guide](../docs/TEAM_GUIDE.md) for the shared interface:
`create_visualization(filtered_df: pandas.DataFrame) -> plotly.graph_objects.Figure`.
Modules receive already-filtered data, never ingest or clean it, and do not mutate it.


For full-scale inputs, the app shell should query exact aggregate tables through
`ParquetQuery` with one shared `FilterSpec`. A pure figure function may receive
that smaller DataFrame; its docstring must state the aggregate schema and valid
denominators. Do not pass a limited preview as a full statistical population.
The team guide documents input patterns for all nine planned charts.

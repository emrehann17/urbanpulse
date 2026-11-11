# Visualization integration

Reserved for the three students' nine final visualizations. Phase 1 implements no
final charts. See [the team guide](../docs/TEAM_GUIDE.md) for the shared interface:
`create_visualization(filtered_df: pandas.DataFrame) -> plotly.graph_objects.Figure`.
Modules receive already-filtered data, never ingest or clean it, and do not mutate it.

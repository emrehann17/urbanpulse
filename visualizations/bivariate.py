"""Member 1: bivariate community district map with a genuine 3×3 key."""

import numpy as np
import pandas as pd
import plotly.graph_objects as go

from pipeline.geography import DISTRICT_CODES, validate_geojson

# Rows: increasing long-closure rate; columns: increasing request count.
# Cyan/magenta to purple avoids a red/green opposition. Text duplicates color.
PALETTE = [
    "#e8e8e8",
    "#ace4e4",
    "#5ac8c8",
    "#dfb0d6",
    "#a5add3",
    "#5698b9",
    "#be64ac",
    "#8c62aa",
    "#3b4994",
]
NO_DATA = "#777777"
TIERS = ["Low", "Medium", "High"]


def classification_thresholds(chart_df: pd.DataFrame) -> pd.DataFrame:
    """Readable display-only bin boundaries; never recalculate classification."""
    rows = []
    for metric, label in (
        ("requests", "Request volume"),
        ("long_closure_rate", "Beyond-seven-day closure rate"),
    ):
        cuts = chart_df.attrs["cuts"][metric]
        if cuts[0] is None:
            bounds = ["Unavailable"] * 3
        else:
            low, high = [f"{v:,.2f}" if metric == "requests" else f"{v:.2%}" for v in cuts]
            bounds = [f"≤ {low}", f"> {low} to ≤ {high}", f"> {high}"]
        rows.append(dict(zip(["Dimension", *TIERS], [label, *bounds], strict=True)))
    return pd.DataFrame(rows)


def create_visualization(chart_df: pd.DataFrame, *, geojson: dict) -> go.Figure:
    """Render district_data's 59-row schema without mutating it or the GeoJSON.

    Requires boro_cd, requests, known_long_labels, long_closures,
    long_closure_rate, support, bivariate_class and attrs cuts/min_known/excluded.
    Uses local polygons and a blank MapLibre background, without tiles/API keys.
    """
    if not DISTRICT_CODES <= validate_geojson(geojson):
        raise ValueError("The map requires all 59 validated community districts")
    if set(chart_df.boro_cd) != DISTRICT_CODES or len(chart_df) != 59:
        raise ValueError("Map input must contain exactly the 59 ordinary districts")
    boundaries = {
        "type": "FeatureCollection",
        "features": [
            f for f in geojson["features"] if str(f["properties"]["boro_cd"]) in DISTRICT_CODES
        ],
    }
    colors = [NO_DATA, *PALETTE]
    scale = [entry for i, c in enumerate(colors) for entry in ([i / 10, c], [(i + 1) / 10, c])]
    rates = ["Unknown" if pd.isna(v) else f"{v:.1%}" for v in chart_df.long_closure_rate]
    classes = [
        "Insufficient / no data" if c < 0 else f"Volume {TIERS[c % 3]} · Rate {TIERS[c // 3]}"
        for c in chart_df.bivariate_class
    ]
    custom = list(
        zip(
            chart_df.requests,
            rates,
            chart_df.known_long_labels,
            chart_df.long_closures,
            chart_df.support,
            classes,
            strict=True,
        )
    )
    fig = go.Figure(
        go.Choroplethmap(
            geojson=boundaries,
            featureidkey="properties.boro_cd",
            locations=chart_df.boro_cd,
            z=chart_df.bivariate_class + 1,
            zmin=-0.5,
            zmax=9.5,
            colorscale=scale,
            showscale=False,
            marker_line_color="white",
            marker_line_width=1,
            customdata=custom,
            hovertemplate=(
                "<b>Community district %{location}</b><br>Requests: %{customdata[0]:,}"
                "<br>Beyond 7 days: %{customdata[1]}<br>Known labels: %{customdata[2]:,}"
                "<br>Positive labels: %{customdata[3]:,}<br>%{customdata[4]}"
                "<br>%{customdata[5]}<extra></extra>"
            ),
        )
    )
    legend_scale = [
        entry for i, c in enumerate(PALETTE) for entry in ([i / 9, c], [(i + 1) / 9, c])
    ]
    fig.add_trace(
        go.Heatmap(
            z=np.arange(9).reshape(3, 3),
            x=[0, 1, 2],
            y=[0, 1, 2],
            colorscale=legend_scale,
            zmin=-0.5,
            zmax=8.5,
            showscale=False,
            xgap=3,
            ygap=3,
            text=[
                [f"Volume: {volume}<br>Beyond-seven-day rate: {rate}" for volume in TIERS]
                for rate in TIERS
            ],
            hovertemplate="%{text}<extra></extra>",
        )
    )
    fig.update_layout(
        title=dict(text="Request volume × beyond-seven-day closure rate", font=dict(size=20)),
        template="plotly_white",
        autosize=True,
        font=dict(family="Arial, sans-serif", size=14, color="#243247"),
        hoverlabel=dict(font_size=14, bgcolor="white"),
        height=900,
        margin=dict(l=30, r=30, t=65, b=65),
        map=dict(
            style="white-bg",
            center=dict(lat=40.705, lon=-73.977),
            zoom=9.35,
            bearing=0,
            pitch=0,
            domain=dict(x=[0, 1], y=[0.30, 1]),
        ),
        xaxis=dict(
            domain=[0.30, 0.70],
            range=[-0.5, 2.5],
            tickvals=[0, 1, 2],
            ticktext=TIERS,
            title=dict(text="Request volume", standoff=10),
            fixedrange=True,
            constrain="domain",
            showgrid=False,
            zeroline=False,
        ),
        yaxis=dict(
            domain=[0.025, 0.21],
            range=[-0.5, 2.5],
            tickvals=[0, 1, 2],
            ticktext=TIERS,
            title=dict(text="Beyond-seven-day<br>closure rate", standoff=10),
            fixedrange=True,
            scaleanchor="x",
            scaleratio=1,
            constrain="domain",
            showgrid=False,
            zeroline=False,
        ),
        shapes=[
            dict(
                type="line",
                xref="paper",
                yref="paper",
                x0=0,
                x1=1,
                y0=0.285,
                y1=0.285,
                line=dict(color="#d7dee8", width=1),
            )
        ],
        annotations=[
            dict(
                x=0.5,
                y=0.265,
                xref="paper",
                yref="paper",
                showarrow=False,
                text="<b>Bivariate key</b>",
                yanchor="middle",
                font=dict(size=14),
            )
        ],
    )
    return fig

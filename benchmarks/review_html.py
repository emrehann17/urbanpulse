"""Responsive standalone review pages; presentation only, no data preparation."""

import json
from html import escape

from visualizations import bivariate, survival

STYLE = """
:root { color-scheme: light; font-family: Inter, 'Segoe UI', Arial, sans-serif;
        color: #243247; background: #f3f6fa; }
* { box-sizing: border-box; }
body { margin: 0; font-size: 16px; line-height: 1.6; }
main { width: min(100% - 48px, 1760px); margin: 32px auto 64px; }
h1 { font-size: clamp(24px, 2.4vw, 36px); line-height: 1.2; margin: 8px 0 16px; }
h2 { font-size: 20px; margin: 0 0 12px; }
p { margin: 8px 0 16px; }
.eyebrow { color: #4d627e; letter-spacing: .1em; font-size: 13px; font-weight: 700; }
.scope { display: inline-block; padding: 6px 12px; background: #e6edf5;
         border-radius: 6px; font-weight: 600; }
.card { margin-top: 24px; padding: 24px; background: white; border: 1px solid #d7dee8;
        border-radius: 12px; min-width: 0; }
.chart-card { padding: 12px; }
.plotly-graph-div { width: 100%; }
.notes { display: grid; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
         gap: 16px 32px; }
ul { padding-left: 22px; margin: 0; }
li { margin: 8px 0; }
.table-scroll { overflow-x: auto; }
table { width: 100%; border-collapse: collapse; font-size: 15px; }
th, td { text-align: left; padding: 12px; border-bottom: 1px solid #d7dee8; }
th { background: #f3f6fa; }
summary { cursor: pointer; font-weight: 600; }
pre { white-space: pre-wrap; overflow-wrap: anywhere; font-size: 13px; }
@media (max-width: 1100px) {
  main { width: calc(100% - 24px); margin-top: 20px; }
  .card { padding: 18px; }
  .chart-card { padding: 4px; }
}
"""

NOTES = {
    "district": (
        [
            "Pan and zoom the map; hover a district for exact counts and denominators.",
            "The separate 3×3 key combines request volume and beyond-seven-day closure rate.",
            "Gray districts have no matching requests or insufficient known labels. "
            "Low / Medium / High are current-cohort tertiles; equal values stay together.",
        ],
        [
            "The rate uses known seven-day labels, including mature open positive labels. "
            "Unknown labels are excluded from its denominator.",
            "Raw volume is not population-adjusted. Reporting propensity and complaint mix differ; "
            "the map is not causal evidence of unequal service quality.",
            "Joint interest areas and unmatched requests are excluded from district comparisons. "
            "The current boundaries are not historically validated for 2025.",
        ],
    ),
    "survival": (
        [
            "The initial view shows the first 30 days. Use First 7 days, First 30 days, "
            "First 90 days or Full observed period to change only the displayed time range.",
            "All valid observations still enter estimation. "
            "No button filters or refits the cohort.",
            "Click a borough in the legend to hide/show its curve and confidence band. "
            "Hover for the exact retained-time probability, risk set and interval.",
        ],
        [
            "Administrative closure is a recorded status, not verified problem resolution.",
            "Valid right-censored observations are included; unknown outcomes are excluded. "
            "The table below reports cohort sizes and exclusions by borough.",
            "Every time group contributes to the exact estimator. Intermediate steps and censor "
            "marks are omitted for display; zoom cannot restore them.",
            "95% pointwise Greenwood intervals assume independent requests and non-informative "
            "censoring. Repeated reports and complaint mix can violate those assumptions. "
            "Sparse tails and boundary intervals require caution; no causal comparison is implied.",
        ],
    ),
    "daily": (
        [
            "Zoom either panel or drag the date slider to change both date axes.",
            "Thin colored lines show daily values; thicker dashed lines show trailing trends.",
            "Hover over closure time for valid-closure and total-request denominators.",
        ],
        [
            "Daily counts are exact. The closure statistic is the median of valid completed "
            "requests grouped by creation day, not the day of closure.",
            "The seven-day closure trend is a median of daily medians, NOT a pooled seven-day "
            "request median. The request trend is the mean daily count, including zeros.",
            "Partial initial rolling windows are allowed. Days without closures have null medians; "
            "their trend can persist while earlier valid days remain in the window.",
            "Open and unknown outcomes are absent from closure medians, which can understate "
            "waits. Invalid creation dates are not assigned a day. The biased demo cannot "
            "estimate population trends.",
        ],
    ),
}


def render_review(
    fig, *, chart: str, cohort: str, dataset: str, summary: dict, districts, outcomes
) -> str:
    """Build an escaped, self-contained HTML review with the same Plotly figure as the app."""
    titles = {
        "district": "Community districts: volume and closure delay",
        "survival": "Time to administrative closure",
        "daily": "Daily demand and closure time",
    }
    label = "Full extraction" if dataset == "full" else "BIASED SAMPLE — NOT POPULATION TRENDS"
    sections = []
    for title, notes in zip(
        ("Explore the chart", "Methods and limitations"), NOTES[chart], strict=True
    ):
        sections.append(
            f"<section><h2>{title}</h2><ul>"
            + "".join(f"<li>{escape(note)}</li>" for note in notes)
            + "</ul></section>"
        )
    if chart == "district":
        table = bivariate.classification_thresholds(districts).to_html(index=False, border=0)
        extra = (
            "<section class='card'><h2>Classification thresholds</h2>"
            f"<div class='table-scroll'>{table}</div>"
            "<p>Thresholds are rounded for display; exact classification is unchanged. "
            f"Gray: fewer than {districts.attrs['min_known']} known labels. "
            f"Excluded JIA requests: {districts.attrs['excluded']['joint_interest_area']:,}; "
            f"unmatched requests: {districts.attrs['excluded']['unmatched']:,}.</p></section>"
        )
    elif chart == "survival":
        table = survival.cohort_summary(outcomes).to_html(index=False, border=0)
        counts = summary["survival"]
        extra = (
            "<section class='card'><details open>"
            "<summary>Borough cohort sizes and censoring</summary>"
            f"<div class='table-scroll'>{table}</div></details>"
            f"<p>Displayed time groups: {counts['plotted_time_groups']:,} of "
            f"{counts['input_time_groups']:,}; all groups contribute to estimation.</p></section>"
        )
    else:
        extra = (
            "<section class='card'><h2>Calendar coverage</h2>"
            "<p>Requests without a valid creation day: "
            f"{summary['daily']['unknown_created_day']:,}. "
            "Zero-request days are retained; missing closure medians are not replaced by zero."
            "</p></section>"
        )
    return (
        "<!doctype html><html lang='en'><head><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width, initial-scale=1'>"
        f"<title>UrbanPulse · {escape(titles[chart])}</title><style>{STYLE}</style></head>"
        "<body><main><header><div class='eyebrow'>URBANPULSE · MEMBER 1</div>"
        f"<h1>{escape(titles[chart])}</h1><p>{escape(cohort.replace('_', ' ').title())}</p>"
        f"<span class='scope'>{escape(label)} · "
        f"{summary['rows']:,} matching requests</span></header>"
        "<section class='card chart-card' aria-label='Interactive chart'>"
        + fig.to_html(
            full_html=False,
            include_plotlyjs=True,
            default_width="100%",
            config={"responsive": True, "displaylogo": False},
        )
        + "</section>"
        + extra
        + "<div class='card notes'>"
        + "".join(sections)
        + "</div>"
        + "<details class='card'><summary>"
        "Exact cohort, exclusions and query measurements</summary><pre>"
        + escape(json.dumps(summary, indent=2))
        + "</pre></details></main></body></html>"
    )

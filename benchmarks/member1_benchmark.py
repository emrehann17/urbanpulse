"""Reproduce real chart queries and export reviewable HTML; never ingest data.

python -m benchmarks.member1_benchmark --dataset full --output benchmarks/local/member1.json
"""

import argparse
import json
import platform
from datetime import UTC, datetime
from pathlib import Path
from statistics import median
from time import perf_counter

import duckdb
import pyarrow.parquet as pq

from benchmarks.query_benchmark import peak_rss_mib
from benchmarks.review_html import render_review
from config.settings import DATA_DIR
from pipeline.chart_data import daily_data, district_data, survival_data
from pipeline.filters import FilterSpec
from pipeline.geography import load_geography
from pipeline.query import ParquetQuery
from visualizations import bivariate, survival, timeseries


def benchmark(dataset: str, repeats: int, html_dir: Path) -> dict:
    """Time uncached Python calls (OS cache uncontrolled), then render all figures."""
    query = ParquetQuery(dataset=dataset)
    geojson = load_geography(DATA_DIR / "geographic" / "community_districts.geojson")
    output = {
        "measured_at": datetime.now(UTC).isoformat(),
        "platform": platform.platform(),
        "python": platform.python_version(),
        "duckdb": duckdb.__version__,
        "dataset": dataset,
        "provenance": query.provenance,
        "rows": query.count(),
        "bytes": query.path.stat().st_size,
        "row_groups": pq.ParquetFile(query.path).metadata.num_row_groups,
        "repeats": repeats,
        "threads": query.threads,
        "memory_limit_mb": query.memory_limit_mb,
        "cohorts": {},
    }
    html_dir.mkdir(parents=True, exist_ok=True)
    for name, filters in {
        "all_requests": FilterSpec(),
        "brooklyn_q1": FilterSpec(
            borough="Brooklyn", start_date="2025-01-01", end_date="2025-03-31"
        ),
    }.items():
        timings, results = {}, {}
        for chart, operation in {
            "district": lambda f=filters: district_data(query, f, geojson),
            "daily": lambda f=filters: daily_data(query, f),
            "survival": lambda f=filters: survival_data(query, f),
        }.items():
            elapsed = []
            for _ in range(repeats):
                start = perf_counter()
                results[chart] = operation()
                elapsed.append((perf_counter() - start) * 1000)
            timings[chart] = {"runs_ms": elapsed, "median_ms": median(elapsed)}
        districts, days = results["district"], results["daily"]
        curves, outcomes = results["survival"]
        count = query.count(filters=filters)
        assert districts.requests.sum() + sum(districts.attrs["excluded"].values()) == count
        assert days.requests.sum() + days.attrs["unknown_created_day"] == count
        assert outcomes.requests.sum() == count
        summary = {
            "filters": filters.__dict__,
            "rows": count,
            "timings": timings,
            "district": districts.attrs,
            "daily": days.attrs,
            "survival": curves.attrs,
            "output_rows": {
                "district": len(districts),
                "daily": len(days),
                "survival": len(curves),
            },
            "outcomes": outcomes.to_dict("records"),
        }
        output["cohorts"][name] = summary
        figures = {
            "district": bivariate.create_visualization(districts, geojson=geojson),
            "daily": timeseries.create_visualization(days),
            "survival": survival.create_visualization(curves, outcomes=outcomes),
        }
        for chart, fig in figures.items():
            html = render_review(
                fig,
                chart=chart,
                cohort=name,
                dataset=dataset,
                summary=summary,
                districts=districts,
                outcomes=outcomes,
            )
            (html_dir / f"{name}_{chart}.html").write_text(html, encoding="utf-8")
    output["process_peak_rss_mib"] = peak_rss_mib()
    return output


def main() -> None:
    """Portable benchmark/visual review entry point, using existing artifacts only."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", choices=("demo", "full", "smoke"), default="full")
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--output", type=Path, default=Path("benchmarks/local/member1.json"))
    parser.add_argument("--html-dir", type=Path, default=Path("benchmarks/local/member1"))
    args = parser.parse_args()
    if not 1 <= args.repeats <= 20:
        parser.error("repeats must be in 1..20")
    result = benchmark(args.dataset, args.repeats, args.html_dir)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()

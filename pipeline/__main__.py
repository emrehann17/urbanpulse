"""Portable CLI: python -m pipeline --help."""

import argparse
import json
import logging
from pathlib import Path

import requests

from config.settings import DATA_DIR
from pipeline.build import build_processed
from pipeline.geography import download_geography
from pipeline.ingest import ingest
from pipeline.quality import check_parquet


def main(argv: list[str] | None = None) -> int:
    """Execute one explicit pipeline operation; return a portable process exit code."""
    parser = argparse.ArgumentParser(description="UrbanPulse shared data pipeline (Phase 1)")
    sub = parser.add_subparsers(dest="command", required=True)
    download = sub.add_parser("ingest", help="Download/resume bounded smoke or full 2025 data")
    download.add_argument("--mode", choices=("smoke", "full"), default="smoke")
    download.add_argument("--run-dir", type=Path, help="New or matching checkpoint directory")
    download.add_argument("--per-month", type=int, default=200, help="Smoke records per month")
    download.add_argument("--page-size", type=int, default=5000)
    geo = sub.add_parser("geography", help="Download validated Community District GeoJSON")
    geo.add_argument(
        "--output", type=Path, default=DATA_DIR / "geographic" / "community_districts.geojson"
    )
    build = sub.add_parser("build", help="Process a completed run into Parquet")
    build.add_argument("--run-dir", type=Path, required=True)
    build.add_argument("--output", type=Path, required=True)
    build.add_argument(
        "--geography", type=Path, help="Validated GeoJSON; omitted means unmatched joins"
    )
    quality = sub.add_parser("quality", help="Validate a Parquet artifact in bounded batches")
    quality.add_argument("--input", type=Path, required=True)
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    try:
        if args.command == "ingest":
            result = ingest(
                args.run_dir or DATA_DIR / "raw" / args.mode,
                mode=args.mode,
                per_month=args.per_month,
                page_size=args.page_size,
            )
            print(
                json.dumps(
                    {k: result[k] for k in ("complete", "audit", "started_at", "finished_at")},
                    indent=2,
                )
            )
        elif args.command == "geography":
            result = download_geography(args.output)
            print(f"Validated {len(result['features'])} geographic features: {args.output}")
        elif args.command == "build":
            result = build_processed(args.run_dir, args.output, geography=args.geography)
            print(
                json.dumps(
                    {k: result[k] for k in ("downloaded_rows", "processed_rows", "excluded_rows")},
                    indent=2,
                )
            )
        else:
            print(json.dumps(check_parquet(args.input), indent=2))
    except (ValueError, OSError, requests.RequestException) as exc:
        parser.exit(1, f"Pipeline error: {exc}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

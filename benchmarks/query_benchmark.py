"""Compare cached Pandas queries and direct Parquet queries in separate processes.

Run: python -m benchmarks.query_benchmark --output benchmarks/demo_results.json
Optional: --synthetic-rows 100000 (temporary, explicitly synthetic demo replicas).
"""

import argparse
import json
import os
import platform
import statistics
import subprocess
import sys
import tempfile
import time
from datetime import UTC, datetime
from pathlib import Path

import duckdb
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from config.settings import DATA_DIR
from pipeline import apply_filters, load_data
from pipeline.contract import SCHEMA
from pipeline.filters import FilterSpec
from pipeline.query import ParquetQuery

COLUMNS = ("unique_key", "borough", "complaint_type", "closure_hours")
FILTERS = {"borough": "Brooklyn", "start_date": "2025-01-01", "end_date": "2025-12-31"}
TASKS = ("filtered_count", "borough", "created_day", "complaint_type", "preview_200")


def peak_rss_mib() -> float | None:
    """OS process high-water RSS, including native allocations; unavailable on Windows."""
    if sys.platform.startswith("linux"):
        # Unlike getrusage, VmHWM is reset on exec: synthetic generation in the
        # parent must not inflate the child worker's reported memory watermark.
        try:
            for line in Path("/proc/self/status").read_text().splitlines():
                if line.startswith("VmHWM:"):
                    return int(line.split()[1]) / 1024
        except OSError:
            return None
        return None
    try:
        import resource
    except ImportError:
        return None
    peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return peak / (1024 * 1024 if sys.platform == "darwin" else 1024)


def canonical(result) -> str:
    """Normalize result values for exact backend parity, independent of row order."""
    if isinstance(result, int):
        return str(result)
    records = []
    for record in result.to_dict(orient="records"):
        values = {
            key: None if pd.isna(value) else value.item() if hasattr(value, "item") else value
            for key, value in record.items()
        }
        records.append(json.dumps(values, sort_keys=True))
    return json.dumps(sorted(records))


def worker(backend: str, path: Path, repeats: int) -> dict:
    """Measure one backend, loading Pandas once and creating SQL connections per query."""
    baseline = peak_rss_mib()
    started = time.perf_counter()
    source = load_data(path) if backend == "pandas" else ParquetQuery(path)
    setup_ms = (time.perf_counter() - started) * 1000
    spec = FilterSpec(**FILTERS)
    timings, outputs = {}, {}
    for task in TASKS:
        elapsed = []
        for _ in range(repeats):
            started = time.perf_counter()
            if backend == "pandas":
                filtered = apply_filters(source, **FILTERS)
                if task == "filtered_count":
                    result = len(filtered)
                elif task == "preview_200":
                    result = filtered.sort_values(
                        ["created_day", "unique_key"], na_position="last"
                    )[list(COLUMNS)].head(200)
                else:
                    result = (
                        filtered.groupby(task, dropna=False).size().reset_index(name="requests")
                    )
            elif task == "filtered_count":
                result = source.count(filters=spec)
            elif task == "preview_200":
                result = source.preview(COLUMNS, filters=spec, limit=200)
            else:
                result = source.aggregate(task, filters=spec)
            elapsed.append((time.perf_counter() - started) * 1000)
        timings[task] = {
            "median_ms": round(statistics.median(elapsed), 3),
            "min_ms": round(min(elapsed), 3),
        }
        outputs[task] = canonical(result)
    return {
        "setup_ms": round(setup_ms, 3),
        "timings": timings,
        "baseline_peak_rss_mib": baseline,
        "peak_rss_mib": peak_rss_mib(),
        "outputs": outputs,
    }


def make_synthetic(seed: Path, output: Path, rows: int) -> None:
    """Replicate real demo profiles with new IDs; label the entire artifact synthetic."""
    if pq.read_metadata(seed).num_rows > 10000:
        raise ValueError("Synthetic seed must be a small demo (<=10,000 rows)")
    demo = load_data(seed)
    if demo.empty:
        raise ValueError("Synthetic seed must not be empty")
    provenance = {
        **demo.attrs["urbanpulse"],
        "mode": "synthetic",
        "sampling": "SYNTHETIC replicated demo profiles with artificial identifiers",
        "source_url": "synthetic://urbanpulse-query-benchmark",
    }
    schema = SCHEMA.with_metadata({b"urbanpulse": json.dumps(provenance).encode()})
    with pq.ParquetWriter(output, schema, compression="zstd") as writer:
        for start in range(0, rows, 10000):
            count = min(rows - start, 10000)
            frame = (
                demo.iloc[[(start + i) % len(demo) for i in range(count)]]
                .reset_index(drop=True)
                .copy()
            )
            frame["unique_key"] = pd.Series(
                [f"synthetic-{start + i:09d}" for i in range(count)], dtype="string"
            )
            writer.write_table(pa.Table.from_pandas(frame, schema=schema, preserve_index=False))


def benchmark(path: Path, repeats: int, *, synthetic: bool) -> dict:
    """Run isolated worker processes, compare exact outputs, and record environment."""
    results = {}
    for backend in ("pandas", "duckdb"):
        output = subprocess.check_output(
            [
                sys.executable,
                "-m",
                "benchmarks.query_benchmark",
                "--worker",
                backend,
                "--input",
                str(path),
                "--repeats",
                str(repeats),
            ],
            text=True,
        )
        results[backend] = json.loads(output)
    if results["pandas"]["outputs"] != results["duckdb"]["outputs"]:
        raise ValueError("Benchmark populations/results differ between backends")
    for result in results.values():
        del result["outputs"]
    metadata = pq.read_metadata(path)
    return {
        "measured_at": datetime.now(UTC).isoformat(),
        "synthetic": synthetic,
        "rows": metadata.num_rows,
        "file_bytes": path.stat().st_size,
        "row_groups": metadata.num_row_groups,
        "row_group_sizes": [metadata.row_group(i).num_rows for i in range(metadata.num_row_groups)],
        "environment": {
            "python": platform.python_version(),
            "platform": platform.platform(),
            "machine": platform.machine(),
            "logical_cpus": os.cpu_count(),
            "pandas": pd.__version__,
            "pyarrow": pa.__version__,
            "duckdb": duckdb.__version__,
        },
        "filters": FILTERS,
        "preview_columns": COLUMNS,
        "repetitions": repeats,
        "duckdb_memory_limit_mb": 512,
        "duckdb_threads": 2,
        "exact_result_parity": True,
        "results": results,
        "method": "separate backend processes; cached Pandas load; fresh SQL connection per query; "
        "median/min wall time; process peak RSS includes imports and native allocations; "
        "Linux RSS from /proc/self/status VmHWM (reset on exec), macOS from getrusage; "
        "OS file cache not flushed; RSS unavailable on Windows",
    }


def main() -> None:
    """CLI entry point, bounded to at most one million synthetic rows."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DATA_DIR / "demo" / "requests.parquet")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--synthetic-rows", type=int)
    parser.add_argument("--worker", choices=("pandas", "duckdb"), help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.repeats < 1:
        parser.error("repeats must be positive")
    if args.worker:
        print(json.dumps(worker(args.worker, args.input.resolve(), args.repeats)))
        return
    if args.synthetic_rows is not None:
        if not 1 <= args.synthetic_rows <= 1000000:
            parser.error("synthetic-rows must be in 1..1000000")
        with tempfile.TemporaryDirectory(prefix="urbanpulse-benchmark-") as temporary:
            path = Path(temporary) / "SYNTHETIC.parquet"
            make_synthetic(args.input.resolve(), path, args.synthetic_rows)
            report = benchmark(path, args.repeats, synthetic=True)
    else:
        report = benchmark(args.input.resolve(), args.repeats, synthetic=False)
    text = json.dumps(report, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text, encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main()

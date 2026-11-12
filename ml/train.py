"""Run both baselines without changing the shared dataset or fetching data."""

import argparse
import json
import platform
import time
from datetime import UTC, datetime
from importlib.metadata import version
from pathlib import Path

import joblib

from config.settings import ROOT
from ml.data_access import COHORTS, MLData
from ml.kmeans import fit_districts
from ml.logistic import fit_logistic


def write_json(path, content):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(content, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def peak_memory_mib():
    """Process high-water RSS on Unix; explicitly unavailable on Windows."""
    try:
        import resource
    except ImportError:
        return None
    usage = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return usage / (1024**2 if platform.system() == "Darwin" else 1024)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", choices=["full"], required=True)
    parser.add_argument("--output", type=Path, default=ROOT / "ml/local")
    parser.add_argument("--results", type=Path, default=ROOT / "ml/results")
    parser.add_argument("--seed", type=int, default=2025)
    parser.add_argument("--train-limit", type=int, default=200000)
    parser.add_argument("--validation-limit", type=int, default=60000)
    parser.add_argument("--test-limit", type=int, default=60000)
    parser.add_argument("--memory-limit-mb", type=int, default=512)
    args = parser.parse_args(argv)
    limits = {name: getattr(args, f"{name}_limit") for name in COHORTS}
    if any(not 1 <= limit <= 1_000_000 for limit in limits.values()):
        parser.error("sample limits must be in 1..1000000")
    args.output.mkdir(parents=True, exist_ok=True)
    args.results.mkdir(parents=True, exist_ok=True)
    started = time.perf_counter()
    data = MLData(memory_limit_mb=args.memory_limit_mb)
    source = data.verify_full()
    common = {
        "model_version": "phase3a-v1",
        "source": source,
        "seed": args.seed,
        "run_started_utc": datetime.now(UTC).isoformat(),
        "packages": {
            name: version(name)
            for name in (
                "scikit-learn",
                "scipy",
                "numpy",
                "pandas",
                "pyarrow",
                "duckdb",
                "joblib",
                "threadpoolctl",
            )
        },
        "python": platform.python_version(),
        "platform": platform.system(),
        "memory_policy": {
            "duckdb_mb": args.memory_limit_mb,
            "duckdb_threads": 1,
            "numerical_threads": 1,
            "note": "DuckDB buffer limit is not a total process RAM limit; "
            "projected bounded samples only; no dense request-level one-hot matrix",
        },
        "verification_seconds": time.perf_counter() - started,
    }
    write_json(args.output / "run_metadata.json", common)
    print(
        f"Verified {source['rows']:,} rows, {source['columns']} columns, "
        f"{source['parquet_sha256']}",
        flush=True,
    )
    stage = time.perf_counter()
    profiles, audit = data.district_profiles()
    clusters, metrics, artifacts = fit_districts(profiles, seed=args.seed)
    clusters["source_sha256"] = source["parquet_sha256"]
    clusters["schema_version"] = source["provenance"]["schema_version"]
    clusters["model_version"] = "phase3a-v1"
    metrics.update(common)
    metrics.update(audit)
    metrics["elapsed_seconds"] = time.perf_counter() - stage
    metrics["process_peak_rss_mib"] = peak_memory_mib()
    # Persist completed K-Means before attempting Logistic Regression.
    joblib.dump({**artifacts, "metadata": metrics}, args.output / "kmeans.joblib")
    for directory in {args.results, args.output}:
        clusters.to_csv(directory / "district_clusters.csv", index=False)
        write_json(directory / "kmeans_metrics.json", metrics)
    print(
        f"K-Means complete: K={metrics['selected_k']}, silhouette={metrics['silhouette']:.4f}",
        flush=True,
    )
    stage = time.perf_counter()
    cohort_audit = data.cohort_audit()
    availability = data.predictor_availability()
    cohorts = {
        name: data.sample(name, limit=limit, seed=args.seed) for name, limit in limits.items()
    }
    sampling = {}
    for name, frame in cohorts.items():
        eligible = cohort_audit.get(name, {}).get("known_labels", 0)
        sampling[name] = {
            "range_inclusive_exclusive": list(COHORTS[name]),
            "limit": limits[name],
            "eligible": eligible,
            "sampled": len(frame),
            "fraction": len(frame) / eligible if eligible else None,
            "eligible_not_sampled": eligible - len(frame),
        }
    extraction = {
        "cohort_audit": cohort_audit,
        "excluded_rows": {
            "invalid_created_date": cohort_audit["invalid_created_date"]["rows"],
            "outside_2025": cohort_audit["outside_2025"]["rows"],
            "unknown_labels_with_valid_2025_dates": sum(
                cohort_audit[name]["unknown_labels"] for name in COHORTS
            ),
            "total": source["rows"] - sum(cohort_audit[name]["known_labels"] for name in COHORTS),
        },
        "predictor_availability": availability,
        "sampling": sampling,
        "sampling_rule": "Within each eligible temporal partition, "
        "ORDER BY sha256(seed || ':' || unique_key), unique_key LIMIT cap; no stratification",
        "exclusion_rule": "Disjoint invalid dates, outside-2025 dates, then unknown labels "
        "within each valid temporal partition. Unknown labels never imputed.",
    }
    write_json(args.output / "logistic_cohorts.json", extraction)
    model, metrics = fit_logistic(cohorts, seed=args.seed)
    metrics.update(common)
    metrics.update(extraction)
    metrics["elapsed_seconds"] = time.perf_counter() - stage
    metrics["total_run_seconds"] = time.perf_counter() - started
    metrics["process_peak_rss_mib"] = peak_memory_mib()
    joblib.dump(
        {"pipeline": model, "threshold": metrics["threshold"], "metadata": metrics},
        args.output / "logistic.joblib",
    )
    for directory in {args.results, args.output}:
        write_json(directory / "logistic_metrics.json", metrics)
    print(
        f"Logistic complete: test AP={metrics['test']['average_precision']}; "
        f"outputs: {args.results}",
        flush=True,
    )


if __name__ == "__main__":
    main()

"""Memory-bounded processing of committed raw pages into atomic Parquet output."""

import json
import sqlite3
import tempfile
from contextlib import closing
from pathlib import Path

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from config.settings import SCHEMA_VERSION
from pipeline.contract import SCHEMA, standardize_types, validate_schema
from pipeline.features import engineer_features
from pipeline.geography import enrich_geography, load_geography, validate_geojson
from pipeline.ingest import iter_pages, sha256, utc_now, write_json
from pipeline.preprocess import preprocess
from pipeline.quality import QualityAccumulator, validate_outcomes


def build_processed(run_dir: Path, output: Path, *, geography: Path | None = None) -> dict:
    """Build a shared artifact, excluding only missing/duplicate IDs with explicit counts.

    First committed occurrence wins for duplicate IDs; original raw pages remain
    intact. Incomplete extractions are rejected. A failed build leaves existing
    output intact; rerun to rebuild from immutable raw pages.
    """
    run_dir, output = Path(run_dir).resolve(), Path(output).resolve()
    manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    if not manifest.get("complete"):
        raise ValueError("Ingestion is incomplete; resume it before building")
    valid_codes = validate_geojson(load_geography(geography)) if geography else set()
    provenance = {
        "schema_version": SCHEMA_VERSION,
        "mode": manifest["config"]["mode"],
        "source_url": manifest["source_url"],
        "extraction_cutoff": manifest["started_at"],
        "extraction_finished": manifest["finished_at"],
        "sampling": manifest["sampling"],
        "manifest_sha256": sha256(run_dir / "manifest.json"),
        "built_at": utc_now(),
        "geography_sha256": sha256(geography) if geography else None,
    }
    schema = SCHEMA.with_metadata({b"urbanpulse": json.dumps(provenance).encode()})
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary_output = output.with_suffix(".parquet.part")
    accumulator = QualityAccumulator()
    excluded = {"missing_unique_key": 0, "duplicate_unique_key": 0}
    downloaded = 0
    raw_missing = {n: 0 for n in manifest["fields"]}
    blank_strings = {n: 0 for n in manifest["fields"]}
    with tempfile.TemporaryDirectory() as temporary:
        with closing(sqlite3.connect(str(Path(temporary) / "seen.sqlite"))) as connection:
            connection.execute("CREATE TABLE seen (key TEXT PRIMARY KEY)")
            with pq.ParquetWriter(temporary_output, schema=schema, compression="zstd") as writer:
                for rows in iter_pages(run_dir, manifest):
                    downloaded += len(rows)
                    for name in raw_missing:
                        raw_missing[name] += sum(row.get(name) in (None, "") for row in rows)
                        blank_strings[name] += sum(
                            isinstance(row.get(name), str) and not row[name].strip() for row in rows
                        )
                    retained = []
                    for row in rows:
                        key = row.get("unique_key")
                        if not key or not str(key).strip():
                            excluded["missing_unique_key"] += 1
                        elif connection.execute(
                            "INSERT OR IGNORE INTO seen VALUES (?)", (key,)
                        ).rowcount:
                            retained.append(row)
                        else:
                            excluded["duplicate_unique_key"] += 1
                    if not retained:
                        continue
                    df = preprocess(pd.DataFrame(retained))
                    df = engineer_features(df, cutoff=manifest["started_at"])
                    df = standardize_types(enrich_geography(df, valid_codes))
                    validate_schema(df)
                    validate_outcomes(df)
                    writer.write_table(
                        pa.Table.from_pandas(df, schema=schema, preserve_index=False)
                    )
                    accumulator.add(df)
    if downloaded != sum(page["rows"] for page in manifest["pages"]):
        raise ValueError("Downloaded row count mismatch")
    temporary_output.replace(output)
    report = {
        **accumulator.report(),
        "provenance": provenance,
        "downloaded_rows": downloaded,
        "excluded_rows": excluded,
        "unique_keys": accumulator.rows,
        "duplicate_keys_in_output": 0,
        "raw_missing_counts": raw_missing,
        "blank_string_counts": blank_strings,
        "raw_missing_percent": {
            k: round(100 * v / downloaded, 4) if downloaded else 0.0 for k, v in raw_missing.items()
        },
        "parquet_sha256": sha256(output),
        "source_count_at_start": manifest.get("source_count_at_start"),
        "downloaded_minus_start_count": (
            downloaded - manifest["source_count_at_start"]
            if "source_count_at_start" in manifest
            else None
        ),
    }
    write_json(output.with_suffix(".quality.json"), report)
    return report

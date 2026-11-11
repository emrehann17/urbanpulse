"""Local-only dataset loading; no network requests or Streamlit dependencies."""

import json
from pathlib import Path

import pandas as pd
import pyarrow.parquet as pq

from config.settings import DATA_DIR, SCHEMA_VERSION
from pipeline.contract import SCHEMA, standardize_types, validate_schema
from pipeline.quality import validate_outcomes


def data_path(dataset: str = "demo") -> Path:
    """Resolve a named dataset independently of the caller's working directory."""
    paths = {
        "demo": DATA_DIR / "demo" / "requests.parquet",
        "full": DATA_DIR / "processed" / "requests.parquet",
        "smoke": DATA_DIR / "processed" / "smoke.parquet",
    }
    if dataset not in paths:
        raise ValueError("dataset must be demo, smoke, or full")
    return paths[dataset]


def inspect_data(path: str | Path | None = None, *, dataset: str = "demo") -> tuple[Path, dict]:
    """Validate local path, Parquet footer schema, and provenance without reading rows.

    This does not replace the offline global uniqueness/outcome quality audit.
    """
    resolved = data_path(dataset) if path is None else Path(path).expanduser()
    if not resolved.is_absolute():
        resolved = DATA_DIR / resolved
    if not resolved.is_file():
        raise FileNotFoundError(f"Dataset not found: {resolved}. Run python -m pipeline --help.")
    schema = pq.read_schema(resolved)
    provenance = json.loads((schema.metadata or {}).get(b"urbanpulse", b"{}"))
    if provenance.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("Unsupported schema version; rebuild with this pipeline")
    if not schema.equals(SCHEMA, check_metadata=False):
        raise ValueError("Parquet schema differs from the shared contract")
    if path is None and dataset == "full" and provenance.get("mode") != "full":
        raise ValueError("A sample cannot be loaded as the full dataset")
    return resolved.resolve(), provenance


def load_data(path: str | Path | None = None, *, dataset: str = "demo") -> pd.DataFrame:
    """Load contract v1 into a DataFrame, with provenance in ``df.attrs``.

    Default is the explicitly labelled demo, never an implicit fallback for full.
    Explicit relative paths are interpreted relative to the repository data root.
    This convenience loader holds the selected artifact in memory; use ParquetQuery
    for full-data aggregates/projections (ingestion/build already stream their work).
    """
    resolved, provenance = inspect_data(path, dataset=dataset)
    table = pq.read_table(resolved)
    df = standardize_types(table.to_pandas())
    validate_schema(df)
    validate_outcomes(df)
    df.attrs["urbanpulse"] = provenance
    return df

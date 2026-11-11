"""Token-optional SODA ingestion with immutable pages and resumable checkpoints."""

import hashlib
import json
import logging
import os
import re
import sqlite3
import tempfile
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from config.settings import BASE_URL, BOROUGH_SCOPE, RAW_FIELDS, REQUESTS_ID, SCOPE

LOG = logging.getLogger(__name__)


def utc_now() -> str:
    """Return an ISO-8601 UTC retrieval timestamp."""
    return datetime.now(UTC).isoformat()


def write_json(path: Path, value: dict, *, compact: bool = False) -> None:
    """Atomically replace a JSON artifact on the same filesystem."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".part")
    temporary.write_text(
        json.dumps(value, indent=None if compact else 2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def sha256(path: Path) -> str:
    """Hash a file without loading it all into memory."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


class SocrataClient:
    """GET client with bounded retries, Retry-After support, and explicit timeouts."""

    def __init__(self, token: str | None = None):
        self.session = requests.Session()
        retry = Retry(
            total=5,
            connect=5,
            read=5,
            status=5,
            backoff_factor=1,
            status_forcelist=(429, 500, 502, 503, 504),
            allowed_methods=("GET",),
            respect_retry_after_header=True,
        )
        self.session.mount("https://", HTTPAdapter(max_retries=retry))
        self.session.headers["User-Agent"] = "UrbanPulse/1.0 (university data pipeline)"
        token = token or os.environ.get("SOCRATA_APP_TOKEN")
        if token:
            self.session.headers["X-App-Token"] = token

    def get(self, endpoint: str, params: dict | None = None):
        """Read public JSON, raising on HTTP errors or invalid JSON."""
        response = self.session.get(BASE_URL + endpoint, params=params, timeout=(15, 120))
        response.raise_for_status()
        return response.json()

    def close(self) -> None:
        """Release pooled HTTP connections."""
        self.session.close()


def verify_schema(metadata: dict) -> list[str]:
    """Fail on missing primary fields/type drift; allow absent auxiliary audit fields."""
    fields = {c["fieldName"]: c["dataTypeName"] for c in metadata["columns"]}
    for name in RAW_FIELDS:
        if name not in fields and name in RAW_FIELDS[-2:]:
            continue
        expected = (
            "calendar_date"
            if "date" in name
            else "number"
            if name in ("latitude", "longitude")
            else "text"
        )
        if fields.get(name) != expected:
            raise ValueError(
                f"Source schema changed: {name}: expected {expected}, got {fields.get(name)}"
            )
    return [name for name in RAW_FIELDS if name in fields]


def iter_pages(run_dir: Path, manifest: dict):
    """Yield verified committed raw pages, preserving original API values."""
    for page in manifest["pages"]:
        path = run_dir / page["file"]
        if sha256(path) != page["sha256"]:
            raise ValueError(f"Raw checksum mismatch: {path}")
        with path.open(encoding="utf-8") as handle:
            rows = [json.loads(line) for line in handle]
        if len(rows) != page["rows"]:
            raise ValueError(f"Raw row count mismatch: {path}")
        if (
            rows
            and "last_created" in page
            and (
                page["last_created"] != rows[-1].get("created_date")
                or page["last_key"] != rows[-1].get("unique_key")
            )
        ):
            raise ValueError(f"Checkpoint cursor does not match committed page: {path}")
        yield rows


def audit_raw(run_dir: Path, manifest: dict) -> dict:
    """Check counts and global key uniqueness using a disk-backed index."""
    with tempfile.TemporaryDirectory() as temporary:
        with closing(sqlite3.connect(str(Path(temporary) / "keys.sqlite"))) as connection:
            connection.execute("CREATE TABLE keys (key TEXT PRIMARY KEY)")
            count = missing = duplicates = 0
            for rows in iter_pages(run_dir, manifest):
                for row in rows:
                    count += 1
                    key = row.get("unique_key")
                    if not key:
                        missing += 1
                        continue
                    inserted = connection.execute("INSERT OR IGNORE INTO keys VALUES (?)", (key,))
                    duplicates += inserted.rowcount == 0
            unique = connection.execute("SELECT COUNT(*) FROM keys").fetchone()[0]
    return {
        "downloaded_rows": count,
        "unique_keys": unique,
        "duplicate_keys": duplicates,
        "missing_keys": missing,
    }


def ingest(
    run_dir: Path,
    *,
    mode: str = "smoke",
    per_month: int = 200,
    page_size: int = 5000,
    client: SocrataClient | None = None,
) -> dict:
    """Download 2025 in monthly creation/key order; resume with identical arguments.

    Smoke selects the earliest ``per_month`` requests per month, not a probability sample.
    Full scans every selected month. Raw JSONL pages are immutable after checkpointing.
    """
    if mode not in {"smoke", "full"} or not 1 <= page_size <= 50000 or per_month < 1:
        raise ValueError("Invalid mode, per_month, or page_size (1..50000)")
    run_dir = Path(run_dir).resolve()
    run_dir.mkdir(parents=True, exist_ok=True)
    client_owned = client is None
    client = client or SocrataClient()
    checkpoint = run_dir / "manifest.json"
    config = {
        "mode": mode,
        "per_month": per_month,
        "page_size": page_size,
        "scope": SCOPE,
        "order": "created_date ASC, unique_key ASC",
    }
    try:
        if checkpoint.exists():
            manifest = json.loads(checkpoint.read_text(encoding="utf-8"))
            if manifest["config"] != config:
                raise ValueError("Checkpoint arguments differ; choose a new --run-dir")
            audit = audit_raw(run_dir, manifest)
            if audit["duplicate_keys"] or audit["missing_keys"]:
                raise ValueError("Checkpoint key audit failed; preserve run for investigation")
            if manifest["complete"]:
                if audit != manifest["audit"]:
                    raise ValueError("Completed checkpoint audit counts do not match raw pages")
                return manifest
        else:
            metadata = client.get(f"/api/views/{REQUESTS_ID}.json")
            fields = verify_schema(metadata)
            write_json(run_dir / "source-schema.json", metadata)
            manifest = {
                "config": config,
                "dataset_id": REQUESTS_ID,
                "source_url": BASE_URL + f"/d/{REQUESTS_ID}",
                "endpoint": BASE_URL + f"/resource/{REQUESTS_ID}.json",
                "started_at": utc_now(),
                "complete": False,
                "pages": [],
                "done_months": [],
                "fields": fields,
                "missing_auxiliary_fields": sorted(set(RAW_FIELDS) - set(fields)),
                "sampling": "earliest creation times per month; lexical key tie-break"
                if mode == "smoke"
                else "none",
            }
            if mode == "full":
                count = client.get(
                    f"/resource/{REQUESTS_ID}.json", {"$select": "count(*) AS n", "$where": SCOPE}
                )
                manifest["source_count_at_start"] = int(count[0]["n"])
            write_json(checkpoint, manifest)
        for month in range(1, 13):
            if month in manifest["done_months"]:
                continue
            pages = [p for p in manifest["pages"] if p["month"] == month]
            fetched = sum(p["rows"] for p in pages)
            last = pages[-1]["last_key"] if pages else None
            last_created = pages[-1]["last_created"] if pages else None
            start = f"2025-{month:02d}-01T00:00:00"
            end = f"2025-{month + 1:02d}-01T00:00:00" if month < 12 else "2026-01-01T00:00:00"
            while mode == "full" or fetched < per_month:
                limit = page_size if mode == "full" else min(page_size, per_month - fetched)
                where = f"created_date >= '{start}' AND created_date < '{end}' AND " + BOROUGH_SCOPE
                if last:
                    if not re.fullmatch(r"\d+", last):
                        raise ValueError("Unexpected non-digit source key")
                    if not re.fullmatch(
                        r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?", last_created
                    ):
                        raise ValueError("Unexpected source timestamp in cursor")
                    where += (
                        f" AND (created_date > '{last_created}' OR "
                        f"(created_date = '{last_created}' AND unique_key > '{last}'))"
                    )
                rows = client.get(
                    f"/resource/{REQUESTS_ID}.json",
                    {
                        "$select": ",".join(manifest["fields"]),
                        "$where": where,
                        "$order": config["order"],
                        "$limit": limit,
                    },
                )
                if not isinstance(rows, list):
                    raise ValueError("Expected a JSON list from SODA")
                if not rows:
                    break
                keys = [row.get("unique_key", "") for row in rows]
                if any(not isinstance(key, str) or not re.fullmatch(r"\d+", key) for key in keys):
                    raise ValueError("Missing or invalid unique key in response")
                cursors = [(row["created_date"], row["unique_key"]) for row in rows]
                if (
                    cursors != sorted(set(cursors))
                    or len(set(keys)) != len(keys)
                    or (last and cursors[0] <= (last_created, last))
                ):
                    raise ValueError("API violated strict key ordering/uniqueness")
                path = run_dir / f"page-{len(manifest['pages']):06d}.jsonl"
                temporary = path.with_suffix(".part")
                with temporary.open("w", encoding="utf-8", newline="\n") as handle:
                    for row in rows:
                        handle.write(json.dumps(row, ensure_ascii=False) + "\n")
                temporary.replace(path)
                last = keys[-1]
                last_created = rows[-1]["created_date"]
                manifest["pages"].append(
                    {
                        "file": path.name,
                        "month": month,
                        "rows": len(rows),
                        "last_key": last,
                        "last_created": last_created,
                        "sha256": sha256(path),
                        "retrieved_at": utc_now(),
                    }
                )
                write_json(checkpoint, manifest)
                fetched += len(rows)
                LOG.info("%s month %02d: %s rows downloaded", mode, month, fetched)
                # A short page is not assumed to be end-of-data: query until empty.
            manifest["done_months"].append(month)
            write_json(checkpoint, manifest)
        manifest["audit"] = audit_raw(run_dir, manifest)
        if manifest["audit"]["missing_keys"] or manifest["audit"]["duplicate_keys"]:
            raise ValueError("Raw keys failed audit; preserve run for investigation")
        if mode == "full":
            difference = manifest["audit"]["downloaded_rows"] - manifest["source_count_at_start"]
            manifest["downloaded_minus_start_count"] = difference
            if difference:
                LOG.warning(
                    "Downloaded count differs from the live start count by %+d rows; "
                    "review snapshot consistency before analysis",
                    difference,
                )
        manifest["finished_at"] = utc_now()
        manifest["complete"] = True
        write_json(checkpoint, manifest)
        return manifest
    finally:
        if client_owned:
            client.close()

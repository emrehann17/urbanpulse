"""Synthetic deterministic fixtures only; these records are not NYC observations."""

import json

import pandas as pd
import pytest

from config.settings import RAW_FIELDS
from pipeline.contract import standardize_types
from pipeline.features import engineer_features
from pipeline.geography import DISTRICT_CODES, JIA_CODES, enrich_geography
from pipeline.ingest import sha256, write_json
from pipeline.preprocess import preprocess


@pytest.fixture
def raw_row():
    return {
        "unique_key": "000123",
        "created_date": "2025-01-01T00:00:00.000",
        "closed_date": "2025-01-02T00:00:00.000",
        "status": "Closed",
        "complaint_type": "Synthetic test complaint",
        "descriptor": None,
        "agency": "TEST",
        "agency_name": "Synthetic test agency",
        "borough": "MANHATTAN",
        "community_board": "01 MANHATTAN",
        "incident_zip": "00123",
        "latitude": "40.75",
        "longitude": "-73.98",
        "open_data_channel_type": "ONLINE",
        "location_type": None,
        "resolution_description": None,
        "resolution_action_updated_date": None,
    }


@pytest.fixture
def transform():
    def run(rows, cutoff="2026-02-01T00:00:00Z"):
        result = engineer_features(preprocess(pd.DataFrame(rows)), cutoff=cutoff)
        return standardize_types(enrich_geography(result, DISTRICT_CODES | JIA_CODES))

    return run


@pytest.fixture
def frame(raw_row, transform):
    return transform(
        [
            raw_row,
            {
                **raw_row,
                "unique_key": "2",
                "borough": "BROOKLYN",
                "agency": "OTHER",
                "complaint_type": "Other",
                "created_date": "2025-02-01T23:30:00.000",
                "closed_date": None,
                "status": "Open",
                "community_board": "01 BROOKLYN",
            },
            {
                **raw_row,
                "unique_key": "3",
                "borough": "QUEENS",
                "created_date": "bad",
                "community_board": "Unspecified QUEENS",
            },
        ]
    )


@pytest.fixture
def raw_run(tmp_path, raw_row):
    """Make a completed two-page synthetic run, with a cross-page duplicate."""
    run = tmp_path / "run"
    run.mkdir()
    pages = []
    for index, rows in enumerate(
        [
            [raw_row],
            [
                raw_row,
                {**raw_row, "unique_key": "2", "status": "Open", "closed_date": None},
                {**raw_row, "unique_key": None},
            ],
        ]
    ):
        path = run / f"page-{index:06d}.jsonl"
        path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
        pages.append({"file": path.name, "rows": len(rows), "sha256": sha256(path)})
    write_json(
        run / "manifest.json",
        {
            "complete": True,
            "config": {"mode": "smoke"},
            "fields": list(RAW_FIELDS),
            "source_url": "https://example.invalid/synthetic-test-fixture",
            "sampling": "synthetic",
            "started_at": "2026-02-01T00:00:00Z",
            "finished_at": "2026-02-01T00:01:00Z",
            "pages": pages,
        },
    )
    return run

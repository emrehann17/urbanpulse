"""Paths and source constants shared by CLI, notebooks, and the application."""

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = Path(os.environ.get("URBANPULSE_DATA_DIR", ROOT / "data")).expanduser().resolve()
BASE_URL = "https://data.cityofnewyork.us"
REQUESTS_ID = "erm2-nwe9"
GEOGRAPHY_ID = "5crt-au7u"
TIMEZONE = "America/New_York"
SCHEMA_VERSION = "1.0.0"
BOROUGHS = ("Manhattan", "Brooklyn", "Queens", "Bronx", "Staten Island")
RAW_FIELDS = (
    "unique_key",
    "created_date",
    "closed_date",
    "status",
    "complaint_type",
    "descriptor",
    "agency",
    "agency_name",
    "borough",
    "community_board",
    "incident_zip",
    "latitude",
    "longitude",
    "open_data_channel_type",
    "location_type",
    "resolution_description",
    "resolution_action_updated_date",
)
DATE_FIELDS = ("created_date", "closed_date", "resolution_action_updated_date")
BOROUGH_SCOPE = "borough in ('MANHATTAN','BROOKLYN','QUEENS','BRONX','STATEN ISLAND')"
SCOPE = (
    "created_date >= '2025-01-01T00:00:00' AND created_date < '2026-01-01T00:00:00' AND "
    + BOROUGH_SCOPE
)

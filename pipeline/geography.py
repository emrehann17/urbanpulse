"""Validated DCP community district identifiers and portable GeoJSON preparation."""

import json
from pathlib import Path

import pandas as pd

from config.settings import BASE_URL, GEOGRAPHY_ID
from pipeline.ingest import SocrataClient, sha256, utc_now, write_json

BOROUGH_CODES = {"MANHATTAN": 1, "BRONX": 2, "BROOKLYN": 3, "QUEENS": 4, "STATEN ISLAND": 5}
DISTRICT_LIMITS = {1: 12, 2: 12, 3: 18, 4: 14, 5: 3}
DISTRICT_CODES = {
    str(b * 100 + n) for b, limit in DISTRICT_LIMITS.items() for n in range(1, limit + 1)
}
JIA_CODES = {"164", "226", "227", "228", "355", "356", "480", "481", "482", "483", "484", "595"}


def validate_geojson(geojson: dict) -> set[str]:
    """Validate unique known codes and polygon coordinate structure in CRS84 degrees.

    Checks structure and envelope, not topological self-intersection. Never repair
    or reproject geometry silently; Socrata GeoJSON is already longitude/latitude.
    """
    if geojson.get("type") != "FeatureCollection":
        raise ValueError("Expected GeoJSON FeatureCollection")
    codes = set()
    for feature in geojson["features"]:
        code = str(feature["properties"]["boro_cd"])
        if code in codes or code not in DISTRICT_CODES | JIA_CODES:
            raise ValueError(f"Duplicate or unknown district: {code}")
        codes.add(code)
        geometry = feature["geometry"]
        if not geometry or geometry["type"] not in {"Polygon", "MultiPolygon"}:
            raise ValueError(f"Invalid polygon for {code}")
        polygons = geometry["coordinates"]
        if geometry["type"] == "Polygon":
            polygons = [polygons]
        if not polygons:
            raise ValueError("Empty geometry")
        for polygon in polygons:
            if not polygon:
                raise ValueError("Empty polygon")
            for ring in polygon:
                if len(ring) < 4 or ring[0] != ring[-1]:
                    raise ValueError("Unclosed or empty polygon ring")
                for lon, lat, *_ in ring:
                    if not (-74.30 <= lon <= -73.65 and 40.45 <= lat <= 40.95):
                        raise ValueError("Coordinates outside NYC longitude/latitude envelope")
    return codes


def download_geography(path: Path, client: SocrataClient | None = None) -> dict:
    """Download and validate all 59 districts and 12 JIAs, recording provenance."""
    owned = client is None
    client = client or SocrataClient()
    try:
        metadata = client.get(f"/api/views/{GEOGRAPHY_ID}.json")
        fields = {c["fieldName"]: c["dataTypeName"] for c in metadata["columns"]}
        if fields.get("boro_cd") != "number" or fields.get("the_geom") != "multipolygon":
            raise ValueError("Geographic source schema changed")
        data = client.get(
            f"/resource/{GEOGRAPHY_ID}.geojson",
            {
                "$select": "boro_cd,the_geom",
                "$order": "boro_cd",
                "$limit": 1000,
            },
        )
        for feature in data["features"]:
            code = str(feature["properties"]["boro_cd"])
            feature["properties"]["boro_cd"] = code
            feature["id"] = code
            feature["properties"]["district_kind"] = (
                "community_district" if code in DISTRICT_CODES else "joint_interest_area"
            )
        codes = validate_geojson(data)
        if codes != DISTRICT_CODES | JIA_CODES:
            raise ValueError("Boundary source does not contain expected 59 districts and 12 JIAs")
        write_json(path, data, compact=True)
        write_json(
            path.with_suffix(".metadata.json"),
            {
                "source_url": BASE_URL + f"/d/{GEOGRAPHY_ID}",
                "endpoint": BASE_URL + f"/resource/{GEOGRAPHY_ID}.geojson",
                "retrieved_at": utc_now(),
                "crs": "OGC:CRS84 (WGS84 longitude, latitude)",
                "transformation": "none",
                "features": len(codes),
                "sha256": sha256(path),
                "source_rows_updated_at": metadata.get("rowsUpdatedAt"),
                "source_description": metadata.get("description"),
            },
        )
        return data
    finally:
        if owned:
            client.close()


def load_geography(path: Path) -> dict:
    """Read and validate a local boundary artifact without network access."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    validate_geojson(data)
    return data


def enrich_geography(df: pd.DataFrame, valid_codes: set[str]) -> pd.DataFrame:
    """Join parsed board codes only to verified polygons; flag borough disagreements.

    Legal borough and service district can differ (Marble Hill, Rikers Island).
    Preserve the board-derived verified code and expose disagreement for review.
    """
    result = df.copy()
    parts = (
        result.community_board.str.strip()
        .str.upper()
        .str.extract(r"^(\d{1,2})\s+(MANHATTAN|BRONX|BROOKLYN|QUEENS|STATEN ISLAND)$")
    )
    candidate = (
        parts[1].map(BOROUGH_CODES).astype("Int64") * 100
        + pd.to_numeric(parts[0], errors="coerce").astype("Int64")
    ).astype("string")
    known = candidate.isin(valid_codes & (DISTRICT_CODES | JIA_CODES))
    result["boro_cd"] = candidate.where(known).astype("string")
    result["geography_status"] = pd.Series("unmatched", index=result.index, dtype="string")
    result.loc[candidate.isin(valid_codes & DISTRICT_CODES), "geography_status"] = (
        "community_district"
    )
    result.loc[candidate.isin(valid_codes & JIA_CODES), "geography_status"] = "joint_interest_area"
    result["board_borough_mismatch"] = (
        parts[1].notna() & result.borough.notna() & parts[1].ne(result.borough.str.upper())
    ).fillna(False)
    return result

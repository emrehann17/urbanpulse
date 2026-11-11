"""Documented borough code mapping, JIA handling, and geometry validation."""

import copy

import pandas as pd
import pytest

from pipeline.geography import enrich_geography, validate_geojson


@pytest.mark.parametrize(
    "board,code,kind",
    [
        ("01 MANHATTAN", "101", "community_district"),
        ("12 BRONX", "212", "community_district"),
        ("18 BROOKLYN", "318", "community_district"),
        ("14 QUEENS", "414", "community_district"),
        ("03 STATEN ISLAND", "503", "community_district"),
        ("64 MANHATTAN", "164", "joint_interest_area"),
        ("Unspecified BROOKLYN", None, "unmatched"),
        ("00 QUEENS", None, "unmatched"),
        ("99 MANHATTAN", None, "unmatched"),
        (None, None, "unmatched"),
    ],
)
def test_mapping(raw_row, transform, board, code, kind):
    row = transform([{**raw_row, "community_board": board}]).iloc[0]
    assert pd.isna(row.boro_cd) if code is None else row.boro_cd == code
    assert row.geography_status == kind


def test_mapping_requires_verified_boundary(frame):
    result = enrich_geography(frame, set())
    assert result.boro_cd.isna().all()
    assert len(result) == len(frame)


def test_service_borough_mismatch_is_flagged(raw_row, transform):
    row = transform([{**raw_row, "community_board": "07 BRONX"}]).iloc[0]
    assert row.boro_cd == "207" and row.board_borough_mismatch


def test_geojson_structure():
    data = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "properties": {"boro_cd": "101"},
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [[[-74, 40.7], [-74, 40.8], [-73.9, 40.8], [-74, 40.7]]],
                },
            }
        ],
    }
    assert validate_geojson(data) == {"101"}
    bad = copy.deepcopy(data)
    bad["features"] *= 2
    with pytest.raises(ValueError, match="Duplicate"):
        validate_geojson(bad)
    bad = copy.deepcopy(data)
    bad["features"][0]["geometry"]["coordinates"][0][1] = [100, 200]
    with pytest.raises(ValueError, match="Coordinates"):
        validate_geojson(bad)

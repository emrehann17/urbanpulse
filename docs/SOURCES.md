# Source verification and provenance

Verified against live source metadata and queries on **2026-11-11**. The initial
sandbox could not resolve hosts; approved network access succeeded. Metadata
snapshots are in `data/metadata/`. Each ingestion run also saves its own schema,
query scope, selected fields, extraction timestamps, page checksums, and counts.
The demo's manifest and quality report preserve its actual retrieval timestamps.

## NYC 311

- [Dataset landing page](https://data.cityofnewyork.us/d/erm2-nwe9)
- [Live metadata](https://data.cityofnewyork.us/api/views/erm2-nwe9.json)
- [Public JSON resource endpoint](https://data.cityofnewyork.us/resource/erm2-nwe9.json)
- [NYC's December 2025 change notice](https://www.nyc.gov/opendata/news/all-news/311-Service-Requests-Updates)

The live title is **311 Service Requests from 2020 to Present**. The historical
2010–2019 data is a different ID, `76ig-c548`, and is not used. NYC's update notice
confirms that the display labels Problem and Problem Detail retain API names
`complaint_type` and `descriptor`. Additional Details (`descriptor_2`) and the
new council/police fields are outside the agreed Phase 1 extraction contract.
All 15 primary and both auxiliary requested fields were present. No substituted
or fabricated fields are used.

| API metadata type | Extracted fields |
| --- | --- |
| text | unique_key, status, complaint_type, descriptor, agency, agency_name, borough, community_board, incident_zip, open_data_channel_type, location_type, resolution_description |
| calendar_date | created_date, closed_date, resolution_action_updated_date |
| number | latitude, longitude |

`calendar_date` metadata represents SODA floating timestamps. Responses tested
used ISO strings without offsets, including fractional seconds. See
[Socrata floating timestamps](https://dev.socrata.com/docs/datatypes/floating_timestamp.html).
The API does not identify an offset or resolve DST folds. Interpreting these
as `America/New_York` is our documented publisher-local-time assumption, not a
claim that the API supplies timezone-aware instants. Ambiguous/nonexistent local
times are retained as raw strings and flagged, with no duration assigned.

## API behavior

The current [Socrata query documentation](https://dev.socrata.com/docs/queries/)
promotes SODA3 POST queries with an application token or authentication. We use
the still-working, documented SODA 2.x `/resource/{id}.json` GET interface to meet
the token-free public access requirement. See
[endpoint versioning](https://dev.socrata.com/docs/endpoints.html) and
[application tokens](https://dev.socrata.com/docs/app-tokens.html). Token-free
live schema, ordered 311 requests, and GeoJSON queries succeeded. An optional
`SOCRATA_APP_TOKEN` is sent only as `X-App-Token`, never in query strings.

Queries explicitly use `$select`, monthly `$where`,
`$order=created_date ASC, unique_key ASC`, and `$limit`. Continuation uses
`created_date > last_created OR (created_date = last_created AND unique_key > last_key)`.
`unique_key` remains text, so timestamp ties compare IDs lexically, never numerically.
[Socrata's ordering documentation](https://dev.socrata.com/docs/queries/order.html)
requires explicit ordering for stable paging. Composite keyset continuation avoids
large offsets. An initial ID-only ordered run suffered repeated read timeouts;
a bounded May query ordered by creation time returned 100 rows in 4.15 seconds.
The partial initial run is preserved locally but is not part of the final demo.
Strict order and duplicate checks detect violations; they cannot make a
live dataset transactionally consistent. Records inserted below a cursor or
moved between months during extraction may be missed or repeated. Full ingestion
records a start count and reports its difference from downloaded rows; equality
alone does not prove a snapshot.

## Community Districts

- [Official dataset and description](https://data.cityofnewyork.us/City-Government/Community-Districts/5crt-au7u/about_data)
- [Metadata](https://data.cityofnewyork.us/api/views/5crt-au7u.json)
- [GeoJSON endpoint](https://data.cityofnewyork.us/resource/5crt-au7u.geojson)
- [DCP Geosupport identifier definitions](https://nycplanning.github.io/Geosupport-UPG/appendices/appendix03/)
- [Socrata GeoJSON format](https://dev.socrata.com/docs/formats/geojson.html)

Live schema: `boro_cd` (number), `the_geom` (multipolygon), `shape_leng` and
`shape_area` (number). We extract only identifiers and geometry; source planar
area/length values are not treated as longitude/latitude measurements. The
verified boundary release is **26c**, updated November 2, 2026. It is a current
boundary file used for 2025 requests, not a verified historical 2025 release.

The GeoJSON has 71 unique IDs: 59 districts and 12 joint interest areas (JIAs).
The first digit is the borough code: Manhattan 1, Bronx 2, Brooklyn 3, Queens 4,
Staten Island 5. The remaining two digits are the board/district number.
Ordinary ranges are 101–112, 201–212, 301–318, 401–414, and 501–503. The explicitly
verified JIA codes are 164, 226–228, 355–356, 480–484, and 595.

`01 MANHATTAN` therefore proposes `101`; it becomes `boro_cd` only if that ID is
present in validated geometry. Unknown/unspecified/zero boards stay unmatched.
A legal borough can differ from a service district (Marble Hill and Rikers
Island). We retain the explicit board-derived code and flag disagreement; do
not silently rewrite it from the request borough.

Coordinates are WGS84 longitude/latitude, OGC:CRS84 axis order; no reprojection
occurs. Validation checks code coverage, unique IDs, polygon/multipolygon types,
closed rings, and a conservative NYC envelope. Topological self-intersection and
point-in-polygon agreement are not verified in Phase 1. The GeoJSON includes
feature `id`, `properties.boro_cd` as strings, and `properties.district_kind`.
Use `featureidkey="properties.boro_cd"` for future Plotly choropleths and separate
JIAs from the 59 ordinary districts.

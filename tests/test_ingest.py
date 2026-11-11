"""Network is mocked: deterministic source pages and transport failures."""

import json
import re
from unittest.mock import Mock

import pytest
import requests

from config.settings import RAW_FIELDS
from pipeline.ingest import SocrataClient, audit_raw, ingest, verify_schema


def source_schema():
    return {
        "columns": [
            {
                "fieldName": n,
                "dataTypeName": "calendar_date"
                if "date" in n
                else "number"
                if n in ("latitude", "longitude")
                else "text",
            }
            for n in RAW_FIELDS
        ]
    }


class FakeClient:
    """Two synthetic records per month, supporting SODA keyset query semantics."""

    def __init__(self, raw_row, fail_at=None):
        self.raw_row = raw_row
        self.calls = []
        self.fail_at = fail_at

    def get(self, endpoint, params=None):
        self.calls.append((endpoint, params))
        if len(self.calls) == self.fail_at:
            raise requests.Timeout("synthetic timeout")
        if "/api/views/" in endpoint:
            return source_schema()
        if params["$select"].startswith("count"):
            return [{"n": "24"}]
        month = int(re.findall(r"created_date >= '2025-(\d\d)", params["$where"])[-1])
        after = re.search(r"unique_key > '(\d+)'", params["$where"])
        rows = [
            {
                **self.raw_row,
                "unique_key": f"{month:02d}{i:02d}",
                "created_date": f"2025-{month:02d}-01T00:00:00",
            }
            for i in range(2)
        ]
        return [row for row in rows if not after or row["unique_key"] > after[1]][
            : params["$limit"]
        ]


def test_pagination_resume_and_complete(tmp_path, raw_row):
    failing = FakeClient(raw_row, fail_at=4)
    with pytest.raises(requests.Timeout):
        ingest(tmp_path, per_month=2, page_size=1, client=failing)
    saved = json.loads((tmp_path / "manifest.json").read_text())
    assert len(saved["pages"]) == 2 and not saved["complete"]
    client = FakeClient(raw_row)
    result = ingest(tmp_path, per_month=2, page_size=1, client=client)
    assert result["complete"] and result["audit"]["unique_keys"] == 24
    assert all(p["rows"] == 1 for p in result["pages"])
    client = FakeClient(raw_row)
    assert ingest(tmp_path, per_month=2, page_size=1, client=client) == result
    assert not client.calls
    with pytest.raises(ValueError, match="arguments differ"):
        ingest(tmp_path, per_month=3, page_size=1, client=client)


def test_full_mode_and_short_pages(tmp_path, raw_row):
    result = ingest(tmp_path, mode="full", page_size=10, client=FakeClient(raw_row))
    assert result["audit"]["downloaded_rows"] == result["source_count_at_start"] == 24
    assert result["sampling"] == "none"


def test_checksums(tmp_path, raw_row):
    result = ingest(tmp_path, per_month=1, client=FakeClient(raw_row))
    (tmp_path / result["pages"][0]["file"]).write_text("corrupt", encoding="utf-8")
    with pytest.raises(ValueError, match="checksum"):
        audit_raw(tmp_path, result)


def test_duplicate_source_page_rejected(tmp_path, raw_row):
    fake = FakeClient(raw_row)
    original = fake.get

    def get(endpoint, params=None):
        rows = original(endpoint, params)
        return rows + rows if params else rows

    fake.get = get
    with pytest.raises(ValueError, match="ordering"):
        ingest(tmp_path, client=fake)


def test_schema_drift_and_auxiliary():
    schema = source_schema()
    schema["columns"] = schema["columns"][:-2]
    assert len(verify_schema(schema)) == 15
    schema["columns"][0]["dataTypeName"] = "number"
    with pytest.raises(ValueError, match="unique_key"):
        verify_schema(schema)


def test_http_errors_timeouts_token_and_retry_policy(monkeypatch):
    monkeypatch.setenv("SOCRATA_APP_TOKEN", "synthetic-test-token")
    client = SocrataClient()
    response = Mock()
    response.json.return_value = [{"unique_key": "1"}]
    client.session.get = Mock(return_value=response)
    assert client.get("/test") == [{"unique_key": "1"}]
    assert client.session.get.call_args.kwargs["timeout"] == (15, 120)
    assert client.session.headers["X-App-Token"] == "synthetic-test-token"
    response.raise_for_status.side_effect = requests.HTTPError("400")
    with pytest.raises(requests.HTTPError):
        client.get("/test")
    client.session.get.side_effect = requests.Timeout()
    with pytest.raises(requests.Timeout):
        client.get("/test")
    retry = client.session.get_adapter("https://").max_retries
    assert retry.total == 5 and retry.is_retry("GET", 429)
    assert retry.is_retry("GET", 503) and not retry.is_retry("GET", 400)
    assert retry.respect_retry_after_header
    retry = retry.increment(error=requests.ConnectionError()).increment(
        error=requests.ConnectionError()
    )
    assert retry.get_backoff_time() == 2
    client.close()


def test_composite_cursor_allows_decreasing_id_across_timestamps(tmp_path, raw_row):
    class ChronologicalClient(FakeClient):
        def get(self, endpoint, params=None):
            if params is None:
                return source_schema()
            assert params["$order"] == "created_date ASC, unique_key ASC"
            month = int(re.findall(r"created_date >= '2025-(\d\d)", params["$where"])[-1])
            rows = [
                {
                    **raw_row,
                    "unique_key": f"{month:02d}99",
                    "created_date": f"2025-{month:02d}-01T00:00:00.000",
                },
                {
                    **raw_row,
                    "unique_key": f"{month:02d}00",
                    "created_date": f"2025-{month:02d}-01T01:00:00.000",
                },
            ]
            cursor_date = re.search(r"created_date > '([^']+)'", params["$where"])
            cursor_key = re.search(r"unique_key > '(\d+)'", params["$where"])
            if cursor_date:
                assert " OR " in params["$where"]
                rows = [
                    row
                    for row in rows
                    if (row["created_date"], row["unique_key"]) > (cursor_date[1], cursor_key[1])
                ]
            return rows[: params["$limit"]]

    result = ingest(tmp_path, per_month=2, page_size=1, client=ChronologicalClient(raw_row))
    assert result["audit"]["unique_keys"] == 24
    assert result["pages"][0]["last_key"] == "0199"
    assert result["pages"][1]["last_key"] == "0100"
    assert result["pages"][1]["last_created"] == "2025-01-01T01:00:00.000"

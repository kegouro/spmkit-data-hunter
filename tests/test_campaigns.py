from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

import spmkit_data_hunter as hunter
from spmkit_data_hunter.campaigns import CampaignConfig, CampaignStore
from spmkit_data_hunter.cli import parse_duration
from spmkit_data_hunter.engine import CampaignEngine
from spmkit_data_hunter.sources import (
    DataCiteSource,
    PagedFigshareSource,
    PagedZenodoSource,
    SearchPage,
)


class FakeClient:
    def __init__(self, get_payloads=None, post_payloads=None):
        self.get_payloads = list(get_payloads or [])
        self.post_payloads = list(post_payloads or [])
        self.get_calls = []
        self.post_calls = []

    def get_json(self, url, **kwargs):
        self.get_calls.append((url, kwargs))
        if not self.get_payloads:
            raise AssertionError("unexpected GET")
        return self.get_payloads.pop(0)

    def post_json(self, url, payload):
        self.post_calls.append((url, payload))
        if not self.post_payloads:
            raise AssertionError("unexpected POST")
        return self.post_payloads.pop(0)


def zenodo_hit(record_id: int, filename: str = "sample.nid"):
    return {
        "id": record_id,
        "metadata": {
            "title": f"Atomic force microscopy dataset {record_id}",
            "description": "AFM source data",
            "license": {"id": "cc-by-4.0"},
        },
        "links": {"html": f"https://zenodo.org/records/{record_id}"},
        "files": [
            {
                "id": record_id * 10,
                "key": filename,
                "size": 123,
                "checksum": "md5:abc",
                "links": {"content": f"https://zenodo.org/api/records/{record_id}/files/x/content"},
            }
        ],
    }


def figshare_detail(record_id: int):
    return {
        "id": record_id,
        "title": f"Atomic force microscopy dataset {record_id}",
        "description": "AFM data with processed output",
        "doi": f"10.6084/m9.figshare.{record_id}",
        "url_public_html": f"https://figshare.com/articles/dataset/{record_id}",
        "license": {"name": "CC BY 4.0"},
        "files": [
            {
                "id": record_id * 10,
                "name": "sample.nid",
                "download_url": f"https://ndownloader.figshare.com/files/{record_id * 10}",
                "size": 456,
                "supplied_md5": "def",
            }
        ],
    }


def test_term_matching_avoids_substring_false_positives() -> None:
    assert "raw" not in hunter.infer_categories("drawings.csv")
    assert "code" not in hunter.infer_categories("decode_results.txt")


def test_raw_csv_does_not_fake_processed_companion() -> None:
    categories = hunter.infer_categories("raw_data.csv")
    assert "raw" in categories
    assert "processed" not in categories


def test_raw_only_record_is_reader_fixture_and_bronze() -> None:
    record = hunter.DatasetRecord(
        source="test",
        source_id="1",
        title="Atomic force microscopy native scan",
        files=[hunter.FileAsset.build(name="sample.nid", url="https://example.org/sample.nid")],
    )
    hunter.score_record(record)
    assert record.utility_class == "reader_fixture"
    assert record.level == "bronze"


def test_distinct_raw_and_processed_with_docs_is_benchmark_ready() -> None:
    record = hunter.DatasetRecord(
        source="test",
        source_id="1",
        title="Atomic force microscopy benchmark",
        files=[
            hunter.FileAsset.build(name="sample.nid", url="https://example.org/sample.nid"),
            hunter.FileAsset.build(
                name="processed_results.csv", url="https://example.org/results.csv"
            ),
            hunter.FileAsset.build(name="README.md", url="https://example.org/README.md"),
        ],
    )
    hunter.score_record(record)
    assert record.utility_class == "benchmark_ready"


@pytest.mark.parametrize(
    ("value", "seconds"),
    [("0", 0), ("90", 90), ("30s", 30), ("2m", 120), ("1.5h", 5400), ("1d", 86400)],
)
def test_parse_duration(value: str, seconds: int) -> None:
    assert parse_duration(value) == seconds


def test_zenodo_pages_resume_from_cursor() -> None:
    client = FakeClient(
        get_payloads=[
            {"hits": {"total": 3, "hits": [zenodo_hit(2), zenodo_hit(3)]}},
            {"hits": {"total": 3, "hits": []}},
        ]
    )
    source = PagedZenodoSource(client)
    pages = list(source.iter_pages("AFM", cursor="2", page_size=2))
    assert pages[0].cursor_used == "2"
    assert pages[0].next_cursor == "3"
    assert pages[-1].exhausted is True
    assert client.get_calls[0][1]["params"]["page"] == 2


def test_figshare_hydrates_every_item_in_page() -> None:
    client = FakeClient(
        post_payloads=[[{"id": 1}, {"id": 2}], []],
        get_payloads=[figshare_detail(1), figshare_detail(2)],
    )
    source = PagedFigshareSource(client)
    pages = list(source.iter_pages("AFM", page_size=2))
    assert len(pages[0].records) == 2
    assert len(pages[0].records[0].files) == 1
    assert pages[-1].exhausted is True


def test_datacite_uses_cursor_and_marks_metadata_only() -> None:
    payload = {
        "data": [
            {
                "id": "10.1234/example",
                "attributes": {
                    "doi": "10.1234/example",
                    "titles": [{"title": "Atomic force microscopy data"}],
                    "descriptions": [{"description": "AFM dataset"}],
                    "url": "https://example.org/dataset",
                    "types": {"resourceTypeGeneral": "Dataset"},
                    "creators": [{"name": "A. Researcher"}],
                    "rightsList": [{"rightsIdentifier": "CC-BY-4.0"}],
                },
            }
        ],
        "links": {"next": "https://api.datacite.org/dois?page%5Bcursor%5D=abc&page%5Bsize%5D=1"},
        "meta": {"total": 2},
    }
    empty = {"data": [], "links": {}, "meta": {"total": 2}}
    client = FakeClient(get_payloads=[payload, empty])
    source = DataCiteSource(client)
    pages = list(source.iter_pages("AFM", page_size=1))
    assert pages[0].next_cursor == "abc"
    assert pages[0].records[0].source == "datacite"
    assert pages[0].records[0].files == []
    assert pages[0].records[0].utility_class in {
        "incomplete",
        "documentation_only",
        "crosscheck_candidate",
    }
    assert pages[0].records[0].instrument_data_unknown is True
    assert client.get_calls[1][1]["params"]["page[cursor]"] == "abc"


def test_campaign_store_round_trip_and_checkpoint(tmp_path: Path) -> None:
    store = CampaignStore(tmp_path / "campaigns.sqlite3")
    try:
        config = CampaignConfig(
            slug="deep-hunt",
            output=str(tmp_path),
            sources=["zenodo"],
            queries=["AFM"],
        )
        campaign = store.create(config)
        store.save_checkpoint(
            campaign.id,
            "zenodo",
            "AFM",
            cursor="4",
            page_number=3,
            exhausted=False,
            records_seen=75,
        )
        checkpoint = store.get_checkpoint(campaign.id, "zenodo", "AFM")
        assert checkpoint.cursor == "4"
        assert checkpoint.records_seen == 75
        store.request(campaign.id, "pause_requested")
        assert store.requested_status(campaign.id) == "pause_requested"
    finally:
        store.close()


def test_campaign_engine_persists_and_exports(tmp_path: Path, monkeypatch) -> None:
    class FakeSource:
        name = "fake"
        page_size_default = 2

        def iter_pages(self, query, *, cursor=None, page_size=None):
            assert cursor is None
            record = hunter.DatasetRecord(
                source="fake",
                source_id="1",
                title="Atomic force microscopy benchmark",
                files=[
                    hunter.FileAsset.build(name="sample.nid", url="https://example.org/sample.nid"),
                    hunter.FileAsset.build(
                        name="processed_results.csv", url="https://example.org/results.csv"
                    ),
                    hunter.FileAsset.build(name="README.md", url="https://example.org/README.md"),
                ],
                matched_query=query,
            )
            hunter.score_record(record)
            yield SearchPage([record], None, None, 1, 1)

    monkeypatch.setattr(
        "spmkit_data_hunter.engine.build_paged_sources",
        lambda names, client: [FakeSource()],
    )
    output = tmp_path / "out"
    store = CampaignStore(output / "campaigns.sqlite3")
    try:
        campaign = store.create(
            CampaignConfig(
                slug="smoke",
                output=str(output),
                sources=["fake"],
                queries=["AFM"],
                heartbeat_seconds=1,
            )
        )
        result = CampaignEngine(store).run(campaign.slug)
        assert result.status == "completed"
        assert result.stats["records_new"] == 1
        assert (output / "catalog.json").exists()
        data = json.loads((output / "catalog.json").read_text())
        assert data[0]["utility_class"] == "benchmark_ready"
    finally:
        store.close()


def test_campaign_pause_is_exactly_at_page_boundary(tmp_path: Path, monkeypatch) -> None:
    output = tmp_path / "out"
    store = CampaignStore(output / "campaigns.sqlite3")
    campaign = store.create(
        CampaignConfig(
            slug="pause-test",
            output=str(output),
            sources=["fake"],
            queries=["AFM"],
        )
    )

    class PausingSource:
        name = "fake"
        page_size_default = 1

        def iter_pages(self, query, *, cursor=None, page_size=None):
            record = hunter.DatasetRecord(
                source="fake",
                source_id="1",
                title="Atomic force microscopy scan",
                files=[hunter.FileAsset.build(name="sample.nid", url="https://example.org/a")],
                matched_query=query,
            )
            hunter.score_record(record)
            yield SearchPage([record], cursor, "2", 1, 2)
            store.request(campaign.id, "pause_requested")
            yield SearchPage([], "2", None, 2, 2)

    monkeypatch.setattr(
        "spmkit_data_hunter.engine.build_paged_sources",
        lambda names, client: [PausingSource()],
    )
    try:
        result = CampaignEngine(store).run(campaign.slug)
        assert result.status == "paused"
        checkpoint = store.get_checkpoint(campaign.id, "fake", "AFM")
        assert checkpoint.cursor == "2"
        assert checkpoint.page_number == 1
        assert checkpoint.exhausted is False
    finally:
        store.close()


def test_catalog_migration_adds_utility_class(tmp_path: Path) -> None:
    db = tmp_path / "catalog.sqlite3"
    conn = sqlite3.connect(db)
    conn.execute(
        """
        CREATE TABLE records (
            record_key TEXT PRIMARY KEY,
            source TEXT, source_id TEXT, title TEXT,
            score INTEGER, level TEXT, metadata_json TEXT, updated_at TEXT
        )
        """
    )
    conn.commit()
    conn.close()
    catalog = hunter.Catalog(db)
    try:
        columns = {row[1] for row in catalog.conn.execute("PRAGMA table_info(records)")}
        assert "utility_class" in columns
    finally:
        catalog.close()


def test_private_literal_ip_is_rejected() -> None:
    assert hunter.is_safe_https_url("https://127.0.0.1/file.nid") is False
    assert hunter.is_safe_https_url("https://169.254.169.254/latest/meta-data") is False
    assert hunter.is_safe_https_url("https://example.org/file.nid") is True


def test_catalog_asset_verification_round_trip(tmp_path: Path) -> None:
    catalog = hunter.Catalog(tmp_path / "catalog.sqlite3")
    try:
        record = hunter.DatasetRecord(
            source="test",
            source_id="1",
            title="Atomic force microscopy data",
            files=[hunter.FileAsset.build(name="sample.nid", url="https://example.org/a")],
        )
        hunter.score_record(record)
        catalog.upsert(record)
        catalog.update_asset_verification(
            record.key,
            record.files[0].url,
            verification_status="reachable",
            verification_notes="HEAD OK",
            observed_size=123,
        )
        row = catalog.conn.execute(
            "SELECT verification_status, verification_notes, size FROM assets"
        ).fetchone()
        assert row == ("reachable", "HEAD OK", 123)
    finally:
        catalog.close()


def test_probe_asset_reachable() -> None:
    import requests

    from spmkit_data_hunter.verification import probe_asset

    response = requests.Response()
    response.status_code = 200
    response.url = "https://example.org/file.nid"
    response.headers["Content-Length"] = "42"
    response._content_consumed = True

    class Client:
        def request(self, method, url, **kwargs):
            assert method == "HEAD"
            return response

    asset = hunter.FileAsset.build(name="file.nid", url="https://example.org/file.nid")
    result = probe_asset(Client(), asset)
    assert result.status == "reachable"
    assert result.observed_size == 42


def test_archive_inventory_flags_unsafe_paths(tmp_path: Path) -> None:
    import zipfile

    archive_path = tmp_path / "bundle.zip"
    with zipfile.ZipFile(archive_path, "w") as archive:
        archive.writestr("../escape.nid", b"123")
        archive.writestr("safe/results.csv", b"a,b\n1,2\n")
    report = hunter.archive_inventory(archive_path)
    assert "../escape.nid" in report["unsafe_paths"]
    assert report["entry_count"] == 2
    assert report["total_uncompressed_bytes"] > 0


def test_catalog_download_status_persists_sha256(tmp_path: Path) -> None:
    catalog = hunter.Catalog(tmp_path / "catalog.sqlite3")
    try:
        record = hunter.DatasetRecord(
            source="test",
            source_id="sha",
            title="Atomic force microscopy data",
            files=[hunter.FileAsset.build(name="sample.nid", url="https://example.org/sha")],
        )
        hunter.score_record(record)
        catalog.upsert(record)
        catalog.update_asset_status(
            record.key,
            record.files[0].url,
            downloaded_path="/tmp/sample.nid",
            download_status="downloaded",
            checksum_status="not_available",
            sha256="a" * 64,
        )
        row = catalog.conn.execute(
            "SELECT download_status, sha256 FROM assets WHERE record_key=?",
            (record.key,),
        ).fetchone()
        assert row == ("downloaded", "a" * 64)
    finally:
        catalog.close()

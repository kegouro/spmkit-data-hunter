"""Read helpers for the legacy-compatible SQLite catalog."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from .legacy import DatasetRecord, FileAsset, score_record


def record_from_dict(data: dict[str, object]) -> DatasetRecord:
    file_fields = {
        "name",
        "url",
        "size",
        "checksum",
        "categories",
        "source_file_id",
        "downloaded_path",
        "download_status",
        "checksum_status",
        "sha256",
        "verification_status",
        "verification_notes",
    }
    files: list[FileAsset] = []
    for item in data.get("files") or []:
        if isinstance(item, dict):
            files.append(
                FileAsset(**{key: value for key, value in item.items() if key in file_fields})
            )

    record_fields = {
        "source",
        "source_id",
        "title",
        "description",
        "doi",
        "landing_url",
        "license",
        "published",
        "modified",
        "creators",
        "keywords",
        "related_identifiers",
        "matched_query",
        "score",
        "level",
        "score_reasons",
        "benchmark_score",
        "relevance_score",
        "domain_relevant",
        "relevance_reasons",
        "utility_class",
        "utility_reasons",
        "discovered_at",
    }
    kwargs = {key: value for key, value in data.items() if key in record_fields}
    kwargs["files"] = files
    return DatasetRecord(**kwargs)


def load_records(catalog_path: Path, keys: list[str] | None = None) -> list[DatasetRecord]:
    if not catalog_path.exists():
        return []
    conn = sqlite3.connect(str(catalog_path))
    conn.row_factory = sqlite3.Row
    try:
        if keys is None:
            rows = conn.execute("SELECT record_key, metadata_json FROM records").fetchall()
        elif not keys:
            return []
        else:
            placeholders = ",".join("?" for _ in keys)
            rows = conn.execute(
                f"SELECT record_key, metadata_json FROM records WHERE record_key IN ({placeholders})",  # noqa: S608
                keys,
            ).fetchall()

        result: list[DatasetRecord] = []
        for row in rows:
            data = json.loads(row["metadata_json"])
            assets = conn.execute(
                "SELECT * FROM assets WHERE record_key=? ORDER BY name", (row["record_key"],)
            ).fetchall()
            data["files"] = [
                {
                    "name": asset["name"],
                    "url": asset["url"],
                    "size": asset["size"],
                    "checksum": asset["checksum"] or "",
                    "categories": json.loads(asset["categories"] or "[]"),
                    "source_file_id": asset["source_file_id"] or "",
                    "downloaded_path": asset["downloaded_path"] or "",
                    "download_status": asset["download_status"] or "pending",
                    "checksum_status": asset["checksum_status"] or "not_checked",
                    "sha256": (asset["sha256"] or "" if "sha256" in asset.keys() else ""),
                    "verification_status": (
                        asset["verification_status"] or "not_checked"
                        if "verification_status" in asset.keys()
                        else "not_checked"
                    ),
                    "verification_notes": (
                        asset["verification_notes"] or ""
                        if "verification_notes" in asset.keys()
                        else ""
                    ),
                }
                for asset in assets
            ]
            result.append(score_record(record_from_dict(data)))
        return sorted(result, key=lambda item: (item.domain_relevant, item.score), reverse=True)
    finally:
        conn.close()

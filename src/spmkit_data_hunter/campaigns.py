"""Persistent campaign model for long-running discovery jobs."""

from __future__ import annotations

import json
import sqlite3
import uuid
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


def utc_now() -> str:
    return datetime.now(UTC).isoformat()


@dataclass(slots=True)
class CampaignConfig:
    slug: str
    output: str
    sources: list[str]
    queries: list[str]
    page_size: int = 100
    max_runtime_seconds: int = 0
    max_records: int = 0
    heartbeat_seconds: int = 15
    min_score: int = 0
    require_open_license: bool = False
    rate_seconds: float = 1.05
    timeout: float = 45.0

    def to_json(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False, sort_keys=True)

    @classmethod
    def from_json(cls, value: str) -> CampaignConfig:
        return cls(**json.loads(value))


@dataclass(slots=True)
class Campaign:
    id: str
    slug: str
    status: str
    requested_status: str
    config: CampaignConfig
    created_at: str
    updated_at: str
    started_at: str
    finished_at: str
    last_heartbeat_at: str
    stats: dict[str, Any]
    last_error: str


@dataclass(slots=True)
class Checkpoint:
    campaign_id: str
    source: str
    query: str
    cursor: str | None
    page_number: int
    exhausted: bool
    records_seen: int
    updated_at: str


class CampaignStore:
    """SQLite-backed source of truth for campaigns and checkpoints."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(path), timeout=30)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA foreign_keys=ON")
        self.conn.execute("PRAGMA busy_timeout=30000")
        self._create_schema()

    def _create_schema(self) -> None:
        self.conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS schema_migrations (
                version INTEGER PRIMARY KEY,
                applied_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS campaigns (
                id TEXT PRIMARY KEY,
                slug TEXT NOT NULL UNIQUE,
                status TEXT NOT NULL,
                requested_status TEXT NOT NULL DEFAULT '',
                config_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                started_at TEXT NOT NULL DEFAULT '',
                finished_at TEXT NOT NULL DEFAULT '',
                last_heartbeat_at TEXT NOT NULL DEFAULT '',
                stats_json TEXT NOT NULL DEFAULT '{}',
                last_error TEXT NOT NULL DEFAULT ''
            );

            CREATE TABLE IF NOT EXISTS checkpoints (
                campaign_id TEXT NOT NULL,
                source TEXT NOT NULL,
                query TEXT NOT NULL,
                cursor TEXT,
                page_number INTEGER NOT NULL DEFAULT 0,
                exhausted INTEGER NOT NULL DEFAULT 0,
                records_seen INTEGER NOT NULL DEFAULT 0,
                updated_at TEXT NOT NULL,
                PRIMARY KEY (campaign_id, source, query),
                FOREIGN KEY (campaign_id) REFERENCES campaigns(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS campaign_records (
                campaign_id TEXT NOT NULL,
                record_key TEXT NOT NULL,
                source TEXT NOT NULL,
                query TEXT NOT NULL,
                discovered_at TEXT NOT NULL,
                PRIMARY KEY (campaign_id, record_key),
                FOREIGN KEY (campaign_id) REFERENCES campaigns(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                campaign_id TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                level TEXT NOT NULL,
                event_type TEXT NOT NULL,
                source TEXT NOT NULL DEFAULT '',
                query TEXT NOT NULL DEFAULT '',
                message TEXT NOT NULL,
                payload_json TEXT NOT NULL DEFAULT '{}',
                FOREIGN KEY (campaign_id) REFERENCES campaigns(id) ON DELETE CASCADE
            );

            CREATE INDEX IF NOT EXISTS idx_events_campaign_time
                ON events(campaign_id, timestamp);
            CREATE INDEX IF NOT EXISTS idx_campaign_records_campaign
                ON campaign_records(campaign_id);
            """
        )
        self.conn.execute(
            "INSERT OR IGNORE INTO schema_migrations(version, applied_at) VALUES(1, ?)",
            (utc_now(),),
        )
        self.conn.commit()

    def create(self, config: CampaignConfig) -> Campaign:
        now = utc_now()
        campaign_id = str(uuid.uuid4())
        self.conn.execute(
            """
            INSERT INTO campaigns(
                id, slug, status, requested_status, config_json,
                created_at, updated_at, stats_json
            ) VALUES(?, ?, 'created', '', ?, ?, ?, '{}')
            """,
            (campaign_id, config.slug, config.to_json(), now, now),
        )
        self.conn.commit()
        return self.get(config.slug)

    def _row_to_campaign(self, row: sqlite3.Row) -> Campaign:
        return Campaign(
            id=row["id"],
            slug=row["slug"],
            status=row["status"],
            requested_status=row["requested_status"],
            config=CampaignConfig.from_json(row["config_json"]),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            started_at=row["started_at"],
            finished_at=row["finished_at"],
            last_heartbeat_at=row["last_heartbeat_at"],
            stats=json.loads(row["stats_json"] or "{}"),
            last_error=row["last_error"],
        )

    def get(self, slug_or_id: str) -> Campaign:
        row = self.conn.execute(
            "SELECT * FROM campaigns WHERE slug=? OR id=?",
            (slug_or_id, slug_or_id),
        ).fetchone()
        if row is None:
            raise KeyError(f"Campaña no encontrada: {slug_or_id}")
        return self._row_to_campaign(row)

    def list(self) -> list[Campaign]:
        rows = self.conn.execute("SELECT * FROM campaigns ORDER BY created_at DESC").fetchall()
        return [self._row_to_campaign(row) for row in rows]

    def set_status(
        self,
        campaign_id: str,
        status: str,
        *,
        clear_request: bool = False,
        error: str = "",
        stats: dict[str, Any] | None = None,
    ) -> None:
        now = utc_now()
        fields = ["status=?", "updated_at=?", "last_error=?"]
        values: list[Any] = [status, now, error]
        if clear_request:
            fields.append("requested_status='' ")
        if status == "running":
            fields.append("started_at=CASE WHEN started_at='' THEN ? ELSE started_at END")
            values.append(now)
        if status in {"completed", "completed_with_errors", "stopped", "failed"}:
            fields.append("finished_at=?")
            values.append(now)
        if stats is not None:
            fields.append("stats_json=?")
            values.append(json.dumps(stats, ensure_ascii=False, sort_keys=True))
        values.append(campaign_id)
        self.conn.execute(
            f"UPDATE campaigns SET {', '.join(fields)} WHERE id=?",  # noqa: S608
            values,
        )
        self.conn.commit()

    def request(self, campaign_id: str, requested_status: str) -> None:
        self.conn.execute(
            "UPDATE campaigns SET requested_status=?, updated_at=? WHERE id=?",
            (requested_status, utc_now(), campaign_id),
        )
        self.conn.commit()

    def requested_status(self, campaign_id: str) -> str:
        row = self.conn.execute(
            "SELECT requested_status FROM campaigns WHERE id=?", (campaign_id,)
        ).fetchone()
        return str(row[0]) if row else ""

    def heartbeat(self, campaign_id: str, stats: dict[str, Any]) -> None:
        now = utc_now()
        self.conn.execute(
            """
            UPDATE campaigns
            SET last_heartbeat_at=?, updated_at=?, stats_json=?
            WHERE id=?
            """,
            (now, now, json.dumps(stats, ensure_ascii=False, sort_keys=True), campaign_id),
        )
        self.conn.commit()

    def get_checkpoint(self, campaign_id: str, source: str, query: str) -> Checkpoint:
        row = self.conn.execute(
            """
            SELECT * FROM checkpoints
            WHERE campaign_id=? AND source=? AND query=?
            """,
            (campaign_id, source, query),
        ).fetchone()
        if row is None:
            return Checkpoint(campaign_id, source, query, None, 0, False, 0, "")
        return Checkpoint(
            campaign_id=row["campaign_id"],
            source=row["source"],
            query=row["query"],
            cursor=row["cursor"],
            page_number=row["page_number"],
            exhausted=bool(row["exhausted"]),
            records_seen=row["records_seen"],
            updated_at=row["updated_at"],
        )

    def save_checkpoint(
        self,
        campaign_id: str,
        source: str,
        query: str,
        *,
        cursor: str | None,
        page_number: int,
        exhausted: bool,
        records_seen: int,
    ) -> None:
        self.conn.execute(
            """
            INSERT INTO checkpoints(
                campaign_id, source, query, cursor, page_number,
                exhausted, records_seen, updated_at
            ) VALUES(?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(campaign_id, source, query) DO UPDATE SET
                cursor=excluded.cursor,
                page_number=excluded.page_number,
                exhausted=excluded.exhausted,
                records_seen=excluded.records_seen,
                updated_at=excluded.updated_at
            """,
            (
                campaign_id,
                source,
                query,
                cursor,
                page_number,
                1 if exhausted else 0,
                records_seen,
                utc_now(),
            ),
        )
        self.conn.commit()

    def link_record(self, campaign_id: str, record_key: str, source: str, query: str) -> bool:
        before = self.conn.total_changes
        self.conn.execute(
            """
            INSERT OR IGNORE INTO campaign_records(
                campaign_id, record_key, source, query, discovered_at
            ) VALUES(?, ?, ?, ?, ?)
            """,
            (campaign_id, record_key, source, query, utc_now()),
        )
        self.conn.commit()
        return self.conn.total_changes > before

    def record_keys(self, campaign_id: str) -> list[str]:
        rows = self.conn.execute(
            "SELECT record_key FROM campaign_records WHERE campaign_id=? ORDER BY discovered_at",
            (campaign_id,),
        ).fetchall()
        return [str(row[0]) for row in rows]

    def event(
        self,
        campaign_id: str,
        event_type: str,
        message: str,
        *,
        level: str = "info",
        source: str = "",
        query: str = "",
        payload: dict[str, Any] | None = None,
    ) -> None:
        self.conn.execute(
            """
            INSERT INTO events(
                campaign_id, timestamp, level, event_type, source,
                query, message, payload_json
            ) VALUES(?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                campaign_id,
                utc_now(),
                level,
                event_type,
                source,
                query,
                message,
                json.dumps(payload or {}, ensure_ascii=False, sort_keys=True),
            ),
        )
        self.conn.commit()

    def close(self) -> None:
        self.conn.close()

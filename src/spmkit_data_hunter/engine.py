"""Long-running campaign execution with durable page checkpoints."""

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Any

import requests

from .campaigns import Campaign, CampaignStore
from .catalog_io import load_records
from .legacy import (
    DEFAULT_USER_AGENT,
    Catalog,
    HttpClient,
    export_catalog,
    license_allowed,
)
from .sources import PagedSource, build_paged_sources

LOG = logging.getLogger("spmkit-data-hunter.campaign")


class CampaignEngine:
    def __init__(self, store: CampaignStore) -> None:
        self.store = store

    def _stats(self, campaign: Campaign) -> dict[str, Any]:
        defaults: dict[str, Any] = {
            "pages": 0,
            "records_seen": 0,
            "records_new": 0,
            "records_duplicate": 0,
            "records_filtered": 0,
            "files_seen": 0,
            "errors": 0,
            "source": "",
            "query": "",
            "page": 0,
            "total_hint": None,
            "started_monotonic": time.monotonic(),
        }
        defaults.update(campaign.stats)
        # Monotonic values are process-local; reset on every invocation.
        defaults["started_monotonic"] = time.monotonic()
        return defaults

    @staticmethod
    def _public_stats(stats: dict[str, Any], started: float) -> dict[str, Any]:
        public = {key: value for key, value in stats.items() if key != "started_monotonic"}
        public["runtime_seconds"] = round(time.monotonic() - started, 2)
        return public

    def _heartbeat(
        self,
        campaign_id: str,
        stats: dict[str, Any],
        started: float,
        *,
        force: bool = False,
        last_print: float,
        interval: int,
    ) -> float:
        now = time.monotonic()
        if not force and now - last_print < max(1, interval):
            return last_print
        public = self._public_stats(stats, started)
        self.store.heartbeat(campaign_id, public)
        LOG.info(
            "heartbeat source=%s page=%s seen=%s new=%s dup=%s files=%s errors=%s runtime=%.1fs",
            public.get("source") or "-",
            public.get("page") or 0,
            public.get("records_seen") or 0,
            public.get("records_new") or 0,
            public.get("records_duplicate") or 0,
            public.get("files_seen") or 0,
            public.get("errors") or 0,
            public.get("runtime_seconds") or 0,
        )
        return now

    def _budget_reached(self, campaign: Campaign, stats: dict[str, Any], started: float) -> str:
        config = campaign.config
        if config.max_runtime_seconds and time.monotonic() - started >= config.max_runtime_seconds:
            return "max_runtime"
        if config.max_records and stats["records_new"] >= config.max_records:
            return "max_records"
        request = self.store.requested_status(campaign.id)
        if request == "pause_requested":
            return "pause_requested"
        if request == "stop_requested":
            return "stop_requested"
        return ""

    def _run_source_query(
        self,
        campaign: Campaign,
        source: PagedSource,
        query: str,
        catalog: Catalog,
        stats: dict[str, Any],
        started: float,
        last_print: float,
    ) -> tuple[str, float]:
        config = campaign.config
        checkpoint = self.store.get_checkpoint(campaign.id, source.name, query)
        if checkpoint.exhausted:
            return "", last_print

        records_seen_for_partition = checkpoint.records_seen
        for page in source.iter_pages(
            query,
            cursor=checkpoint.cursor,
            page_size=config.page_size,
        ):
            # Budgets are checked between pages. This deliberately avoids losing
            # the unprocessed tail of a page and makes checkpoints exact.
            reason = self._budget_reached(campaign, stats, started)
            if reason:
                return reason, last_print

            stats["source"] = source.name
            stats["query"] = query
            stats["page"] = page.page_number
            stats["total_hint"] = page.total_hint

            for record in page.records:
                stats["records_seen"] += 1
                records_seen_for_partition += 1
                stats["files_seen"] += len(record.files)
                if record.score < config.min_score:
                    stats["records_filtered"] += 1
                    continue
                if not license_allowed(record, config.require_open_license):
                    stats["records_filtered"] += 1
                    continue
                catalog.upsert(record)
                if self.store.link_record(campaign.id, record.key, source.name, query):
                    stats["records_new"] += 1
                else:
                    stats["records_duplicate"] += 1

            # Commit the next cursor only after the complete page was persisted.
            self.store.save_checkpoint(
                campaign.id,
                source.name,
                query,
                cursor=page.next_cursor,
                page_number=page.page_number,
                exhausted=page.exhausted,
                records_seen=records_seen_for_partition,
            )
            stats["pages"] += 1
            last_print = self._heartbeat(
                campaign.id,
                stats,
                started,
                force=True,
                last_print=last_print,
                interval=config.heartbeat_seconds,
            )
            if page.exhausted:
                break

        return "", last_print

    def run(self, slug_or_id: str) -> Campaign:
        campaign = self.store.get(slug_or_id)
        config = campaign.config
        output = Path(config.output).expanduser().resolve()
        output.mkdir(parents=True, exist_ok=True)
        catalog = Catalog(output / "catalog.sqlite3")
        client = HttpClient(
            timeout=config.timeout,
            user_agent=DEFAULT_USER_AGENT,
            rate_seconds=config.rate_seconds,
        )
        sources = build_paged_sources(config.sources, client)
        stats = self._stats(campaign)
        started = time.monotonic()
        last_print = 0.0
        self.store.set_status(
            campaign.id, "running", clear_request=True, stats=self._public_stats(stats, started)
        )
        self.store.event(campaign.id, "campaign_started", "Campaign execution started")

        try:
            for query in config.queries:
                for source in sources:
                    try:
                        reason, last_print = self._run_source_query(
                            campaign, source, query, catalog, stats, started, last_print
                        )
                    except (requests.RequestException, ValueError, KeyError, OSError) as exc:
                        stats["errors"] += 1
                        self.store.event(
                            campaign.id,
                            "partition_failed",
                            str(exc),
                            level="error",
                            source=source.name,
                            query=query,
                        )
                        LOG.error(
                            "partition failed source=%s query=%r: %s", source.name, query, exc
                        )
                        # The checkpoint is deliberately not advanced. A later resume
                        # retries the same page while the campaign continues with other
                        # independent source/query partitions.
                        continue
                    if reason:
                        public = self._public_stats(stats, started)
                        if reason == "pause_requested":
                            self.store.set_status(
                                campaign.id, "paused", clear_request=True, stats=public
                            )
                        else:
                            self.store.set_status(
                                campaign.id, "stopped", clear_request=True, stats=public
                            )
                        self.store.event(
                            campaign.id,
                            "campaign_interrupted",
                            f"Campaign stopped at a safe page checkpoint: {reason}",
                            payload={"reason": reason},
                        )
                        return self.store.get(campaign.id)

            keys = self.store.record_keys(campaign.id)
            records = load_records(output / "catalog.sqlite3", keys)
            export_catalog(records, output)
            public = self._public_stats(stats, started)
            final_status = "completed_with_errors" if stats["errors"] else "completed"
            self.store.set_status(campaign.id, final_status, clear_request=True, stats=public)
            self.store.event(
                campaign.id,
                "campaign_completed",
                (
                    "Configured partitions finished with recoverable errors"
                    if stats["errors"]
                    else "All configured source/query partitions were exhausted"
                ),
                level="warning" if stats["errors"] else "info",
                payload=public,
            )
            return self.store.get(campaign.id)
        except KeyboardInterrupt:
            public = self._public_stats(stats, started)
            self.store.set_status(campaign.id, "paused", clear_request=True, stats=public)
            self.store.event(
                campaign.id,
                "campaign_paused",
                "SIGINT received; paused at the last committed page checkpoint",
            )
            return self.store.get(campaign.id)
        except (requests.RequestException, ValueError, KeyError, OSError) as exc:
            stats["errors"] += 1
            public = self._public_stats(stats, started)
            self.store.set_status(campaign.id, "failed", error=str(exc), stats=public)
            self.store.event(
                campaign.id,
                "campaign_failed",
                str(exc),
                level="error",
            )
            raise
        finally:
            catalog.close()

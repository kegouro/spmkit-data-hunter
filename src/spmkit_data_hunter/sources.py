"""Paged source adapters for long-running, resumable discovery campaigns."""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from typing import Protocol
from urllib.parse import parse_qs, urlparse

import requests

from .legacy import (
    FIGSHARE_API,
    ZENODO_API,
    DatasetRecord,
    FigshareSource,
    HttpClient,
    Source,
    ZenodoSource,
    normalize_identifier,
    score_record,
    strip_html,
)

DATACITE_API = "https://api.datacite.org/dois"


@dataclass(slots=True)
class SearchPage:
    """A serializable unit of source progress.

    ``next_cursor`` is the cursor to persist *after* every record from this page
    has been committed. ``None`` means the partition is exhausted.
    """

    records: list[DatasetRecord]
    cursor_used: str | None
    next_cursor: str | None
    page_number: int
    total_hint: int | None = None

    @property
    def exhausted(self) -> bool:
        return self.next_cursor is None


class PagedSource(Protocol):
    name: str
    page_size_default: int

    def iter_pages(
        self,
        query: str,
        *,
        cursor: str | None = None,
        page_size: int | None = None,
    ) -> Iterator[SearchPage]: ...


class PagedZenodoSource(ZenodoSource):
    """Zenodo adapter with explicit page checkpoints."""

    page_size_default = 25

    def iter_pages(
        self,
        query: str,
        *,
        cursor: str | None = None,
        page_size: int | None = None,
    ) -> Iterator[SearchPage]:
        page = max(1, int(cursor or "1"))
        size = max(1, min(page_size or self.page_size_default, 100))
        search_query = f"({query}) AND access_right:open"

        while True:
            payload = self.client.get_json(
                ZENODO_API,
                params={
                    "q": search_query,
                    "size": size,
                    "page": page,
                    "sort": "bestmatch",
                    "all_versions": "false",
                },
            )
            if isinstance(payload, list):
                hits = payload
                total_hint = None
            else:
                hits_container = payload.get("hits") or {}
                hits = hits_container.get("hits") or []
                total_raw = hits_container.get("total")
                if isinstance(total_raw, dict):
                    total_raw = total_raw.get("value")
                try:
                    total_hint = int(total_raw) if total_raw is not None else None
                except (TypeError, ValueError):
                    total_hint = None

            records = [self._parse_hit(hit, query) for hit in hits]
            next_cursor = str(page + 1) if len(hits) == size else None
            yield SearchPage(
                records=records,
                cursor_used=str(page),
                next_cursor=next_cursor,
                page_number=page,
                total_hint=total_hint,
            )
            if next_cursor is None:
                break
            page += 1


class PagedFigshareSource(FigshareSource):
    """Figshare adapter with explicit page checkpoints and detail hydration."""

    page_size_default = 100

    def iter_pages(
        self,
        query: str,
        *,
        cursor: str | None = None,
        page_size: int | None = None,
    ) -> Iterator[SearchPage]:
        page = max(1, int(cursor or "1"))
        size = max(1, min(page_size or self.page_size_default, 1000))

        while True:
            payload = {
                "search_for": query,
                "item_type": 3,
                "page": page,
                "page_size": size,
                "order": "published_date",
                "order_direction": "desc",
            }
            items = self.client.post_json(f"{FIGSHARE_API}/articles/search", payload)
            if not isinstance(items, list):
                raise ValueError("Figshare search response was not a list")

            records: list[DatasetRecord] = []
            for item in items:
                article_id = item.get("id") if isinstance(item, dict) else None
                if article_id is None:
                    continue
                try:
                    detail = self.client.get_json(f"{FIGSHARE_API}/articles/{article_id}")
                    records.append(self._parse_detail(detail, query))
                except (requests.RequestException, ValueError, KeyError):
                    # A single malformed/unavailable record must not discard the page.
                    continue

            next_cursor = str(page + 1) if len(items) == size else None
            yield SearchPage(
                records=records,
                cursor_used=str(page),
                next_cursor=next_cursor,
                page_number=page,
                total_hint=None,
            )
            if next_cursor is None:
                break
            page += 1


def _first_text(values: object, key: str) -> str:
    if not isinstance(values, list):
        return ""
    for item in values:
        if isinstance(item, dict) and item.get(key):
            return strip_html(item[key])
    return ""


def _cursor_from_link(url: str | None) -> str | None:
    if not url:
        return None
    values = parse_qs(urlparse(url).query).get("page[cursor]")
    return values[0] if values else None


class DataCiteSource(Source):
    """Metadata discovery through DataCite.

    DataCite is a meta-index. Records discovered here may not expose file URLs;
    they remain useful for DOI, repository and relation discovery and must not be
    misrepresented as fully hydrated benchmark packages.
    """

    name = "datacite"
    page_size_default = 100

    def _parse_item(self, item: dict[str, object], query: str) -> DatasetRecord:
        attributes = item.get("attributes") or {}
        if not isinstance(attributes, dict):
            attributes = {}

        title = _first_text(attributes.get("titles"), "title") or "Sin título"
        description = _first_text(attributes.get("descriptions"), "description")

        creators: list[str] = []
        for creator in attributes.get("creators") or []:
            if isinstance(creator, dict):
                name = creator.get("name")
                if not name:
                    parts = [creator.get("givenName"), creator.get("familyName")]
                    name = " ".join(str(part) for part in parts if part)
                if name:
                    creators.append(strip_html(name))

        keywords: list[str] = []
        for subject in attributes.get("subjects") or []:
            if isinstance(subject, dict) and subject.get("subject"):
                keywords.append(strip_html(subject["subject"]))

        related: list[dict[str, str]] = []
        for relation in attributes.get("relatedIdentifiers") or []:
            if not isinstance(relation, dict):
                continue
            identifier = normalize_identifier(relation.get("relatedIdentifier"))
            if not identifier:
                continue
            related.append(
                {
                    "identifier": identifier,
                    "relation": normalize_identifier(relation.get("relationType")),
                    "scheme": normalize_identifier(relation.get("relatedIdentifierType")),
                }
            )

        license_value = ""
        rights = attributes.get("rightsList") or []
        if isinstance(rights, list) and rights:
            first = rights[0]
            if isinstance(first, dict):
                license_value = str(
                    first.get("rightsIdentifier")
                    or first.get("rights")
                    or first.get("rightsUri")
                    or ""
                )

        doi = str(attributes.get("doi") or item.get("id") or "")
        landing_url = str(attributes.get("url") or (f"https://doi.org/{doi}" if doi else ""))
        dates = attributes.get("dates") or []
        published = ""
        if isinstance(dates, list):
            for date in dates:
                if isinstance(date, dict) and date.get("date"):
                    published = str(date["date"])
                    if str(date.get("dateType", "")).casefold() in {"issued", "created"}:
                        break

        record = DatasetRecord(
            source=self.name,
            source_id=str(item.get("id") or doi),
            title=title,
            description=description,
            doi=doi,
            landing_url=landing_url,
            license=license_value,
            published=published
            or str(attributes.get("published") or attributes.get("created") or ""),
            modified=str(attributes.get("updated") or ""),
            creators=creators,
            keywords=keywords,
            related_identifiers=related,
            files=[],
            matched_query=query,
        )
        return score_record(record)

    def iter_pages(
        self,
        query: str,
        *,
        cursor: str | None = None,
        page_size: int | None = None,
    ) -> Iterator[SearchPage]:
        current_cursor = cursor or "1"
        size = max(1, min(page_size or self.page_size_default, 1000))
        page_number = 1

        while True:
            payload = self.client.get_json(
                DATACITE_API,
                params={
                    "query": query,
                    "resource-type-id": "dataset",
                    "page[size]": size,
                    "page[cursor]": current_cursor,
                    "disable-facets": "true",
                },
            )
            if not isinstance(payload, dict):
                raise ValueError("DataCite response was not an object")
            data = payload.get("data") or []
            if not isinstance(data, list):
                raise ValueError("DataCite data field was not a list")
            records = [self._parse_item(item, query) for item in data if isinstance(item, dict)]
            links = payload.get("links") or {}
            next_cursor = _cursor_from_link(links.get("next") if isinstance(links, dict) else None)
            meta = payload.get("meta") or {}
            total_raw = meta.get("total") if isinstance(meta, dict) else None
            try:
                total_hint = int(total_raw) if total_raw is not None else None
            except (TypeError, ValueError):
                total_hint = None

            yield SearchPage(
                records=records,
                cursor_used=current_cursor,
                next_cursor=next_cursor,
                page_number=page_number,
                total_hint=total_hint,
            )
            if not next_cursor or not data:
                break
            current_cursor = next_cursor
            page_number += 1

    def search(self, query: str, limit: int) -> list[DatasetRecord]:
        records: list[DatasetRecord] = []
        for page in self.iter_pages(query):
            records.extend(page.records)
            if limit and len(records) >= limit:
                return records[:limit]
        return records


def build_paged_sources(names: list[str], client: HttpClient) -> list[PagedSource]:
    requested = {name.casefold() for name in names}
    if not requested or "all" in requested:
        requested = {"zenodo", "figshare", "datacite"}

    available: dict[str, PagedSource] = {
        "zenodo": PagedZenodoSource(client),
        "figshare": PagedFigshareSource(client),
        "datacite": DataCiteSource(client),
    }
    unknown = requested.difference(available)
    if unknown:
        raise ValueError(f"Fuentes desconocidas: {', '.join(sorted(unknown))}")
    return [available[name] for name in sorted(requested)]


def source_capabilities() -> list[dict[str, object]]:
    return [
        {
            "name": "zenodo",
            "role": "direct",
            "files": True,
            "checksums": True,
            "resume": "page",
            "authentication": "optional for public discovery",
        },
        {
            "name": "figshare",
            "role": "direct",
            "files": True,
            "checksums": True,
            "resume": "page",
            "authentication": "optional for public discovery",
        },
        {
            "name": "datacite",
            "role": "meta-index",
            "files": False,
            "checksums": False,
            "resume": "cursor",
            "authentication": "not required for public retrieval",
        },
    ]

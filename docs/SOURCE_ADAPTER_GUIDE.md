# Source Adapter Guide

A source adapter is accepted only when it can search, resume, and explain its
coverage.

## Required interface

```python
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
```

`next_cursor` must represent the next unread page. It is persisted only after
all records in the current page are committed.

## Adapter checklist

- Link official API documentation.
- Identify source role.
- Document authentication.
- Document page size and hard caps.
- Document sort stability.
- Preserve stable source IDs.
- Enumerate every file exposed by the record-detail endpoint.
- Preserve checksums and sizes.
- Validate optional and missing fields.
- Add offline fixtures for pagination and errors.
- Add a responsible per-host request rate.
- Avoid scraping HTML when an API exists.

## Meta-index adapters

Meta-indexes such as DataCite may expose a DOI and repository URL without file
metadata. Such records must remain metadata-only until hydrated by a direct
repository adapter.

## Official references

- Zenodo API: https://developers.zenodo.org/
- Figshare API: https://docs.figshare.com/
- DataCite REST API: https://support.datacite.org/docs/api
- OSF API: https://developer.osf.io/

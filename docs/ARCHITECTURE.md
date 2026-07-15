# Architecture

## Current transition

Version 2.2 introduces a package architecture while preserving the historical
single-module API in `spmkit_data_hunter.legacy`.

```text
CLI
├── legacy flag mode
└── campaign subcommands
     ↓
CampaignEngine
     ↓
PagedSource adapters ── HttpClient
     ↓
Catalog + CampaignStore (SQLite)
     ↓
JSON / JSONL / CSV / Markdown exports
```

## Modules

| Module | Responsibility |
|---|---|
| `legacy.py` | Existing models, classification, catalog, downloading, exports, and compatible CLI |
| `sources.py` | Paged/cursor adapters and source capability metadata |
| `campaigns.py` | Campaign configuration, states, checkpoints, events, and SQLite persistence |
| `engine.py` | Safe page-level orchestration, heartbeats, budgets, pause/resume, and exports |
| `catalog_io.py` | Reconstruction of records from the persistent catalog |
| `cli.py` | New command tree and compatibility routing |

## Invariants

1. Cursors advance only after a complete page is committed.
2. The catalog database is the source of truth for records and files.
3. The campaign database is the source of truth for search progress.
4. Export files are replaceable views.
5. A source adapter may fetch and parse, but does not download dataset files.
6. A failed partition is not marked exhausted.
7. Replaying a page is safe because writes are idempotent.

## Known migration debt

The legacy module remains large. Future extraction order:

1. file classification and format registry;
2. domain and utility scoring;
3. catalog repository;
4. download and checksum service;
5. archive inventory;
6. export formatters.

Each extraction must retain compatibility tests.

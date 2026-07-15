# Migration from 2.1 to 2.2

## Installation layout

The former single file `src/spmkit_data_hunter.py` became a package:

```text
src/spmkit_data_hunter/
```

Imports such as the following remain supported:

```python
import spmkit_data_hunter as hunter
hunter.DatasetRecord(...)
```

## CLI compatibility

Flag-only commands are routed to the legacy-compatible CLI:

```bash
spmkit-data-hunter --preset all --limit 0
```

New subcommands use the campaign engine:

```bash
spmkit-data-hunter campaign create deep --preset all --source all
spmkit-data-hunter campaign run deep
```

## Limit semantics

- Old behavior: `--limit 20` by default.
- New legacy behavior: `--limit 0` by default, meaning until source exhaustion.
- Campaign behavior: `--max-records 0` and `--max-runtime 0` mean no
  user-selected functional limit.

## Catalog migration

Opening an existing catalog adds idempotent columns for:

- benchmark and relevance scores;
- domain relevance;
- utility class;
- file verification status and notes.

Back up important catalogs before migration.

## Scoring behavior

Raw-only records no longer qualify as Gold or Silver. They are classified as
`reader_fixture`. Gold and Silver now require distinct raw and processed assets.

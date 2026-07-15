# Engineering audit report for v2.2.0

## Scope

This audit reviewed the uploaded v2.1 repository as a scientific data discovery
and curation tool. It covered architecture, pagination, classification,
persistence, CLI behavior, download safety, documentation, and tests.

## Baseline findings

- The project was implemented as a single module of more than 2,000 lines.
- Zenodo and Figshare searches were controlled by a default limit of 20 results
  per source and query.
- The source contract returned a complete list instead of a resumable page
  stream.
- Long jobs had no durable source/query cursor.
- Raw-only records could receive a strong benchmark label through aggregate
  metadata scoring.
- Filename roles used substring matching, allowing cases such as `drawings.csv`
  to activate `raw`.
- The catalog persisted records and downloads, but not campaign state.
- Tests covered core relevance logic but not campaign resume or source cursors.

## Implemented corrections

### Search depth

- Legacy `--limit 0` now searches until a source is exhausted.
- New paged adapters expose explicit next cursors.
- Campaigns persist source/query checkpoints.
- Budgets are checked between pages to avoid skipping a page tail.

### Architecture

- Converted the installable code into a Python package.
- Preserved the previous API in `legacy.py`.
- Added separate source, campaign, engine, catalog-read, verification, and CLI
  modules.

### Scientific classification

- Added utility classes that describe what evidence can support.
- Raw-only datasets remain reader fixtures and Bronze.
- A single ambiguous file cannot fabricate a raw-plus-processed chain.
- Token-aware matching replaced naive substring rules.

### Operations

- Added create, run, status, list, pause, resume, stop, verify, and export
  campaign commands.
- Added a selective download plan/run workflow.
- Added runtime, record, page, duplicate, file, and error statistics.
- Added remote file reachability and size probes.

### Integrity

- Fixed the User-Agent repository URL.
- Rejected literal private, loopback, link-local, reserved, and metadata-service
  IP destinations.
- Added archive entry count, path traversal signals, encrypted-entry count,
  byte totals, and compression ratio.
- Added explicit acknowledgement for unbounded campaign downloads.

### Documentation

- Replaced the README with a campaign-oriented guide.
- Added the Scientific Data Hunting Bible.
- Added architecture, source-adapter, operations, validation, threat-model,
  roadmap, migration, ADR, and agent guidance.

## Verification performed

```text
pytest: 52 passed
ruff check: passed
ruff format --check: passed
legacy self-test: passed
campaign create/status smoke test: passed
wheel build: passed
```

## Known limitations

- Query partitioning for repository hard caps is specified but not yet
  implemented.
- DataCite discovers metadata but does not hydrate files from every destination
  repository.
- OSF, Dataverse, Dryad, DSpace, and generic InvenioRDM adapters remain roadmap
  work.
- DNS rebinding protection is incomplete; literal unsafe IPs are blocked, but
  hostnames are not pinned to resolved public addresses.
- Remote verification establishes reachability and obvious size problems, not
  full content integrity; full downloads receive local SHA-256 and available
  repository checksum verification.
- Full format detection still relies primarily on filename and metadata clues;
  magic-byte and reader-based inspection remain future work.
- The legacy module still contains substantial responsibilities and should be
  extracted incrementally.

## Verdict

The repository is now suitable as a serious alpha research-software project. It
is not yet an exhaustive world index or an automatic scientific-validation
oracle. Its claims, architecture, and evidence taxonomy are aligned with what it
actually implements.

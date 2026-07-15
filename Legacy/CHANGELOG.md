# Changelog

All notable changes to this project will be documented here.

## [2.1.0] - 2026-07-13

### Added

- Domain relevance gate that separates AFM/SPM detection from benchmark quality scoring.
- `assess_domain_relevance()` function with strong phrases, native extensions, and contextual signal families.
- New `DatasetRecord` fields: `benchmark_score`, `relevance_score`, `domain_relevant`, `relevance_reasons`.
- Idempotent SQLite migration for catalogs from v2.0.0.
- False-positive regression tests for ecological, oceanographic, engineering, and parasitology datasets.
- Positive tests for strong phrases, native formats, KPFM, cantilever mechanics, and contextual signals.
- Relevance vs benchmark separation in CSV, REPORT.md, WHY_THIS_DATASET.md, and terminal output.

### Changed

- `score_record()` now evaluates domain relevance first; irrelevant records are capped at score 39 and can never be Gold or Silver.
- `merge_records()` prefers domain-relevant records over irrelevant ones during deduplication and ranking.
- Ranking sort key includes `domain_relevant` as primary discriminator.
- `calculate_benchmark_score()` extracted from `score_record()` for separation of concerns.
- Self-test expanded with false-positive and native-format assertions.

## [2.0.0] - 2026-07-13

### Added

- Zenodo and Figshare discovery through official APIs.
- Raw/processed/code/documentation/archive classification.
- Gold, Silver, and Bronze benchmark ranking.
- DOI-based deduplication.
- SQLite, JSON, JSONL, CSV, and Markdown reports.
- Resumable downloads.
- Checksum validation.
- Size limits and archive inventory.
- Query presets for major SPM workflows.
- Offline self-test and continuous integration.

### Changed

- Reframed the project from an extension-based downloader into a benchmark curator.

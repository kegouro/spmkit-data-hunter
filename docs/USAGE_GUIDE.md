# SPM-Kit Data Hunter — Usage Guide v2.2.0

**Deep, resumable discovery of public AFM/SPM validation evidence**

Author: José Labarca Baeza | License: MIT | [Repository](https://github.com/kegouro/spmkit-data-hunter)

---

## 1. Introduction

SPM-Kit Data Hunter is a command-line tool that discovers, catalogs, classifies, and selectively downloads public AFM/SPM datasets from scientific repositories. It searches Zenodo, Figshare, and DataCite through official public APIs — not by scraping commercial websites.

Its purpose is to find and organize the evidence chains needed to validate scientific software for atomic force microscopy (AFM) and scanning probe microscopy (SPM). A validation chain requires more than isolated files: it needs native instrument data, processing methods or code, processed outputs, and publication context.

Data Hunter does not declare scientific ground truth. It provides structure, classification, and provenance so that human reviewers can make informed decisions.

**Key design principles:**

- **Discovery is not validation** — a search result is a candidate, not a benchmark.
- **Raw-only datasets are reader fixtures**, not analysis validators.
- **Processed reference values are evidence**, not absolute truth.
- **Scientific review remains necessary** before any validation claim.

> **Note:** Data Hunter is alpha software (v2.2.0). It is under active development. Expect improvements to classification heuristics, source coverage, and format intelligence in future releases.

---

## 2. Installation

**Requirements:** Python 3.11 or later, pip, git.

### 2.1 Clone and set up

```bash
git clone https://github.com/kegouro/spmkit-data-hunter.git
cd spmkit-data-hunter
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

On Windows PowerShell:

```powershell
.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
```

### 2.2 Verify the installation

```bash
spmkit-data-hunter doctor
spmkit-data-hunter sources list
pytest
ruff check .
```

The `doctor` command reports whether optional API tokens are detected (it never prints their values) and lists available source adapters.

### 2.3 Dependencies

| Type | Packages |
|------|----------|
| Runtime | `requests` (HTTP client with retry logic), `tqdm` (progress bars) |
| Development | `pytest` (testing), `ruff` (linting and formatting) |

> **Tip:** Optional API tokens (`ZENODO_TOKEN`, `FIGSHARE_TOKEN`, `GITHUB_TOKEN`) may improve rate limits but are not required for public discovery.

---

## 3. Core Concepts

### 3.1 Evidence Chains

Data Hunter scores records by the completeness of their evidence chain:

```
native instrument data  →  processing method or code  →  processed output  →  publication
```

Each link contributes to the benchmark score. A file alone tests a reader; a full chain enables validation.

### 3.2 Domain Relevance Gate

Before scoring, every record passes through a deterministic, offline domain relevance check. It detects AFM/SPM signals through:

- **Strong phrases:** "atomic force microscopy", "scanning probe microscopy", "KPFM", etc.
- **Acronyms:** AFM, SPM, KPFM, MFM, EFM, STM.
- **Contextual families:** cantilever mechanics, topography, SPM software, force spectroscopy, scanning modalities.
- **Native file extensions:** `.nid`, `.gwy`, `.jpk`, `.jpk-force`, `.spm`, `.ibw`, `.sxm`, `.mdt`, `.sm4`, etc.

Records that fail the gate receive capped scores and cannot be Gold or Silver.

### 3.3 Utility Classes

Every record receives one of **seven utility classes**. This is the most important classification — it tells you what the record can actually support.

| Class | Criteria | Valid Use |
|---|---|---|
| `benchmark_ready` | Distinct raw + processed assets + method/code | Analysis validation candidate (requires human review) |
| `crosscheck_candidate` | Distinct raw + processed, incomplete method/code | Preliminary comparison, manual follow-up |
| `reader_fixture` | Raw/native data, no processed reference | Reader, parser, channel, robustness tests |
| `processed_reference_only` | Processed output, no recoverable raw input | Numerical context, format examples |
| `documentation_only` | Paper, protocol, script without usable data | Query expansion, provenance discovery |
| `incomplete` | Insufficient or ambiguous evidence | Manual triage, query refinement |
| `rejected` | Corrupt, empty, unsafe, irrelevant, inaccessible | None without resolving the rejection reason |

### 3.4 Heuristic Levels: Gold, Silver, Bronze

Gold, Silver, and Bronze are compact convenience labels that combine benchmark score with utility class. They are **NOT** declarations of scientific truth. Prefer the utility class for decision-making.

| Level | Rule |
|---|---|
| **Gold** | Utility class is `benchmark_ready` AND benchmark score ≥ 72 |
| **Silver** | Utility class is `benchmark_ready` or `crosscheck_candidate` AND score ≥ 48 |
| **Bronze** | Everything else that passes the domain gate, plus all records that fail the gate |

### 3.5 Benchmark Score (0–100)

The benchmark score evaluates evidence-chain completeness:

| Signal | Points |
|---|---|
| Raw data detected | +32 |
| Processed outputs detected | +24 |
| Code or notebooks detected | +18 |
| Documentation or methods detected | +10 |
| Archive files present | +4 |
| Text mentions raw/original data | +5 |
| Text mentions results or processing | +5 |
| Method or calibration signals | +8 |
| Has DOI | +4 |
| Links to related resources | +5 |
| Recognizable open license | +4 |
| No raw data detected | −18 |
| Images/documents only | −15 |
| No public files | −30 |
| Complete chain bonus (4+ categories) | +5 |

### 3.6 File Categories

Files are classified by extension with token-aware name analysis (word boundaries prevent substring traps like `drawings.csv` matching "raw"):

| Category | Example Extensions |
|---|---|
| `raw` | `.nid` `.gwy` `.jpk` `.jpk-force` `.spm` `.ibw` `.sxm` `.mdt` `.sm4` |
| `processed` | `.csv` `.tsv` `.xlsx` `.json` `.tif` `.h5` `.npy` `.npz` `.mat` |
| `code` | `.py` `.ipynb` `.m` `.r` `.jl` `.cpp` `.sh` `.toml` |
| `documentation` | `.md` `.pdf` `.tex` `.rst` `.docx` `.html` |
| `image` | `.png` `.jpg` `.svg` `.bmp` `.webp` |
| `archive` | `.zip` `.tar.gz` `.tar.bz2` `.tar.xz` `.7z` `.rar` |

---

## 4. Command Reference

The CLI has two modes: the **new subcommand tree** (campaign, download, doctor, sources) and the **legacy flag-only mode**. The new mode is recommended for all work.

### 4.1 Global Entry Point

```
spmkit-data-hunter [command]
  --version    Print version and exit
  --help       Print help and exit
```

### 4.2 `doctor` — Inspect Installation

```bash
spmkit-data-hunter doctor [--json]
```

Reports Python version, platform, user agent, detected API tokens (presence only, never values), and available source adapters.

### 4.3 `sources list` — List Source Adapters

```bash
spmkit-data-hunter sources list
```

Prints JSON with source name, role (direct or meta-index), file inventory support, checksum support, resume strategy, and authentication requirements.

### 4.4 `campaign` — Resumable Discovery Campaigns

Campaigns persist progress in SQLite. They survive interruptions, can be paused/resumed/stopped, and export results to multiple formats.

#### 4.4.1 `campaign create` — Define a Campaign

```bash
spmkit-data-hunter campaign create <name>
  --output <path>               Output directory (default: ./spm_benchmarks)
  --source <name>               Source adapter (repeatable: zenodo, figshare, datacite, all)
  --preset <name>               Query preset (repeatable: all, topography, force, kpfm, grains, resonance)
  --query <text>                Custom query (repeatable)
  --page-size <n>               Records per page (default: 100)
  --max-runtime <duration>      Time budget: 0=unlimited, 1h, 30m, 3600 (seconds)
  --max-records <n>             Record budget: 0=unlimited
  --heartbeat <n>               Heartbeat interval in seconds (default: 15)
  --min-score <n>               Minimum score filter (default: 0)
  --require-open-license        Only include records with open licenses
  --rate-seconds <n>            Delay between API calls per host (default: 1.05)
  --timeout <n>                 HTTP timeout in seconds (default: 45.0)
```

The configuration is frozen at creation time. To change parameters, create a new campaign.

#### 4.4.2 `campaign run` — Execute a Campaign

```bash
spmkit-data-hunter campaign run <name> [--output <path>]
```

Runs a previously created campaign. Stops when budgets are reached or sources are exhausted. Can be interrupted with `Ctrl+C` (equivalent to pause).

#### 4.4.3 `campaign resume` — Continue a Campaign

```bash
spmkit-data-hunter campaign resume <name> [--output <path>]
```

Resumes from the last committed page checkpoint. Replayed pages are safe because catalog writes are idempotent.

#### 4.4.4 `campaign status` — Inspect a Campaign

```bash
spmkit-data-hunter campaign status <name> [--output <path>]
```

Prints campaign metadata, status, configuration, and live statistics.

#### 4.4.5 `campaign list` — List All Campaigns

```bash
spmkit-data-hunter campaign list [--output <path>]
```

Shows all campaigns with slug, status, records seen, and unique records.

#### 4.4.6 `campaign pause` / `campaign stop` — Request Interruption

```bash
spmkit-data-hunter campaign pause <name>
spmkit-data-hunter campaign stop <name>
```

Requests a graceful interruption at the next safe page checkpoint. `Ctrl+C` during a run is equivalent to pause.

#### 4.4.7 `campaign verify` — Probe Remote Files

```bash
spmkit-data-hunter campaign verify <name>
  --max-files <n>               Limit number of files to probe
  --rate-seconds <n>            Delay between probes
  --timeout <n>                 HTTP timeout
```

Uses HEAD requests (falling back to one-byte range) to check reachability of every remote file in the campaign. Flags inaccessible, empty, redirected, and size-mismatched entries. Does **not** download file contents.

#### 4.4.8 `campaign export` — Export Campaign Catalog

```bash
spmkit-data-hunter campaign export <name>
  --output <path>               Campaign output directory
  --target <path>               Export destination (defaults to --output)
```

Exports all records in the campaign to JSON, JSONL, CSV, and Markdown files.

> **Warning:** A campaign checkpoint advances only after the entire page is committed. This makes checkpoints exact and pages replayable. A failed API partition is **never** marked exhausted — it retries on the next resume.

### 4.5 `download` — Plan and Execute Selective Downloads

Discovery and download are deliberately separate. You discover first, then decide what to download.

#### 4.5.1 `download plan` — Preview Without Downloading

```bash
spmkit-data-hunter download plan <campaign-name>
  --output <path>               Campaign output directory
  --level <gold|silver|bronze>  Filter by level (repeatable)
  --category <name>             Filter by file category (repeatable)
```

Reports record count, file count, known size in GiB, and count of files with unknown sizes. Nothing is downloaded.

#### 4.5.2 `download run` — Execute Downloads

```bash
spmkit-data-hunter download run <campaign-name>
  --output <path>               Campaign output directory
  --level <gold|silver|bronze>  Filter by level (repeatable)
  --category <name>             Filter by category (repeatable)
  --max-file-gb <n>             Per-file size limit (default: 2.0)
  --max-record-gb <n>           Per-record total size limit (default: 10.0)
  --accept-unbounded-downloads  Allow unlimited sizes (safety acknowledgment)
  --inspect-archives            List archive contents without extraction
  --rate-seconds <n>            Delay between downloads (default: 1.05)
  --timeout <n>                 HTTP timeout (default: 120.0)
```

Setting both `--max-file-gb` and `--max-record-gb` to `0` with `--accept-unbounded-downloads` disables user-selected size ceilings. Integrity and security checks are never disabled.

Downloads are resumable: already-downloaded files with matching checksums are skipped. Repository checksums (MD5 from Zenodo/Figshare) and local SHA-256 are recorded.

> **Warning:** Unbounded downloads require `--accept-unbounded-downloads`. This is a deliberate safety acknowledgment, not a scientific filter. Without it, setting both size limits to `0` will produce an error.

---

## 5. Campaign Workflow — Step by Step

### Step 1: Create a Campaign

```bash
spmkit-data-hunter campaign create afm-scan \
  --preset all \
  --source all \
  --max-runtime 2h \
  --max-records 0 \
  --output spm_benchmarks
```

### Step 2: Run the Campaign

```bash
spmkit-data-hunter campaign run afm-scan --output spm_benchmarks
```

Watch the heartbeat output: it reports source, page, records seen, new unique records, duplicates, files, errors, and runtime.

### Step 3: Check Progress (from another terminal)

```bash
spmkit-data-hunter campaign status afm-scan
spmkit-data-hunter campaign list
```

### Step 4: Pause, Resume, or Stop

```bash
spmkit-data-hunter campaign pause afm-scan     # graceful pause between pages
spmkit-data-hunter campaign resume afm-scan    # continue from last checkpoint
spmkit-data-hunter campaign stop afm-scan      # graceful stop between pages
```

`Ctrl+C` in the running terminal also triggers a pause.

### Step 5: Verify Remote File Reachability

```bash
spmkit-data-hunter campaign verify afm-scan
```

### Step 6: Export Results

```bash
spmkit-data-hunter campaign export afm-scan
```

### Step 7: Plan Downloads

```bash
spmkit-data-hunter download plan afm-scan \
  --level gold silver \
  --category raw processed
```

### Step 8: Execute Downloads

```bash
spmkit-data-hunter download run afm-scan \
  --level gold silver \
  --category raw processed code \
  --max-file-gb 2 \
  --max-record-gb 20 \
  --inspect-archives
```

### Campaign Lifecycle Statuses

A campaign moves through these statuses during its lifetime:

`created` → `running` → `completed` / `completed_with_errors` / `stopped` / `paused` / `failed`

| Status | Meaning |
|---|---|
| `created` | Configuration frozen, not yet executed |
| `running` | Actively searching and persisting |
| `paused` | Interrupted via Ctrl+C or pause request |
| `stopped` | Interrupted via stop request |
| `completed` | All configured source/query partitions exhausted |
| `completed_with_errors` | All partitions exhausted, some had recoverable errors |
| `failed` | Unrecoverable error (e.g., disk full, catalog corruption) |

> **Tip:** A campaign can be resumed from `paused` or `stopped`. Checkpoints are page-granular: each page checkpoint records the next cursor and whether the partition is exhausted. A resumed campaign skips exhausted partitions and retries failed ones.

---

## 6. Query Presets

Presets are curated query sets targeting specific AFM/SPM modalities. They can be combined and extended with custom queries.

| Preset | Scope | Queries |
|---|---|---|
| `all` | Broad AFM/SPM discovery across modalities | 8 |
| `topography` | Height maps, profiles, roughness, Gwyddion comparisons | 4 |
| `force` | Force curves, calibration, adhesion, modulus, WLC/FJC | 4 |
| `kpfm` | Surface potential, Kelvin probe datasets | 3 |
| `grains` | Segmentation, particles, grain analysis | 3 |
| `resonance` | Cantilever thermal tune, resonance fitting | 3 |

**Usage examples:**

```bash
# Single preset
spmkit-data-hunter campaign create fc --preset force --source all

# Combine presets
spmkit-data-hunter campaign create multi --preset force --preset kpfm --source all

# Presets + custom queries
spmkit-data-hunter campaign create custom \
  --preset force \
  --query "single molecule force spectroscopy raw processed" \
  --query "JPK force curve analysis notebook" \
  --source all
```

Custom queries are appended to preset queries and deduplicated. If no preset or custom query is provided, the `all` preset is used.

---

## 7. Data Sources

Each source adapter follows strict rules: cursors advance only after full page commit; failed partitions are never marked exhausted; replaying a page is safe (idempotent writes); source adapters fetch metadata only, never download dataset files directly.

| Source | API | Role | File Inventory | Checksums | Resume | Auth |
|---|---|---|---|---|---|---|
| Zenodo | `api.zenodo.org` | Direct repository | Yes | Yes (MD5) | Page | Optional |
| Figshare | `api.figshare.com/v2` | Direct repository | Yes | Yes (MD5) | Page | Optional |
| DataCite | `api.datacite.org` | Metadata index | Usually no | No | Cursor | Not required |

DataCite records are valuable for DOI discovery and publication linkage but typically lack file inventories — they are metadata evidence, not benchmark packages.

**Planned adapters** for future releases: OSF, Dataverse, Dryad, InvenioRDM, DSpace 7.

---

## 8. Output Structure

All output lands in the directory specified by `--output` (default: `./spm_benchmarks`).

```
spm_benchmarks/
├── catalog.sqlite3           # Normalized records, file inventories, scores
├── campaigns.sqlite3          # Campaign configs, checkpoints, events, stats
├── catalog.json               # JSON export of all campaign records
├── catalog.jsonl              # JSON Lines export (one record per line)
├── catalog.csv                # CSV export
├── REPORT.md                  # Human-readable Markdown report
└── datasets/                  # Downloaded files organized by record
```

- **`catalog.sqlite3`** — source of truth for discovered records and their file inventories.
- **`campaigns.sqlite3`** — source of truth for campaign state (campaigns, checkpoints, campaign_records linking table, events audit log).
- **Export files** — views that can be regenerated at any time with `campaign export`. Delete them freely; the catalog database is the canonical source.
- Both databases use **WAL journal mode**. To safely copy: stop the process first, then copy the main `.sqlite3` file together with its `-wal` and `-shm` companion files.

> **Tip:** The `REPORT.md` file includes a summary of records by level, utility class distribution, and per-record details with file listings.

---

## 9. Validation Philosophy

This section is essential reading before using discovered data for scientific validation.

### Discovery is not validation

A search result, a DOI, a downloaded file — none of these is a benchmark. They are candidates. A human must verify: instrument and acquisition conditions, calibration parameters, method, units, conventions, and software versions.

### Raw-only files are reader fixtures

A pristine `.nid` or `.gwy` file can test that a reader correctly parses channels, handles orientation, and survives edge cases. It **cannot** demonstrate that a roughness algorithm, force-curve fit, or physical model produces correct results.

### Processed values are references, not absolute truth

A CSV of roughness values from another laboratory is evidence — not a golden answer. Without documented units, calibration, filtering parameters, and software version, it is a weak reference at best.

### Gwyddion as a reference

Gwyddion can serve as an independent reference for many image-processing operations when version, units, parameters, and operation order are recorded. It is **not** a universal oracle for force-spectroscopy models or proprietary instrument metadata.

### What Data Hunter guarantees

| Does guarantee | Does NOT guarantee |
|---|---|
| Structured discovery of public AFM/SPM material | Scientific correctness certification |
| Classification of what each record contains | Automated benchmark validation |
| Provenance linking to DOIs and publications | Ground truth declarations |
| File reachability verification | — |

Read the full doctrine in **[SCIENTIFIC_DATA_HUNTING_BIBLE.md](SCIENTIFIC_DATA_HUNTING_BIBLE.md)**.

> **Warning:** Before reusing a dataset: (1) read its license, (2) cite the version DOI, (3) do not redistribute restricted files, (4) preserve checksums and provenance, (5) record processing parameters, (6) ask an AFM/SPM practitioner to review instrument-specific assumptions.

---

## 10. Development

### Setup

```bash
pip install -e ".[dev]"
```

### Run Tests (53 tests)

```bash
pytest
```

Tests cover: file classification, DOI/URL normalization, scoring, domain relevance gate, utility classification, campaign creation and checkpoint lifecycle, pause/resume semantics, DataCite adapter, pagination edge cases, and download planning.

### Lint and Format

```bash
ruff check .
ruff format --check .
```

### Legacy Self-Test (no network required)

```bash
spmkit-data-hunter --self-test
```

### Project Structure

```
src/spmkit_data_hunter/
├── __init__.py          # Package exports
├── __main__.py           # python -m entry point
├── cli.py                # Unified command-line interface
├── campaigns.py          # Campaign model and SQLite store
├── catalog_io.py         # Record reconstruction from catalog
├── engine.py             # Campaign execution orchestration
├── legacy.py             # Models, classification, scoring, downloads, exports
├── sources.py            # Paged source adapters (Zenodo, Figshare, DataCite)
├── verification.py       # Lightweight remote file probes
└── version.py            # Version string
```

Every real false positive or API edge case should become a regression test.

> **Note:** See `CONTRIBUTING.md` for guidelines on adding source adapters and the required PR checklist.

---

## 11. Troubleshooting

| Problem | Solution |
|---|---|
| Campaign won't start | Check it was created (`campaign list`), verify output directory exists and is writable, run `doctor`. |
| "Unbounded downloads require --accept-unbounded-downloads" | This is a safety gate. Pass `--accept-unbounded-downloads` to confirm. |
| Network errors during campaign | The engine catches exceptions per partition and continues. Failed partitions retry on resume. |
| Campaign appears stuck | Check heartbeat (`campaign status`). Reduce `--rate-seconds` for faster API calls. Empty pages are normal for exhaustive search. |
| Downloaded files corrupted | Check checksums in catalog. Delete the file and re-download. Already-downloaded files are skipped. |
| SQLite database locked | Ensure only one process runs per output directory. Busy timeout is 30 seconds. WAL recovery is automatic. |

**Inspecting campaign events directly:**

```bash
sqlite3 spm_benchmarks/campaigns.sqlite3 \
  "SELECT timestamp, level, event_type, message FROM events ORDER BY id DESC LIMIT 20;"
```

---

## 12. Relationship to SPM-Kit

SPM-Kit Data Hunter is a companion project for [SPM-Kit](https://github.com/kegouro/spmkit), an open-source AFM/SPM analysis toolkit.

- **SPM-Kit** performs AFM analysis: loading native formats, processing images, fitting force curves, extracting features.
- **Data Hunter** discovers and curates public material for reader tests, cross-checks, and validation manifests.
- Data Hunter does **not** perform AFM analysis. SPM-Kit does **not** perform dataset discovery.

Together, they aim to make AFM/SPM software validation more reproducible, transparent, and data-driven.

**Future integration (roadmap v2.5):** SPM-Kit validation manifests referencing Data Hunter catalog records, versioned tolerance and parameter records, curated public benchmark index with human-reviewed entries.

---

## Appendix A: Quick Reference Card

**Create and run:**
```bash
spmkit-data-hunter campaign create <name> --preset all --source all --max-runtime 2h --max-records 0
spmkit-data-hunter campaign run <name>
```

**Manage:**
```bash
spmkit-data-hunter campaign status <name>
spmkit-data-hunter campaign list
spmkit-data-hunter campaign pause <name>
spmkit-data-hunter campaign resume <name>
spmkit-data-hunter campaign stop <name>
```

**Verify and export:**
```bash
spmkit-data-hunter campaign verify <name>
spmkit-data-hunter campaign export <name>
```

**Download:**
```bash
spmkit-data-hunter download plan <name> --level gold silver
spmkit-data-hunter download run <name> --level gold --category raw processed
```

**Inspect:**
```bash
spmkit-data-hunter doctor
spmkit-data-hunter sources list
```

**Legacy:**
```bash
spmkit-data-hunter --preset force --source all --limit 0 --top 50
spmkit-data-hunter --self-test
```

---

## Appendix B: Environment Variables

Run `spmkit-data-hunter doctor` to see which tokens are detected. Values are never printed.

| Variable | Purpose | Required? |
|---|---|---|
| `GITHUB_TOKEN` | GitHub API authentication | No |
| `ZENODO_TOKEN` | Zenodo API authentication | No |
| `FIGSHARE_TOKEN` | Figshare API authentication | No |
| `OSF_TOKEN` | OSF API (future adapter) | No |
| `DATAVERSE_TOKEN` | Dataverse API (future adapter) | No |
| `DRYAD_TOKEN` | Dryad API (future adapter) | No |
| `OPENALEX_API_KEY` | OpenAlex API (future) | No |
| `CROSSREF_MAILTO` | Crossref polite pool email | No |

---

## Appendix C: Verification Status Codes

| Status | Meaning |
|---|---|
| `not_checked` | Default; no probe attempted |
| `reachable` | Remote object responded to HEAD or range request |
| `rejected_url` | URL is not an allowed public HTTPS URL |
| `rejected_redirect` | Redirect resolved to a disallowed destination |
| `empty` | Remote object reports zero bytes |
| `size_mismatch` | Repository metadata size differs from remote size |
| `failed` | Request failed (timeout, DNS, connection refused, etc.) |

---

*SPM-Kit Data Hunter v2.2.0 — MIT License — Repository: https://github.com/kegouro/spmkit-data-hunter*

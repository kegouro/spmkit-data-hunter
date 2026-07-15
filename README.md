# SPM-Kit Data Hunter

[![CI](https://github.com/kegouro/spmkit-data-hunter/actions/workflows/ci.yml/badge.svg)](https://github.com/kegouro/spmkit-data-hunter/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org/)

**SPM-Kit Data Hunter** discovers, inventories, ranks, and selectively downloads
public AFM/SPM evidence for scientific software validation.

It searches for more than isolated microscopy files. The target is a traceable
chain:

> native instrument data → method or code → processed result → publication

Data Hunter uses public repository APIs. It is not a commercial-site scraper,
and it does not claim that a high score establishes scientific ground truth.

## Why this exists

AFM/SPM validation material is fragmented across repositories, supplementary
files, instrument-specific formats, papers, scripts, and processed exports. A
raw file may test a reader but cannot by itself validate a roughness algorithm,
force-curve fit, or physical model.

Data Hunter preserves those distinctions and records what each dataset can
actually support.

## Scientific utility classes

| Utility class | Meaning |
|---|---|
| `benchmark_ready` | Distinct raw and processed/reference assets plus method or code evidence |
| `crosscheck_candidate` | Raw and processed/reference assets, but incomplete method/code context |
| `reader_fixture` | Native/raw file useful for I/O and robustness testing, without an independent processed reference |
| `processed_reference_only` | Processed output or reported values without recoverable raw input |
| `documentation_only` | Paper, method, script, or README without usable data assets |
| `incomplete` | Evidence is insufficient or ambiguous |
| `rejected` | Empty, corrupt, unsafe, irrelevant, inaccessible, or unusable for the intended workflow |

Gold, Silver, and Bronze remain compact heuristic labels. They are secondary to
the utility class.

## Features

- Deep, resumable campaigns with durable SQLite checkpoints.
- Searches Zenodo and Figshare through public APIs.
- Uses DataCite as a metadata discovery index.
- No hidden 20/25/30-record campaign limit.
- Run by time, record budget, or until configured partitions are exhausted.
- Safe pause with `Ctrl+C` or a second terminal.
- Persistent heartbeat, page, record, duplicate, file, and error counters.
- Enumerates every file exposed by direct repository records.
- Token-aware filename classification that avoids substring traps such as
  `drawings.csv → raw`.
- Distinguishes raw-only reader fixtures from analysis benchmarks.
- Persistent catalog with JSON, JSONL, CSV, Markdown, and SQLite outputs.
- Selective, resumable downloads with repository checksum support and local SHA-256.
- Archive inventory without extraction.
- Backward-compatible flag-only CLI.
- Offline tests for classification, pagination, cursor resume, campaigns,
  migration, and pause semantics.

## Installation

```bash
git clone https://github.com/kegouro/spmkit-data-hunter.git
cd spmkit-data-hunter
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install --upgrade pip
python3 -m pip install -e ".[dev]"
```

Windows PowerShell:

```powershell
.venv\Scripts\Activate.ps1
```

## Inspect the installation

```bash
spmkit-data-hunter doctor
spmkit-data-hunter sources list
python3 -m pytest
python3 -m ruff check .
```

`doctor` reports whether optional credential variables exist, but never prints
their values.

## Recommended workflow: campaigns

### One-hour broad search

```bash
spmkit-data-hunter campaign create afm-one-hour \
  --preset all \
  --source all \
  --max-runtime 1h \
  --max-records 0 \
  --output spm_benchmarks

spmkit-data-hunter campaign run afm-one-hour \
  --output spm_benchmarks
```

The campaign stops at a safe page checkpoint when its runtime budget is reached.
Resume it later:

```bash
spmkit-data-hunter campaign resume afm-one-hour \
  --output spm_benchmarks
```

### Search until exhaustion

```bash
spmkit-data-hunter campaign create afm-deep \
  --preset all \
  --source all \
  --max-runtime 0 \
  --max-records 0

spmkit-data-hunter campaign run afm-deep
```

`0` means no user-selected functional limit. API rate limits, HTTP timeouts,
filesystem limits, path protections, and archive protections still apply.

### Status, pause, and stop

```bash
spmkit-data-hunter campaign status afm-deep
spmkit-data-hunter campaign pause afm-deep
spmkit-data-hunter campaign resume afm-deep
spmkit-data-hunter campaign stop afm-deep
spmkit-data-hunter campaign list
```

A campaign checkpoint advances only after the entire page is committed. Replayed
pages are safe because catalog writes are idempotent.

### Probe remote files without downloading them fully

```bash
spmkit-data-hunter campaign verify afm-deep
```

The verifier uses HEAD or a one-byte range request to detect inaccessible, empty,
redirected, and obvious size-mismatch cases. It does not prove that scientific
content is correct and does not replace checksum verification after download.

### Export a campaign

```bash
spmkit-data-hunter campaign export afm-deep
```

## Download workflow

Discovery and download are deliberately separate.

### Plan first

```bash
spmkit-data-hunter download plan afm-deep \
  --level gold \
  --level silver \
  --category raw \
  --category processed \
  --category documentation
```

The plan reports records, files, known bytes, and files with unknown sizes.

### Download with limits

```bash
spmkit-data-hunter download run afm-deep \
  --level gold \
  --level silver \
  --max-file-gb 4 \
  --max-record-gb 20 \
  --inspect-archives
```

### Explicit unbounded download

```bash
spmkit-data-hunter download run afm-deep \
  --max-file-gb 0 \
  --max-record-gb 0 \
  --accept-unbounded-downloads
```

The acknowledgement disables user-selected size ceilings, not integrity or
security checks.

## Legacy CLI

Existing flag-only commands remain valid. In legacy mode, `--limit 0` now means
search until the source returns no more results.

```bash
spmkit-data-hunter \
  --preset force \
  --source all \
  --limit 0 \
  --top 50
```

For long or interruptible runs, campaigns are strongly preferred because legacy
mode does not persist page checkpoints.

## Query presets

| Preset | Intended use |
|---|---|
| `all` | Broad AFM/SPM discovery |
| `topography` | Height maps, profiles, roughness, and Gwyddion comparisons |
| `force` | Force curves, calibration, adhesion, modulus, WLC/FJC evidence |
| `kpfm` | Surface potential and Kelvin probe datasets |
| `grains` | Segmentation, particles, and grain analysis |
| `resonance` | Cantilever thermal tune and resonance fitting |

Presets can be repeated and combined with custom queries:

```bash
spmkit-data-hunter campaign create custom \
  --preset force \
  --query 'single molecule force spectroscopy raw processed' \
  --query 'JPK force curve analysis notebook'
```

## Supported sources

| Source | Role | File inventory | Checkpoint |
|---|---|---:|---|
| Zenodo | Direct repository | Yes | Page |
| Figshare | Direct repository | Yes | Page |
| DataCite | Metadata index | Usually no | Cursor |

DataCite records are retained as metadata evidence and are not misrepresented as
fully hydrated benchmark packages.

Planned adapters include OSF, Dataverse, Dryad, generic InvenioRDM, and DSpace 7.
See [`docs/ROADMAP.md`](docs/ROADMAP.md).

## Output

```text
spm_benchmarks/
├── catalog.sqlite3
├── campaigns.sqlite3
├── catalog.json
├── catalog.jsonl
├── catalog.csv
├── REPORT.md
└── datasets/
```

- `catalog.sqlite3` stores normalized records and file inventories.
- `campaigns.sqlite3` stores campaign configuration, checkpoints, events, and
  progress.
- Export files are views and can be regenerated.

## Validation philosophy

A raw file alone can validate reader behavior, file parsing, channel presence,
orientation, and robustness. It cannot demonstrate that an analysis algorithm
reproduces an independent result.

Gwyddion can be an excellent independent reference for many image-processing
operations when version, units, parameters, and operation order are recorded.
It should not be treated as an automatic oracle for every force-spectroscopy or
instrument-calibration workflow.

Read the full doctrine in:

### [The Scientific Data Hunting Bible](SCIENTIFIC_DATA_HUNTING_BIBLE.md)

Supporting documents:

- [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md)
- [`docs/VALIDATION_TAXONOMY.md`](docs/VALIDATION_TAXONOMY.md)
- [`docs/SOURCE_ADAPTER_GUIDE.md`](docs/SOURCE_ADAPTER_GUIDE.md)
- [`docs/OPERATIONS.md`](docs/OPERATIONS.md)
- [`docs/THREAT_MODEL.md`](docs/THREAT_MODEL.md)

## Responsible use

Before reusing a dataset:

1. Read its repository metadata and license.
2. Cite the version DOI and related publication.
3. Do not redistribute files when the license forbids it.
4. Preserve checksums and provenance.
5. Record processing parameters used for comparison.
6. Ask an AFM/SPM practitioner to review instrument-specific assumptions.

Never commit downloaded datasets, access tokens, cookies, private laboratory
data, or generated SQLite WAL files.

## Development

```bash
python3 -m pip install -e ".[dev]"
python3 -m pytest
python3 -m ruff check .
python3 -m ruff format --check .
```

Every real false positive or failed API edge case should become a regression
test.

## Relationship to SPM-Kit

Data Hunter is a companion project for
[SPM-Kit](https://github.com/kegouro/spmkit). It discovers and curates public
material that may support reader tests, cross-checks, and future validation
manifests. It does not perform AFM analysis itself.

## Citation

Citation metadata are available in [`CITATION.cff`](CITATION.cff).

## License

MIT. See [`LICENSE`](LICENSE).

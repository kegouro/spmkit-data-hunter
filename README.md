# SPM-Kit Data Hunter

[![CI](https://github.com/kegouro/spmkit-data-hunter/actions/workflows/ci.yml/badge.svg)](https://github.com/kegouro/spmkit-data-hunter/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org/)

**SPM-Kit Data Hunter** discovers, ranks, catalogs, and optionally downloads public AFM/SPM datasets suitable for scientific software validation.

Instead of collecting isolated microscopy files, it searches for **chains of evidence**:

> raw instrument data → processing method or code → processed results → related publication

The project uses official repository APIs and does not scrape commercial websites.

## Why it exists

Scientific validation needs more than a raw file. A useful benchmark should ideally include:

- native AFM/SPM data;
- processed exports or reported numerical results;
- scripts, notebooks, or a documented workflow;
- calibration and method information;
- a DOI, license, and related publication.

Data Hunter detects these signals and ranks candidate records as:

| Level | Meaning |
|---|---|
| **Gold** | Raw data plus processed results and code or documentation |
| **Silver** | Raw data plus at least one strong validation companion |
| **Bronze** | Potentially useful, but incomplete or weakly documented |

The score is a discovery heuristic, not a scientific quality judgment. Every selected dataset should still be reviewed by a domain expert before being used as ground truth.

## Features

- Searches **Zenodo** and **Figshare** through their official APIs.
- Query presets for topography, force spectroscopy, KPFM, grain analysis, and resonance.
- Detects native SPM formats such as `.nid`, `.nhf`, `.gwy`, `.jpk-force`, `.spm`, `.ibw`, `.mtrx`, and `.sxm`.
- Separates files into `raw`, `processed`, `code`, `documentation`, `archive`, and `image`.
- Generates a 0–100 benchmark score and Gold/Silver/Bronze label.
- Deduplicates records by DOI.
- Stores a persistent **SQLite catalog**.
- Exports JSON, JSONL, CSV, and a readable Markdown report.
- Supports resumable downloads with `.part` files.
- Verifies checksums when repositories provide them.
- Applies per-file and per-record size limits.
- Can inventory ZIP and TAR contents without extracting them.
- Includes an offline self-test.

## Installation

### From the repository

```bash
git clone https://github.com/kegouro/spmkit-data-hunter.git
cd spmkit-data-hunter
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install --upgrade pip
python3 -m pip install -e .
```

On Windows PowerShell, activate the environment with:

```powershell
.venv\Scripts\Activate.ps1
```

## Quick start

Run the internal tests:

```bash
spmkit-data-hunter --self-test
```

Discover and rank candidates without downloading anything:

```bash
spmkit-data-hunter --preset all --limit 20 --top 30
```

Search for force-spectroscopy benchmarks:

```bash
spmkit-data-hunter --preset force --limit 30 --top 40
```

Download only Gold and Silver candidates:

```bash
spmkit-data-hunter \
  --preset force \
  --levels gold silver \
  --download \
  --inspect-archives \
  --max-file-mb 1500 \
  --max-record-gb 8
```

Search with custom queries:

```bash
spmkit-data-hunter \
  --query "AFM raw processed data" \
  --query "atomic force microscopy source data analysis script" \
  --source all \
  --top 50
```

Require a recognizable open license:

```bash
spmkit-data-hunter \
  --preset topography \
  --require-open-license
```

## Output

By default, Data Hunter creates `spm_benchmarks/`:

```text
spm_benchmarks/
├── catalog.csv
├── catalog.json
├── catalog.jsonl
├── catalog.sqlite3
├── REPORT.md
└── datasets/
```

`REPORT.md` is the best place to review candidates before enabling downloads.

Each downloaded dataset receives:

```text
dataset_folder/
├── metadata.json
├── WHY_THIS_DATASET.md
├── archive_inventory.json   # when requested and applicable
└── downloaded files
```

## Query presets

| Preset | Intended use |
|---|---|
| `all` | Broad AFM/SPM benchmark discovery |
| `topography` | Height maps, profiles, roughness, Gwyddion comparisons |
| `force` | Force curves, calibration, adhesion, modulus |
| `kpfm` | Surface potential and Kelvin probe datasets |
| `grains` | Segmentation, particle and grain analysis |
| `resonance` | Cantilever thermal tune and resonance fitting |

Presets may be repeated and combined with custom queries.

## Responsible use

Data Hunter searches public APIs and deliberately rate-limits requests. Downloaded data remain subject to each record's license and terms.

Before reusing a dataset:

1. Read the repository metadata and license.
2. Cite the dataset DOI and associated publication.
3. Do not redistribute files whose license forbids redistribution.
4. Treat published processed values as **reference results**, not unquestionable ground truth.
5. Record all processing parameters used in comparisons.
6. Ask an AFM/SPM practitioner to review instrument-specific assumptions.

Never commit downloaded datasets, credentials, API tokens, or private laboratory data to this repository.

## Validation philosophy

The strongest comparison unit is not a single file. It is a reproducible chain:

```text
native input
    ↓
documented preprocessing and calibration
    ↓
reference numerical output
    ↓
SPM-Kit result
    ↓
difference, tolerance, and explanation
```

Differences can arise from a software defect, unequal parameters, format conventions, orientation choices, calibration, or genuinely different numerical methods. Data Hunter helps locate evidence; it does not replace scientific interpretation.

## Development

```bash
python3 -m pip install -e ".[dev]"
python3 -m pytest
python3 -m ruff check .
python3 -m ruff format --check .
```

The CLI also contains its own dependency-light smoke test:

```bash
python3 src/spmkit_data_hunter.py --self-test
```

## Roadmap

- Support additional public repositories through official APIs.
- Inspect supported archive manifests before full dataset download.
- Add optional metadata extraction for papers and supplementary files.
- Export benchmark manifests consumable directly by SPM-Kit tests.
- Add human-reviewed benchmark annotations.
- Track comparison provenance and tolerances.

## Relationship to SPM-Kit

Data Hunter is a companion project for [SPM-Kit](https://github.com/kegouro/spmkit). It does not perform AFM analysis itself. It discovers and organizes public material that may be suitable for validating SPM-Kit readers and analysis functions.

## Citation

Citation metadata are available in [`CITATION.cff`](CITATION.cff).

## License

MIT License. See [`LICENSE`](LICENSE).

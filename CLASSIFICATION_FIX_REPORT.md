# Classification Fix Report — v2.2.1

## 1. What failed

A discovery campaign with `--preset all --source zenodo figshare datacite`
catalogued **9,276 unique records** but the results were severely polluted:

- **1 Gold record**: "Data set for Long-Range Magnetoelectricity in Type-II
  Multiferroic NiI₂" — not AFM/SPM microscopy data. "AFM" likely appears as
  "antiferromagnetic" in the text.
- **Thousands of Bronze records**: Biology, medicine, chemistry, and social
  science papers where "AFM" appears as a casual mention but the actual
  uploaded files are `.docx`, `.xlsx`, `.pdf`, or unrelated data.
- **Real AFM datasets missed**: Records from `contact.engineering` scored
  Bronze with `score=0` because DataCite has no file inventory.

## 2. Root causes

### a) CSRV files classified as "raw data"

`infer_categories()` classified `raw_data.csv` as `{"raw"}`. The benchmark
scorer awarded **+32** for "raw" detection. Medical/biology papers with
`raw_data.csv` files got a massive score boost despite having zero AFM
instrument data.

### b) No distinction between instrument formats and text exports

Vendor formats (`.nid`, `.jpk`, `.spm`, etc.) and generic CSV/TSV/XLSX were
treated identically. A paper with `raw_data.csv`, `results.xlsx`,
`analysis.py`, and `methods.docx` could score 70+ and reach Gold.

### c) Domain gate was permissive with acronym-only matches

"AFM" acronym (+20) + one contextual family (+15) = 35 pts + `independent_families >= 2` = gate passed. But "AFM" is ambiguous (antiferromagnetic, etc.).

### d) DataCite records penalized for having no files

DataCite records (no file inventory) got `-30` for "no files", reducing them
to score=0. Real AFM datasets from `contact.engineering` were buried as
Bronze.

## 3. Changes made

### File: `src/spmkit_data_hunter/legacy.py`

**New constant sets** (lines ~140-245):
- `INSTRUMENT_RAW_EXTENSIONS`: vendor-native formats only (`.nid`, `.jpk`, `.spm`, etc.)
- `DERIVED_RAW_EXTENSIONS`: text/excel exports (`.csv`, `.tsv`, `.xlsx`, etc.)
- `PUBLICATION_ONLY_EXTENSIONS`: documentation formats (`.pdf`, `.docx`, `.tex`, etc.)
- `NEGATIVE_CONTEXT_PATTERNS`: 60+ regex patterns for unrelated domains
  (clinical trials, genomics, ecology, etc.)
- `CONTACT_ENGINEERING_DOMAIN` / `SPMKIT_DOMAIN`: high-confidence source patterns

**Modified `infer_categories()`** (line ~562):
- Vendor formats → `{"raw", "instrument_raw"}`
- Derived exports (.csv/.xlsx) → `{"raw", "derived_raw"}` only if raw signal in name
- Publication formats (.pdf/.docx) → NEVER classified as "raw"

**Modified `assess_domain_relevance()`** (line ~939):
- `contact.engineering` and `spmkit.org` → +70, immediate gate pass
- Native extensions → +70 (was +60)
- Negative context filter: reduces confidence score when unrelated-domain signals detected
- With negative context: requires 2+ strong phrases + 2+ contextual families

**Modified `calculate_benchmark_score()`** (line ~1123):
- `instrument_raw` → +32 (full raw data bonus)
- `derived_raw` → +18 (partial bonus)
- No instrument format penalty: -10 (if any raw detected) or -30 (severe)
- Publication-only penalty: -20 for records with only .docx/.pdf/.png files

**Modified `score_record()`** (line ~1260):
- Gold requires `instrument_raw` files
- Silver requires `instrument_raw`
- DataCite `instrument_data_unknown` records → crosscheck_candidate

**Modified `classify_utility()`** (line ~1300):
- New flags: `likely_false_positive`, `instrument_data_unknown`, `vendor_format_detected`, `only_publication_assets`
- DataCite + strong signals → `crosscheck_candidate` (was `incomplete`)

**New `DatasetRecord` fields** (line ~635):
- `likely_false_positive: bool`
- `instrument_data_unknown: bool`
- `vendor_format_detected: bool`
- `only_publication_assets: bool`

**Schema migration** (line ~1870):
- New columns auto-migrated from v2.1.0/v2.2.0 catalogs

**CSV export** (line ~2345):
- New columns in catalog.csv

### File: `tests/test_campaigns.py`
- Updated DataCite test to accept `crosscheck_candidate` utility class

## 4. New flags / subcategories

| Flag | Meaning | Trigger |
|------|---------|---------|
| `vendor_format_detected` | Contains `.nid`, `.jpk`, `.spm`, etc. | `instrument_raw` in file categories |
| `instrument_data_unknown` | DataCite record, no file inventory, strong AFM signals | source=datacite, 0 files, domain_relevant |
| `likely_false_positive` | Passed gate but has suspicious patterns | negative context + no instrument files; OR only .docx/.pdf/.png |
| `only_publication_assets` | All files are publication/image formats | every file in PUBLICATION_ONLY_EXTENSIONS or IMAGE_EXTENSIONS |

### New file categories

| Category | Meaning | Extensions |
|----------|---------|------------|
| `instrument_raw` | Vendor-native AFM/SPM instrument data | `.nid`, `.jpk`, `.spm`, `.ibw`, `.gwy`, etc. |
| `derived_raw` | Text/table exports claiming to be raw | `.csv`, `.tsv`, `.xlsx`, `.txt`, `.dat`, etc. |
| (no change) `raw` | Generic raw signal (includes both above) | — |

## 5. Validation

### Self-tests (`python3 -m spmkit_data_hunter --self-test`):
- File classification: `instrument_raw`, `derived_raw`, publication exclusion
- Negative context: clinical trial title → rejected
- Gold gate: requires `instrument_raw`, not just CSV "raw"
- DataCite: `instrument_data_unknown` flag, `crosscheck_candidate` utility
- `contact.engineering`: high-confidence source detection

### Test suite (`python3 -m pytest`):
- 53/53 tests pass
- New assertions in self-tests cover negative context, instrument classification,
  DataCite handling, contact.engineering detection.

### Suggested manual testing:
1. Re-run the discovery campaign with the hardened gate
2. Check that the "Table 1_Efficacy of esketamine..." records are now Bronze or
   filtered entirely
3. Verify that `contact.engineering` records score higher
4. Check that the lone Gold record from the original campaign now appears at
   a lower level if it has no instrument files

## 6. Future work

- **contact.engineering direct adapter**: add a source adapter for the
  `contact.engineering` API to hydrate file inventories for DataCite records
- **Archive inspection**: when archives (.zip/.tar) are detected, consider
  inspecting their contents (listing members) to detect instrument files
  inside. Currently archives get a small bonus but their contents are opaque.
- **Query preset refinement**: the "all" preset queries contain broad patterns
  like `"AFM" raw processed data` that pull in many false positives at the
  retrieval stage. Consider removing the acronym-only queries.
- **Whitelist DOI prefixes**: known AFM/SPM repositories could get automatic
  domain relevance even without file inspection (e.g., specific Zenodo
  communities).

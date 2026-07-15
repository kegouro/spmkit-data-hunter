# The Scientific Data Hunting Bible

## A constitution for reproducible, ethical, and technically serious discovery of public AFM/SPM evidence

> **SPM-Kit Data Hunter is not a web vacuum.** It is an evidence-curation system.
>
> Its job is not to collect the largest pile of files. Its job is to build a
> traceable path from a public scientific claim to the data, methods, outputs,
> and provenance needed to test that claim responsibly.

This document is the normative engineering and scientific doctrine of
**SPM-Kit Data Hunter**. It defines what the project means by exhaustive search,
validation evidence, safe downloading, reproducibility, source coverage, and
honest uncertainty.

The words **MUST**, **MUST NOT**, **SHOULD**, **SHOULD NOT**, and **MAY** are used
in the RFC sense. A pull request that violates a MUST needs an explicit
architecture decision record explaining why.

---

## 1. The first principle: discovery is not validation

A search result is not a benchmark. A DOI is not a benchmark. A native AFM file
is not a benchmark. A paper is not a benchmark. A CSV named `results.csv` is not
a benchmark.

A scientific benchmark is a **relationship among evidence**:

```text
native input
    ↓
known instrument and acquisition context
    ↓
documented preprocessing and calibration
    ↓
reference output or independently reported value
    ↓
SPM-Kit output generated with matched assumptions
    ↓
difference, tolerance, and explanation
```

Data Hunter discovers and organizes the material required to build that chain.
It does not declare ground truth by itself.

### 1.1 The project MUST distinguish five questions

1. **Is the record actually about AFM/SPM?**
2. **Does it contain usable data?**
3. **Is the data intact and accessible?**
4. **Does it contain independent comparison evidence?**
5. **Is the evidence sufficient for a specific validation claim?**

These questions are related but not interchangeable. A pristine `.nid` file may
be excellent for testing a reader and useless for validating a roughness
algorithm. A paper table may be valuable as a numerical reference and useless
for reproducing the processing chain.

### 1.2 Utility classes

Every record MUST receive one of the following utility classes:

| Class | Meaning | Valid uses |
|---|---|---|
| `benchmark_ready` | Distinct raw and processed/reference assets plus method or code evidence | Human-reviewed analysis validation candidate |
| `crosscheck_candidate` | Raw and processed/reference assets, but incomplete method/code context | Preliminary comparison, manual follow-up |
| `reader_fixture` | Raw/native data without an independent processed reference | Reader, parser, channel, orientation, metadata, and robustness tests |
| `processed_reference_only` | Processed output or reported values without recoverable raw input | Format examples, numerical context, literature tracing |
| `documentation_only` | Paper, protocol, script, or README without usable data assets | Query expansion, provenance, method discovery |
| `incomplete` | Insufficient or ambiguous evidence | Manual triage, query refinement |
| `rejected` | Corrupt, empty, unsafe, irrelevant, inaccessible, or legally unusable for the intended workflow | None without resolving the rejection reason |

Gold, Silver, and Bronze are convenience labels. They MUST NOT be presented as
scientific truth. The utility class is the more meaningful field.

---

## 2. The second principle: exhaustive means auditable, not infinite

“Search everything” is not an implementation. It is a coverage claim that must
be made precise.

A campaign MAY run until every configured source/query partition is exhausted.
It MAY run under a time or record budget. In every case, the system MUST record
what it searched, how it paginated, where it stopped, and what it could not
reach.

### 2.1 No hidden small limits

The application MUST NOT silently stop at 20, 25, or 30 results because an
example, default, or first page used that number.

- `max_records=0` means no user-selected record limit.
- `max_runtime=0` means no user-selected runtime limit.
- Source page sizes are transport details, not campaign limits.
- Safety protections remain active even in unlimited mode.

### 2.2 Coverage is a ledger

For every source and query, the campaign MUST preserve:

- query text;
- source name and adapter version;
- filter parameters;
- page or cursor;
- total reported by the source, if any;
- pages successfully read;
- records seen;
- records accepted, filtered, and deduplicated;
- retryable and terminal errors;
- exhaustion reason;
- known coverage gaps.

A campaign MUST NOT report “complete” when a source imposed a hard result cap or
a page failed repeatedly.

### 2.3 Adaptive partitioning

When a source limits accessible results, the query planner SHOULD subdivide the
search space in this order:

1. publication or deposit date;
2. AFM/SPM modality;
3. manufacturer or instrument family;
4. native format;
5. resource type or repository-specific facet.

A partition is considered searchable only when its result set fits inside the
source's accessible pagination model. Every child partition MUST preserve a link
to its parent so the coverage tree can be audited.

### 2.4 Checkpoints are scientific provenance

A checkpoint is not merely a convenience feature. It is part of the evidence
that the search was deterministic and recoverable.

The system MUST checkpoint only after the full page has been persisted. It MUST
never advance the cursor before committing the records from that page. A crash
may cause a page to be replayed, but MUST NOT cause a page to be skipped.

---

## 3. The third principle: public APIs first

Data Hunter uses official APIs and stable machine-readable interfaces whenever
possible.

### 3.1 Source hierarchy

Sources fall into three roles:

- **Direct repositories** expose records and files.
- **Meta-indexes** expose DOI metadata and repository links but may not expose
  files.
- **Enrichment services** help connect datasets to papers, code, authors, or
  citations.

A meta-index result MUST NOT be treated as a fully hydrated dataset.

### 3.2 Current supported sources

| Source | Role | Files | Checksum hints | Resume model |
|---|---|---:|---:|---|
| Zenodo | Direct repository | Yes | Often | Page |
| Figshare | Direct repository | Yes | Often | Page |
| DataCite | Meta-index | Usually no | No | Cursor |

### 3.3 Planned sources

Priority order:

1. OSF
2. Dataverse
3. Dryad
4. generic InvenioRDM instances
5. DSpace 7 repositories
6. OpenAIRE and repository aggregators
7. BioStudies and domain repositories where AFM/SPM data appear

A source SHOULD NOT be added if it requires brittle scraping of HTML, bypassing
access controls, ignoring terms of service, or emulating a browser against a
commercial site.

### 3.4 Responsible request behavior

Every adapter MUST implement:

- a descriptive User-Agent;
- per-host rate limiting;
- finite connect and read timeouts;
- retry with exponential backoff; jitter SHOULD be used when supported;
- `Retry-After` support;
- bounded concurrency;
- response schema validation;
- redacted errors;
- resumable pagination.

A source adapter MUST NOT assume that a successful HTTP response has the
expected JSON structure.

---

## 4. The fourth principle: file names are clues, not facts

Extensions and names are useful but fallible.

### 4.1 Ambiguous containers

The following suffixes are containers or generic formats, not proof of scientific
role:

- `.csv`, `.tsv`, `.txt`, `.dat`
- `.h5`, `.hdf5`
- `.tif`, `.tiff`
- `.mat`, `.npy`, `.npz`

A `.h5` file may be native instrument data, a processed analysis archive, or an
unrelated machine-learning tensor. A TIFF may be a raw vendor format, a rendered
image, or a figure panel.

### 4.2 Token boundaries are mandatory

Classification MUST use token-aware matching. Substring logic creates absurd
false positives:

- `drawings.csv` MUST NOT count as raw because it contains `raw`.
- `decode_results.txt` MUST NOT count as code because it contains `code`.
- `staff_notes.md` MUST NOT count as AFM because it contains the letters `afm`.

Every real false positive discovered during a campaign SHOULD become a
regression test.

### 4.3 One file cannot fabricate a chain

A single file classified as both raw and processed MUST NOT, by itself, satisfy
the “raw + processed” requirement. Validation-chain completeness requires
**distinct assets** or explicit internal structure verified by a format-aware
inspector.

### 4.4 Confidence and reasons

A mature classifier SHOULD return:

```yaml
role: raw
format_id: bruker-nanoscope
confidence: 0.94
reasons:
  - numeric extension matched a known Bruker family
  - header signature matched
  - record metadata names a Bruker instrument
```

A label without reasons is not reviewable.

---

## 5. The fifth principle: preserve provenance before interpretation

The raw source payload is evidence. Normalization improves usability, but MUST
not erase origin.

For each record, preserve:

- source and source identifier;
- source landing page;
- version DOI and concept DOI where available;
- normalized DOI;
- raw source metadata;
- retrieval timestamp;
- matched query and partition;
- adapter version;
- file URLs and repository file identifiers;
- repository-provided checksums;
- local SHA-256 after download;
- license and rights statements;
- related identifiers and relation types.

Normalization decisions MUST be deterministic. Potentially lossy merges MUST be
conservative and reversible.

### 5.1 Deduplication order

Preferred identity hierarchy:

1. exact version DOI;
2. concept DOI plus explicit version;
3. repository-native persistent identifier;
4. normalized canonical URL;
5. conservative fingerprint of title, creators, year, and source.

Two records MUST NOT be merged only because their titles are similar.

### 5.2 Version awareness

A concept DOI represents a family of versions. A version DOI represents a
specific citable object. Data Hunter SHOULD preserve both and SHOULD prefer
version-specific checksums and file inventories for reproducibility.

---

## 6. The sixth principle: integrity is layered

Integrity checks do not prove scientific correctness, but they remove obvious
failure modes.

### 6.1 Metadata integrity

Check:

- non-empty title or identifier;
- usable landing URL;
- plausible file entries;
- declared size consistency;
- license presence and clarity;
- relation identifiers;
- duplicate or conflicting file names.

### 6.2 Transport integrity

Check:

- HTTPS;
- redirect destinations;
- HTTP status;
- content length when provided;
- resumable range semantics;
- timeout behavior;
- partial file consistency;
- repository checksum;
- local SHA-256.

### 6.3 Container integrity

Archives MAY be inventoried without extraction. Inventory SHOULD report:

- entry count;
- nested paths;
- suspicious absolute or traversal paths;
- total compressed and uncompressed size;
- compression ratio;
- encrypted entries;
- duplicate paths;
- detected file roles and formats;
- truncation due to safety limits.

Data Hunter MUST NOT execute downloaded content.

### 6.4 Scientific integrity

Scientific integrity is a separate layer and requires human review of:

- calibration parameters;
- coordinate conventions;
- channel units;
- image orientation;
- preprocessing order;
- tip/cantilever parameters;
- model assumptions;
- fitting ranges and initial values;
- reported uncertainty;
- tolerance definition.

---

## 7. The seventh principle: unlimited downloads still need brakes

The project may allow functionally unlimited downloads because AFM/SPM public
data are scarce and artificial size filters can discard the best evidence.

However, “unlimited” MUST require explicit acknowledgement in non-interactive
mode. It MUST NOT disable:

- path sanitization;
- redirect validation;
- private-network blocking;
- disk-write error handling;
- partial-file recovery;
- checksum verification;
- archive safety checks;
- pause and stop requests;
- observability.

### 7.1 Discovery and download are separate phases

A campaign SHOULD first build a complete metadata and file inventory. Download
selection happens afterward.

Before download, the CLI SHOULD display:

- selected records;
- selected files;
- known bytes;
- unknown-size files;
- unknown licenses;
- file roles and formats;
- destination;
- whether the run is bounded or unbounded.

### 7.2 Idempotent downloading

A verified local file MUST NOT be downloaded again. A `.part` file SHOULD be
resumed when the server honors byte ranges. If the server ignores the range,
the partial file MUST be restarted rather than concatenated with a full body.

---

## 8. The eighth principle: progress must be truthful

A progress indicator is an operational measurement, not decoration.

When the total is known, the application MAY show percentage and ETA. When the
total is unknown, it MUST show counters and rates instead of inventing a
percentage.

At minimum, a running campaign SHOULD expose:

- campaign state;
- uptime;
- current source;
- current query and page/cursor;
- records seen;
- unique records;
- duplicates;
- files enumerated;
- errors;
- recent rate;
- last heartbeat;
- current budget remaining, when bounded.

A heartbeat MUST continue during long jobs so the user can distinguish slow work
from a dead process.

---

## 9. The ninth principle: pause is a first-class operation

A campaign MUST support cooperative pause and resume.

- First `SIGINT`: request pause and stop at the next safe checkpoint.
- A second emergency interruption MAY exit faster, but MUST close active
  transactions where possible.
- `campaign pause`: persist `pause_requested`.
- `campaign resume`: continue from the saved cursor.
- `campaign stop`: finish at a safe checkpoint and mark the campaign stopped.

A resumed campaign MUST be idempotent. Replayed pages may increase duplicate
counts but MUST NOT duplicate catalog records or downloads.

---

## 10. The tenth principle: SQLite is the ledger, exports are views

The persistent database is the campaign's source of truth. JSON, JSONL, CSV, and
Markdown are exports for humans and downstream tools.

The database MUST use:

- schema migrations;
- foreign keys;
- WAL mode;
- unique constraints;
- short transactions;
- UTC timestamps;
- idempotent upserts;
- durable checkpoints.

Large raw source payloads MAY be stored as JSON, but stable query fields SHOULD
be promoted to explicit columns when they become operationally important.

---

## 11. The eleventh principle: scoring must be decomposable

A single score is seductive and dangerous. It compresses different questions
into a number that looks more certain than the evidence.

The system SHOULD maintain independent dimensions:

- domain relevance;
- format confidence;
- evidence completeness;
- integrity confidence;
- license clarity;
- benchmark readiness.

Every score MUST include reasons. Threshold changes MUST be tested against a
small human-reviewed corpus of positives and negatives.

### 11.1 Gold is not truth

Gold means the record appears to contain a strong validation chain according to
documented heuristics. It does not mean:

- the authors' processed result is correct;
- the method is appropriate;
- SPM-Kit must reproduce it exactly;
- all metadata are complete;
- the dataset is legally redistributable.

---

## 12. The twelfth principle: tests are accumulated memory

The test suite is where the project remembers every trap it has encountered.

### 12.1 Required test families

Every source adapter MUST have offline fixtures for:

- first and final page;
- cursor/page resume;
- empty result;
- malformed response;
- missing optional fields;
- 429 and `Retry-After`;
- 500-series response;
- timeout;
- duplicate DOI;
- duplicate file URL;
- file inventory;
- source-specific checksum format.

Core tests MUST cover:

- DOI and URL normalization;
- token-boundary classification;
- ambiguous extensions;
- utility classes;
- exact page checkpoints;
- pause/resume;
- idempotent upserts;
- schema migration;
- checksum mismatch;
- unsafe paths;
- interrupted downloads;
- deterministic exports.

### 12.2 Live tests

Live API tests MUST be opt-in, rate-limited, and non-destructive. CI MUST NOT
depend on external services for normal correctness.

### 12.3 Done means verified

A feature is not complete because the CLI prints the expected sentence. It is
complete when:

- behavior is specified;
- failure cases are tested;
- migration is tested;
- documentation is updated;
- the diff is reviewed;
- the claimed capability is demonstrated.

---

## 13. The thirteenth principle: source adapters are plugins, not special cases

A new source adapter MUST document:

- official API documentation;
- role: direct, meta-index, or enrichment;
- authentication requirements;
- public-access behavior;
- pagination model;
- hard result caps;
- supported filters;
- file-list capability;
- checksum capability;
- rate-limit guidance;
- stable identifiers;
- licensing fields;
- known schema quirks;
- checkpoint representation;
- test fixtures.

A source MUST NOT be merged until it can resume without skipping records.

See [`docs/SOURCE_ADAPTER_GUIDE.md`](docs/SOURCE_ADAPTER_GUIDE.md).

---

## 14. The fourteenth principle: scientific scarcity changes prioritization

AFM/SPM public datasets are scarce and heterogeneous. Data Hunter SHOULD favor
recall during discovery and precision during benchmark promotion.

That means:

- broad queries are acceptable;
- Bronze and raw-only records may be retained;
- downloads are selected later;
- only strong evidence is promoted to benchmark-ready;
- human annotations are preserved;
- uncertain classifications remain uncertain.

The project MUST NOT erase weak candidates merely because they are not complete
today. A later paper, code repository, or processed export may complete the
chain.

---

## 15. The fifteenth principle: legal and ethical provenance is part of quality

Publicly accessible does not automatically mean freely redistributable.

Before reuse:

1. read the dataset license;
2. preserve author and repository attribution;
3. cite the version DOI;
4. retain rights statements;
5. avoid redistributing restricted files;
6. avoid collecting private or accidentally exposed laboratory data;
7. respect API and repository terms;
8. document transformations.

Data Hunter MUST NOT include credentials, private datasets, cookies, or API
secrets in exported catalogs or logs.

---

## 16. The sixteenth principle: human review is a recorded transformation

Human review SHOULD not live only in someone's memory or a private spreadsheet.
A reviewed benchmark manifest SHOULD record:

```yaml
review:
  status: human_reviewed
  reviewer: ORCID-or-name
  reviewed_at: 2026-07-14T22:00:00Z
  decision: crosscheck_candidate
  reasons:
    - raw and processed files refer to the same experiment
    - processing parameters are incomplete
  unresolved:
    - cantilever spring constant not reported
```

A review may be revised. Revisions MUST preserve prior decisions and reasons.

---

## 17. The seventeenth principle: benchmark manifests are the bridge to SPM-Kit

The final product of curation is not merely a download folder. It is a manifest
that SPM-Kit can consume reproducibly.

A mature manifest SHOULD include:

```yaml
dataset:
  version_doi: 10.xxxx/example.v2
  concept_doi: 10.xxxx/example
  source: zenodo
  source_id: "123456"
  license: CC-BY-4.0

files:
  raw:
    - path: raw/scan.nid
      sha256: ...
      format_id: nanosurf-nid
  processed:
    - path: reference/roughness.csv
      sha256: ...

comparison:
  operation: iso25178_roughness
  reference:
    Sa: 2.31e-9
    Sq: 3.02e-9
  units: m
  parameters:
    leveling: plane
    filter: none
  tolerances:
    relative: 0.02

provenance:
  publication_doi: 10.xxxx/paper
  code_url: https://...
  notes: ...
```

Data Hunter MAY generate a draft manifest. A human MUST approve scientific
comparison parameters before the manifest becomes part of a validation suite.

---

## 18. The eighteenth principle: architecture serves recoverability

The architecture separates:

- domain models;
- source adapters;
- query planning;
- campaign state;
- persistence;
- classification;
- downloading;
- exporting;
- CLI presentation.

No source adapter should write files directly. No classifier should perform HTTP
requests. No CLI formatter should own scientific decisions. No database model
should depend on terminal rendering.

The old single-module API may remain as a compatibility layer during migration,
but new functionality SHOULD be implemented in dedicated modules.

---

## 19. The nineteenth principle: failures are data

A failed request, corrupt archive, missing file, or ambiguous license is part of
the campaign result.

Errors SHOULD record:

- operation;
- source;
- query and cursor;
- exception category;
- redacted message;
- retryability;
- attempt count;
- first and last occurrence;
- resolution state.

The application SHOULD continue independent partitions after recoverable
failures. It MUST NOT silently mark an errored partition as exhausted.

---

## 20. The twentieth principle: claims must match implementation

The README, paper, release notes, and CLI help MUST describe what the software
actually does.

Do not claim:

- “all public AFM data” when only three repositories are searched;
- “validation” when only file integrity is checked;
- “verified format” when only an extension matched;
- “complete campaign” when partitions failed;
- “reproducible benchmark” when parameters are missing;
- “safe archive” when it was merely listed without extraction.

Precise language is not modesty theater. It is scientific instrumentation for
expectations.

---

# Operational doctrine

## A. One-hour campaign

```bash
spmkit-data-hunter campaign create afm-one-hour \
  --preset all \
  --source all \
  --max-runtime 1h \
  --max-records 0 \
  --output spm_benchmarks

spmkit-data-hunter campaign run afm-one-hour --output spm_benchmarks
```

Inspect while it is not running:

```bash
spmkit-data-hunter campaign status afm-one-hour --output spm_benchmarks
```

Resume after the runtime budget:

```bash
spmkit-data-hunter campaign resume afm-one-hour --output spm_benchmarks
```

## B. Run until configured partitions are exhausted

```bash
spmkit-data-hunter campaign create afm-deep \
  --preset all \
  --source all \
  --max-runtime 0 \
  --max-records 0

spmkit-data-hunter campaign run afm-deep
```

## C. Pause safely

From another terminal:

```bash
spmkit-data-hunter campaign pause afm-deep
```

Or press `Ctrl+C` once in the running terminal.

## D. Plan downloads before consuming disk

```bash
spmkit-data-hunter download plan afm-deep \
  --level gold \
  --level silver \
  --category raw \
  --category processed \
  --category documentation
```

## E. Explicit unbounded download

```bash
spmkit-data-hunter download run afm-deep \
  --max-file-gb 0 \
  --max-record-gb 0 \
  --accept-unbounded-downloads
```

This disables user-selected size ceilings, not security checks or filesystem
reality.

---

# Release oath

Before a release, the maintainer should be able to answer yes to all of these:

- Does a campaign resume without skipping a page?
- Can a raw-only record avoid being mislabeled as validated?
- Are every source's files enumerated when the API exposes them?
- Are query limits visible and auditable?
- Do failed partitions remain unfinished?
- Are downloads idempotent and checksummed?
- Are credentials absent from logs and exports?
- Do offline tests cover pagination and malformed payloads?
- Is every new classification rule explained and tested?
- Does the documentation avoid claims stronger than the evidence?

If not, the release is not damned. It is simply not ready.

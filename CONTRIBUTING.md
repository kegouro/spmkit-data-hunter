# Contributing

Contributions are welcome, especially:

- repository adapters built on documented public APIs;
- pagination and resume fixtures;
- native AFM/SPM format intelligence;
- false-positive regression cases;
- integrity and download hardening;
- human-reviewed benchmark manifests;
- documentation corrections.

Read [`SCIENTIFIC_DATA_HUNTING_BIBLE.md`](SCIENTIFIC_DATA_HUNTING_BIBLE.md)
before changing scientific classification or coverage claims.

## Development setup

```bash
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install -e ".[dev]"
python3 -m pytest
python3 -m ruff check .
python3 -m ruff format --check .
```

## Ground rules

- Do not add API keys, credentials, private datasets, cookies, or restricted files.
- Use official APIs whenever available.
- Do not bypass access controls or scrape services that prohibit automation.
- A cursor may advance only after a complete page is persisted.
- A failed partition may not be marked exhausted.
- Raw-only evidence must remain a reader fixture, not an analysis benchmark.
- Every real false positive should become a regression test.
- Explain scientific assumptions and uncertainty explicitly.
- Gold is a discovery heuristic, not a declaration of experimental truth.

## Adding a source

Follow [`docs/SOURCE_ADAPTER_GUIDE.md`](docs/SOURCE_ADAPTER_GUIDE.md). A source
pull request must include:

1. official API documentation;
2. role and capability declaration;
3. pagination/checkpoint semantics;
4. offline search and detail fixtures;
5. malformed-response and final-page tests;
6. file inventory and checksum mapping;
7. rate-limit guidance;
8. known coverage gaps.

## Pull requests

Keep pull requests focused. Describe:

1. what changed;
2. why it is useful;
3. how it was tested;
4. migration or compatibility effects;
5. API assumptions;
6. scientific assumptions;
7. remaining risks.

Do not mix a large refactor with new classification behavior unless the change
cannot be separated safely.

# Instructions for coding agents

This repository welcomes AI-assisted contributions, but the agent is not the
scientific authority.

## Read first

1. `SCIENTIFIC_DATA_HUNTING_BIBLE.md`
2. `docs/ARCHITECTURE.md`
3. `docs/VALIDATION_TAXONOMY.md`
4. `docs/SOURCE_ADAPTER_GUIDE.md`
5. `docs/THREAT_MODEL.md`

## Non-negotiable rules

- Do not invent API fields, pagination behavior, file formats, or scientific
  claims.
- Use official API documentation and offline fixtures.
- Do not advance a campaign cursor before persisting the complete page.
- Do not classify raw-only evidence as an analysis benchmark.
- Do not add hidden search limits.
- Do not disable security protections to satisfy “unlimited” mode.
- Do not print or commit secrets.
- Do not scrape a commercial website when a public API exists.
- Do not make a destructive Git operation without human authorization.
- Do not claim completion without running tests and Ruff.

## Required verification

```bash
python3 -m pip install -e ".[dev]"
python3 -m pytest
python3 -m ruff check .
python3 -m ruff format --check .
spmkit-data-hunter --self-test
spmkit-data-hunter doctor
```

## Change protocol

For each non-trivial change, report:

- files changed;
- behavior changed;
- tests added;
- commands run;
- compatibility effect;
- scientific assumptions;
- remaining risks.

Every discovered false positive or API edge case should become a regression
test.

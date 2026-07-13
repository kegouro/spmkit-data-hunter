# Contributing

Contributions are welcome, especially:

- new repository adapters that use documented public APIs;
- support for additional native AFM/SPM file extensions;
- improved benchmark scoring rules;
- tests for API response variations;
- reviewed public benchmark manifests;
- documentation corrections.

## Development setup

```bash
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install -e ".[dev]"
python3 -m pytest
python3 -m ruff check .
```

## Ground rules

- Do not add API keys, credentials, private datasets, or restricted files.
- Do not bypass access controls or scrape services that prohibit automated access.
- Keep requests rate-limited and use official APIs whenever available.
- Add tests for parsing and scoring changes.
- Explain scientific assumptions explicitly.
- A Gold score is a discovery heuristic, not a declaration of experimental truth.

## Pull requests

Please keep pull requests focused. Describe:

1. what changed;
2. why it is useful;
3. how it was tested;
4. any API or scientific assumptions introduced.

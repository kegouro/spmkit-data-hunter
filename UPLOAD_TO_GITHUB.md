# Release and upload checklist

The project already contains GitHub-ready metadata, CI, issue templates,
documentation, and package configuration.

## Verify locally

```bash
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install -e ".[dev]"
python3 -m pytest
python3 -m ruff check .
python3 -m ruff format --check .
spmkit-data-hunter --self-test
spmkit-data-hunter doctor
```

## Inspect the diff

```bash
git status --short
git diff --stat
git diff
```

Do not commit:

- `spm_benchmarks/`;
- downloaded datasets;
- `.env` files;
- tokens;
- `.DS_Store`;
- SQLite `-wal` or `-shm` files;
- caches and virtual environments.

## Suggested commit

```bash
git add .
git commit -m "Add resumable scientific data hunting campaigns"
git push origin main
```

Review the CI result before creating a release.

## Suggested release

Tag:

```text
v2.2.0
```

Title:

```text
SPM-Kit Data Hunter v2.2.0: resumable campaign engine
```

Highlights:

- deep page/cursor search without small hidden limits;
- durable campaign checkpoints;
- pause, resume, stop, heartbeat, and export;
- Zenodo, Figshare, and DataCite adapters;
- scientific utility classes;
- remote file probes;
- stronger archive inventory;
- package architecture with legacy CLI compatibility;
- the Scientific Data Hunting Bible.

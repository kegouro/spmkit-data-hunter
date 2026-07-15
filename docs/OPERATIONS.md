# Operations

## Inspect configuration

```bash
spmkit-data-hunter doctor
spmkit-data-hunter sources list
```

## Create and run a campaign

```bash
spmkit-data-hunter campaign create overnight \
  --preset all \
  --source all \
  --max-runtime 8h \
  --max-records 0

spmkit-data-hunter campaign run overnight
```

## Status and recovery

```bash
spmkit-data-hunter campaign status overnight
spmkit-data-hunter campaign pause overnight
spmkit-data-hunter campaign resume overnight
spmkit-data-hunter campaign stop overnight
spmkit-data-hunter campaign verify overnight
```

`verify` performs lightweight remote reachability and size probes without full
download. A campaign stopped by time or record budget retains its next cursor and may be
resumed.

## Databases

- `spm_benchmarks/catalog.sqlite3`: normalized records and files.
- `spm_benchmarks/campaigns.sqlite3`: campaign configurations, checkpoints,
  events, and statistics.

SQLite uses WAL mode. Copy the main database together with `-wal` and `-shm`
files only while the process is stopped, or use SQLite's backup mechanism.

## Logs

Normal logs provide a heartbeat after every page. A healthy campaign should show
changing page, record, or file counters. A source failure is recorded as a
partition error and does not advance the cursor.

"""Unified command-line interface.

Legacy flag-only invocations remain supported. New campaign-oriented commands
provide durable checkpoints for searches that run for hours or until sources
are exhausted.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import platform
import sys
from collections.abc import Sequence
from pathlib import Path

from .campaigns import CampaignConfig, CampaignStore
from .catalog_io import load_records
from .engine import CampaignEngine
from .legacy import (
    DEFAULT_OUTPUT,
    DEFAULT_USER_AGENT,
    QUERY_PRESETS,
    Catalog,
    HttpClient,
    download_record,
    export_catalog,
)
from .legacy import (
    main as legacy_main,
)
from .sources import source_capabilities
from .verification import probe_asset
from .version import __version__

NEW_COMMANDS = {"doctor", "sources", "campaign", "download"}


def parse_duration(value: str) -> int:
    text = value.strip().casefold()
    if text in {"0", "unlimited", "none"}:
        return 0
    multipliers = {"s": 1, "m": 60, "h": 3600, "d": 86400}
    if text[-1:] in multipliers:
        try:
            return int(float(text[:-1]) * multipliers[text[-1]])
        except ValueError as exc:
            raise argparse.ArgumentTypeError(f"Duración inválida: {value}") from exc
    try:
        return int(text)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"Duración inválida: {value}") from exc


def _queries(presets: list[str], custom: list[str]) -> list[str]:
    result: list[str] = []
    for preset in presets:
        result.extend(QUERY_PRESETS[preset])
    result.extend(custom)
    if not result:
        result.extend(QUERY_PRESETS["all"])
    return list(dict.fromkeys(result))


def _store(output: Path) -> CampaignStore:
    return CampaignStore(output.expanduser().resolve() / "campaigns.sqlite3")


def _print_campaign(campaign) -> None:
    print(f"Campaign: {campaign.slug}")
    print(f"ID:       {campaign.id}")
    print(f"Status:   {campaign.status}")
    if campaign.requested_status:
        print(f"Request:  {campaign.requested_status}")
    print(f"Output:   {campaign.config.output}")
    print(f"Sources:  {', '.join(campaign.config.sources)}")
    print(f"Queries:  {len(campaign.config.queries)}")
    print(f"Created:  {campaign.created_at}")
    print(f"Heartbeat:{campaign.last_heartbeat_at or ' never'}")
    if campaign.last_error:
        print(f"Error:    {campaign.last_error}")
    if campaign.stats:
        print("Stats:")
        for key in sorted(campaign.stats):
            print(f"  {key}: {campaign.stats[key]}")


def _campaign_create(args: argparse.Namespace) -> int:
    output = args.output.expanduser().resolve()
    output.mkdir(parents=True, exist_ok=True)
    store = _store(output)
    try:
        config = CampaignConfig(
            slug=args.name,
            output=str(output),
            sources=args.source or ["all"],
            queries=_queries(args.preset, args.query),
            page_size=args.page_size,
            max_runtime_seconds=args.max_runtime,
            max_records=args.max_records,
            heartbeat_seconds=args.heartbeat,
            min_score=args.min_score,
            require_open_license=args.require_open_license,
            rate_seconds=args.rate_seconds,
            timeout=args.timeout,
        )
        campaign = store.create(config)
        _print_campaign(campaign)
        print("\nRun with:")
        print(f"  spmkit-data-hunter campaign run {campaign.slug} --output {output}")
        return 0
    except Exception as exc:
        print(f"No se pudo crear la campaña: {exc}", file=sys.stderr)
        return 2
    finally:
        store.close()


def _campaign_run(args: argparse.Namespace) -> int:
    store = _store(args.output)
    try:
        campaign = CampaignEngine(store).run(args.name)
        _print_campaign(campaign)
        return (
            0
            if campaign.status in {"completed", "completed_with_errors", "paused", "stopped"}
            else 1
        )
    except KeyError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    finally:
        store.close()


def _campaign_status(args: argparse.Namespace) -> int:
    store = _store(args.output)
    try:
        _print_campaign(store.get(args.name))
        return 0
    except KeyError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    finally:
        store.close()


def _campaign_list(args: argparse.Namespace) -> int:
    store = _store(args.output)
    try:
        campaigns = store.list()
        if not campaigns:
            print("No campaigns found.")
            return 0
        for campaign in campaigns:
            seen = campaign.stats.get("records_seen", 0)
            new = campaign.stats.get("records_new", 0)
            print(f"{campaign.slug:24} {campaign.status:10} seen={seen:<8} unique={new:<8}")
        return 0
    finally:
        store.close()


def _campaign_request(args: argparse.Namespace, status: str) -> int:
    store = _store(args.output)
    try:
        campaign = store.get(args.name)
        store.request(campaign.id, status)
        print(f"Requested {status} for {campaign.slug}.")
        return 0
    except KeyError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    finally:
        store.close()


def _campaign_verify(args: argparse.Namespace) -> int:
    store = _store(args.output)
    catalog = Catalog(args.output / "catalog.sqlite3")
    try:
        campaign = store.get(args.name)
        records = load_records(args.output / "catalog.sqlite3", store.record_keys(campaign.id))
        client = HttpClient(
            timeout=args.timeout,
            user_agent=DEFAULT_USER_AGENT,
            rate_seconds=args.rate_seconds,
        )
        checked = 0
        counts: dict[str, int] = {}
        for record in records:
            for asset in record.files:
                if args.max_files and checked >= args.max_files:
                    break
                result = probe_asset(client, asset)
                asset.verification_status = result.status
                asset.verification_notes = result.notes
                catalog.update_asset_verification(
                    record.key,
                    asset.url,
                    verification_status=result.status,
                    verification_notes=result.notes,
                    observed_size=result.observed_size,
                )
                counts[result.status] = counts.get(result.status, 0) + 1
                checked += 1
                print(f"[{result.status}] {asset.name}")
            if args.max_files and checked >= args.max_files:
                break
        refreshed = load_records(args.output / "catalog.sqlite3", store.record_keys(campaign.id))
        export_catalog(refreshed, args.output)
        print(f"Verified {checked} remote file entries")
        for status, count in sorted(counts.items()):
            print(f"  {status}: {count}")
        return 0
    except KeyError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    finally:
        catalog.close()
        store.close()


def _campaign_export(args: argparse.Namespace) -> int:
    store = _store(args.output)
    try:
        campaign = store.get(args.name)
        records = load_records(args.output / "catalog.sqlite3", store.record_keys(campaign.id))
        target = args.target or args.output
        export_catalog(records, target)
        print(f"Exported {len(records)} records to {target.resolve()}")
        return 0
    finally:
        store.close()


def _selected_records(args: argparse.Namespace):
    store = _store(args.output)
    try:
        campaign = store.get(args.name)
        records = load_records(args.output / "catalog.sqlite3", store.record_keys(campaign.id))
    finally:
        store.close()
    levels = set(args.level or ["gold", "silver"])
    return [record for record in records if record.level in levels]


def _download_plan(args: argparse.Namespace) -> int:
    records = _selected_records(args)
    categories = set(args.category or ["raw", "processed", "code", "documentation", "archive"])
    files = [
        asset
        for record in records
        for asset in record.files
        if not categories or categories.intersection(asset.categories)
    ]
    known_bytes = sum(asset.size or 0 for asset in files)
    unknown = sum(asset.size is None for asset in files)
    print(f"Records:       {len(records)}")
    print(f"Files:         {len(files)}")
    print(f"Known bytes:   {known_bytes} ({known_bytes / 1024**3:.3f} GiB)")
    print(f"Unknown sizes: {unknown}")
    print("No files were downloaded.")
    return 0


def _download_run(args: argparse.Namespace) -> int:
    if args.max_file_gb == 0 and args.max_record_gb == 0 and not args.accept_unbounded_downloads:
        print(
            "Unbounded downloads require --accept-unbounded-downloads. "
            "This is a safety acknowledgement, not a scientific filter.",
            file=sys.stderr,
        )
        return 2
    records = _selected_records(args)
    client = HttpClient(
        timeout=args.timeout,
        user_agent=DEFAULT_USER_AGENT,
        rate_seconds=args.rate_seconds,
    )
    catalog = Catalog(args.output / "catalog.sqlite3")
    max_file = int(args.max_file_gb * 1024**3) if args.max_file_gb else 2**63 - 1
    max_record = int(args.max_record_gb * 1024**3) if args.max_record_gb else 2**63 - 1
    try:
        for record in records:
            download_record(
                record,
                client=client,
                catalog=catalog,
                output_dir=args.output,
                categories=set(
                    args.category or ["raw", "processed", "code", "documentation", "archive"]
                ),
                max_file_bytes=max_file,
                max_record_bytes=max_record,
                inspect_archives=args.inspect_archives,
            )
        export_catalog(records, args.output)
        return 0
    finally:
        catalog.close()


def _doctor(args: argparse.Namespace) -> int:
    print(f"SPM-Kit Data Hunter {__version__}")
    print(f"Python: {platform.python_version()} ({sys.executable})")
    print(f"Platform: {platform.platform()}")
    print(f"User-Agent: {DEFAULT_USER_AGENT}")
    print("Credentials detected:")
    for name in [
        "GITHUB_TOKEN",
        "ZENODO_TOKEN",
        "FIGSHARE_TOKEN",
        "OSF_TOKEN",
        "DATAVERSE_TOKEN",
        "DRYAD_TOKEN",
        "OPENALEX_API_KEY",
        "CROSSREF_MAILTO",
    ]:
        print(f"  {name}: {'yes' if os.getenv(name) else 'no'}")
    print("Sources:")
    for source in source_capabilities():
        print(
            f"  {source['name']}: role={source['role']} files={source['files']} "
            f"resume={source['resume']}"
        )
    if args.json:
        print(json.dumps(source_capabilities(), indent=2))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="spmkit-data-hunter",
        description="Deep, resumable discovery of public AFM/SPM validation evidence.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    doctor = sub.add_parser("doctor", help="Inspect local configuration and capabilities")
    doctor.add_argument("--json", action="store_true")
    doctor.set_defaults(func=_doctor)

    sources = sub.add_parser("sources", help="Inspect source adapters")
    sources_sub = sources.add_subparsers(dest="sources_command", required=True)
    sources_list = sources_sub.add_parser("list")
    sources_list.set_defaults(
        func=lambda _args: (
            print(json.dumps(source_capabilities(), indent=2, ensure_ascii=False)) or 0
        )
    )

    campaign = sub.add_parser("campaign", help="Create and control resumable campaigns")
    campaign_sub = campaign.add_subparsers(dest="campaign_command", required=True)

    create = campaign_sub.add_parser("create", help="Create a frozen campaign configuration")
    create.add_argument("name")
    create.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    create.add_argument(
        "--source", action="append", choices=["all", "zenodo", "figshare", "datacite"]
    )
    create.add_argument("--preset", action="append", choices=sorted(QUERY_PRESETS), default=[])
    create.add_argument("--query", action="append", default=[])
    create.add_argument("--page-size", type=int, default=100)
    create.add_argument("--max-runtime", type=parse_duration, default=0)
    create.add_argument("--max-records", type=int, default=0)
    create.add_argument("--heartbeat", type=int, default=15)
    create.add_argument("--min-score", type=int, default=0)
    create.add_argument("--require-open-license", action="store_true")
    create.add_argument("--rate-seconds", type=float, default=1.05)
    create.add_argument("--timeout", type=float, default=45.0)
    create.set_defaults(func=_campaign_create)

    for name, function in [("run", _campaign_run), ("resume", _campaign_run)]:
        command = campaign_sub.add_parser(name)
        command.add_argument("name")
        command.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
        command.set_defaults(func=function)

    status = campaign_sub.add_parser("status")
    status.add_argument("name")
    status.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    status.set_defaults(func=_campaign_status)

    list_cmd = campaign_sub.add_parser("list")
    list_cmd.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    list_cmd.set_defaults(func=_campaign_list)

    for name, request in [("pause", "pause_requested"), ("stop", "stop_requested")]:
        command = campaign_sub.add_parser(name)
        command.add_argument("name")
        command.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
        command.set_defaults(func=lambda args, request=request: _campaign_request(args, request))

    export = campaign_sub.add_parser("export")
    export.add_argument("name")
    export.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    export.add_argument("--target", type=Path)
    export.set_defaults(func=_campaign_export)

    verify = campaign_sub.add_parser(
        "verify", help="Probe every remote file entry without full download"
    )
    verify.add_argument("name")
    verify.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    verify.add_argument("--max-files", type=int, default=0)
    verify.add_argument("--rate-seconds", type=float, default=1.05)
    verify.add_argument("--timeout", type=float, default=45.0)
    verify.set_defaults(func=_campaign_verify)

    download = sub.add_parser("download", help="Plan or run selective campaign downloads")
    download_sub = download.add_subparsers(dest="download_command", required=True)
    for name, function in [("plan", _download_plan), ("run", _download_run)]:
        command = download_sub.add_parser(name)
        command.add_argument("name")
        command.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
        command.add_argument(
            "--level",
            action="append",
            choices=["gold", "silver", "bronze"],
            default=None,
        )
        command.add_argument(
            "--category",
            action="append",
            choices=["raw", "processed", "code", "documentation", "archive", "image", "other"],
            default=None,
        )
        if name == "run":
            command.add_argument("--max-file-gb", type=float, default=2.0)
            command.add_argument("--max-record-gb", type=float, default=10.0)
            command.add_argument("--accept-unbounded-downloads", action="store_true")
            command.add_argument("--inspect-archives", action="store_true")
            command.add_argument("--rate-seconds", type=float, default=1.05)
            command.add_argument("--timeout", type=float, default=120.0)
        command.set_defaults(func=function)

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args_list = list(sys.argv[1:] if argv is None else argv)
    if args_list and args_list[0] not in NEW_COMMANDS:
        return legacy_main(args_list)
    if not args_list:
        build_parser().print_help()
        print("\nLegacy mode remains available with flag-only commands, e.g. --preset all.")
        return 0
    parser = build_parser()
    args = parser.parse_args(args_list)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
    return int(args.func(args))

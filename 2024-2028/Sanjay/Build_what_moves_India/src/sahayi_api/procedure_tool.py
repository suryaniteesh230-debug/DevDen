from __future__ import annotations

import argparse
import json
from pathlib import Path

from pydantic import ValidationError

from sahayi_api.procedures import PackLoadError, ProcedurePack, default_pack_root, load_procedure_registry


def schema_text() -> str:
    return json.dumps(ProcedurePack.model_json_schema(), indent=2, sort_keys=True) + "\n"


def default_schema_path() -> Path:
    return Path(__file__).resolve().parents[2] / "procedure-packs" / "schemas" / "procedure-pack-v1.schema.json"


def export_schema(output: Path) -> int:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(schema_text(), encoding="utf-8")
    print(f"Exported Procedure Pack v1 schema to {output}")
    return 0


def check_schema(schema_path: Path) -> int:
    try:
        checked_in = schema_path.read_text(encoding="utf-8")
    except OSError:
        print("Checked-in Procedure Pack schema is missing")
        return 1
    if checked_in != schema_text():
        print("Checked-in Procedure Pack schema does not match the Pydantic model")
        return 1
    print("Checked-in Procedure Pack schema matches the Pydantic model")
    return 0


def validate_packs(pack_root: Path) -> int:
    try:
        registry = load_procedure_registry(pack_root)
    except PackLoadError as exc:
        print(str(exc))
        return 1
    print(f"Validated {len(registry)} active procedure pack(s)")
    for service_id, loaded in sorted(registry.items()):
        print(f"{service_id} {loaded.pack.pack_version} sha256:{loaded.digest}")
    return 0


def validate_file(pack_path: Path) -> int:
    try:
        pack = ProcedurePack.model_validate_json(pack_path.read_text(encoding="utf-8"))
    except (OSError, ValidationError, ValueError):
        print("Procedure pack is invalid")
        return 1
    print(f"Validated {pack.service_id} {pack.pack_version}")
    return 0


def monitor_sources(
    *,
    pack_root: Path,
    live: bool,
    acknowledged: bool,
    source_ids: list[str],
    fixture: Path | None,
    json_output: bool,
    output: Path | None,
) -> int:
    from sahayi_api.monitoring import SourceRetriever, load_demo_reports, report_exit_code, report_json, report_text

    try:
        registry = load_procedure_registry(pack_root)
    except PackLoadError:
        print("Procedure packs are unavailable")
        return 1
    if live and not acknowledged:
        print("Live retrieval requires --acknowledge-live-public-source-check")
        return 2
    if not live and source_ids:
        print("--source-id is available only with explicit live mode")
        return 2
    if live:
        configured = [
            (loaded, source)
            for loaded in registry.values()
            for source in loaded.pack.sources
            if source.monitoring is not None and (not source_ids or source.source_id in source_ids)
        ]
        if source_ids and set(source_ids) != {source.source_id for _, source in configured}:
            print("Requested source is not an allowlisted monitored source")
            return 2
        retriever = SourceRetriever()
        reports = [retriever.retrieve(loaded, source) for loaded, source in configured]
    else:
        reports = load_demo_reports(registry, fixture)
    rendered = report_json(reports) if json_output else report_text(reports)
    if output is None:
        print(rendered, end="")
    else:
        output.write_text(rendered, encoding="utf-8")
        print(f"Wrote bounded review report to {output}")
    return report_exit_code(reports)


def main() -> int:
    parser = argparse.ArgumentParser(description="Export and validate Sahayi Procedure Pack v1 data")
    subparsers = parser.add_subparsers(dest="command", required=True)

    export = subparsers.add_parser("export-schema")
    export.add_argument("--output", type=Path, default=default_schema_path())

    check = subparsers.add_parser("check-schema")
    check.add_argument("--schema", type=Path, default=default_schema_path())

    validate = subparsers.add_parser("validate")
    validate.add_argument("--pack-root", type=Path, default=default_pack_root())
    validate.add_argument("--file", type=Path)

    monitor = subparsers.add_parser("monitor", help="Run the one-shot, human-reviewed source change detector")
    monitor.add_argument("--pack-root", type=Path, default=default_pack_root())
    monitor.add_argument("--live", action="store_true", help="Retrieve exact allowlisted public source URLs once")
    monitor.add_argument("--acknowledge-live-public-source-check", action="store_true")
    monitor.add_argument("--source-id", action="append", default=[])
    monitor.add_argument("--fixture", type=Path)
    monitor.add_argument("--json", action="store_true")
    monitor.add_argument("--output", type=Path)

    args = parser.parse_args()
    if args.command == "export-schema":
        return export_schema(args.output)
    if args.command == "check-schema":
        return check_schema(args.schema)
    if args.command == "monitor":
        return monitor_sources(
            pack_root=args.pack_root,
            live=args.live,
            acknowledged=args.acknowledge_live_public_source_check,
            source_ids=args.source_id,
            fixture=args.fixture,
            json_output=args.json,
            output=args.output,
        )
    if args.file:
        return validate_file(args.file)
    return validate_packs(args.pack_root)


if __name__ == "__main__":
    raise SystemExit(main())

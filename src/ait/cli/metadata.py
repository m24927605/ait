from __future__ import annotations

from ._shared import *

from ait.metadata_bundle import export_metadata_bundle, import_metadata_bundle


def handle(args, repo_root: Path, parser=None) -> int:
    del parser
    try:
        if args.metadata_command == "export":
            payload = export_metadata_bundle(repo_root, output=args.output, dry_run=args.dry_run)
            _print_metadata_payload(payload, args.format)
            return 0
        if args.metadata_command == "import":
            payload = import_metadata_bundle(repo_root, input_path=args.input, dry_run=args.dry_run)
            _print_metadata_payload(payload, args.format)
            return 0 if payload.get("status") == "planned" else 2
    except ValueError as exc:
        payload = {"status": "error", "error": str(exc)}
        _print_metadata_payload(payload, args.format)
        return 2
    return 1


def _print_metadata_payload(payload: dict[str, object], output_format: str) -> None:
    if output_format == "json":
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        print(_format_metadata(payload))


def _format_metadata(payload: dict[str, object]) -> str:
    lines = ["AIT Metadata", f"status: {payload.get('status')}"]
    counts = payload.get("object_counts")
    if isinstance(counts, dict):
        for key, value in counts.items():
            lines.append(f"{key}: {value}")
    errors = payload.get("errors")
    if isinstance(errors, list) and errors:
        lines.append("Errors:")
        lines.extend(f"- {error}" for error in errors)
    return "\n".join(lines)

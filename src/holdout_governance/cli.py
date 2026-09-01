"""Command-line interface for Holdout research governance."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from . import __version__
from .contracts import build_report, validate_manifest


def _load_manifest(path: str) -> dict[str, Any]:
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected a JSON object: {path}")
    return value


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="gov",
        description="Fail-closed evidence checks for financial AI research.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    validate = sub.add_parser("validate", help="validate a research evidence manifest")
    validate.add_argument("--manifest", required=True, help="manifest JSON path")
    validate.add_argument("--json", action="store_true", help="machine-readable output")

    report = sub.add_parser("report", help="print a compact governance report")
    report.add_argument("--manifest", required=True, help="manifest JSON path")

    sub.add_parser("version", help="print version")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "version":
        print(__version__)
        return 0

    manifest = _load_manifest(args.manifest)
    if args.command == "validate":
        blockers = validate_manifest(manifest)
        if args.json:
            print(json.dumps({"passed": not blockers, "blockers": blockers}, indent=2))
        elif blockers:
            print("BLOCKED")
            for blocker in blockers:
                print(f" - {blocker}")
        else:
            print("PASS - research evidence manifest is complete")
        return 0 if not blockers else 1

    if args.command == "report":
        report = build_report(manifest)
        print(json.dumps(report, indent=2))
        return 0 if report["passed"] else 1

    parser.error(f"unknown command: {args.command}")
    return 2


if __name__ == "__main__":
    sys.exit(main())

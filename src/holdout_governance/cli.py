"""Command-line interface for Holdout research governance.

Subcommands:

- ``init``       generate policy.yml + gate-inputs.json + artifact.json
- ``check``      run required gates (optional), decide, write back
- ``report``     human-readable decision report (v1 or v0.2)
- ``validate``   legacy v1 research-manifest validation
- ``api``        serve the HTTP JSON API (stdlib, no extra deps)
- ``mcp``        serve the MCP stdio server (needs the [mcp] extra)
- ``version``    print version
"""

from __future__ import annotations

import argparse
import json
import sys

from . import __version__
from . import engine
from .contracts import validate_manifest
from .report import build_report_text, summary_json


def _emit_warnings(warnings: list[str]) -> None:
    for warning in warnings:
        print(f"warning: {warning}", file=sys.stderr)


def cmd_init(args: argparse.Namespace) -> int:
    result = engine.run_init(args.dir, kind=args.kind, name=args.name)
    if result.get("error"):
        print(f"error: {result['error']}", file=sys.stderr)
        return 1
    print(f"init: wrote {', '.join(result['files'])} in {args.dir}")
    print(f"policy_ref: {result['policy_ref']}  "
          "(matches policy.yml as written — re-hash after edits)")
    return 0


def cmd_check(args: argparse.Namespace) -> int:
    worst = 0
    for manifest in args.manifest:
        result = engine.run_check(manifest, policy=args.policy,
                                  gate_inputs=args.gate_inputs, kind=args.kind)
        if args.json:
            if result.get("error"):
                print(json.dumps({"manifest": manifest, "error": result["error"]}))
            else:
                print(json.dumps(summary_json(result["artifact"], result["policy_ref_ok"]),
                                 ensure_ascii=False, indent=2))
        else:
            if result.get("error"):
                print(f"error: {result['error']}", file=sys.stderr)
            else:
                _emit_warnings(result["warnings"])
                print(build_report_text(result["artifact"], result["policy_ref_ok"]))
        worst = max(worst, result["exit_code"])
    return worst


def cmd_report(args: argparse.Namespace) -> int:
    result = engine.run_report(args.manifest, policy=args.policy)
    if result.get("error"):
        print(f"error: {result['error']}", file=sys.stderr)
        return 2
    if result["v1"]:
        print(json.dumps(result["report"], indent=2))
        return result["exit_code"]
    if args.json:
        print(json.dumps(summary_json(result["artifact"], result["policy_ref_ok"]),
                         ensure_ascii=False, indent=2))
    else:
        print(build_report_text(result["artifact"], result["policy_ref_ok"]))
    return result["exit_code"]


def cmd_validate(args: argparse.Namespace) -> int:
    try:
        from .engine import _load_raw

        manifest = _load_raw(args.manifest)
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
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


def cmd_api(args: argparse.Namespace) -> int:
    from .api import run_server

    run_server(host=args.host, port=args.port)
    return 0


def cmd_mcp(args: argparse.Namespace) -> int:
    try:
        from .mcp_server import build_mcp_server
    except ImportError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    server = build_mcp_server()
    server.run(transport="stdio")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="gov",
        description="Fail-closed evidence checks for financial AI research.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    init = sub.add_parser("init", help="generate policy.yml, gate-inputs.json, artifact.json")
    init.add_argument("--dir", default=".", help="output directory (default: .)")
    init.add_argument(
        "--kind",
        default="research_conclusion",
        choices=["research_conclusion", "strategy_advice", "public_copy", "code"],
    )
    init.add_argument("--name", default=None, help="artifact id (default: generated)")

    check = sub.add_parser("check", help="run required gates, decide, write back")
    check.add_argument("--manifest", nargs="+", required=True, help="artifact JSON path(s)")
    check.add_argument("--policy", default=None, help="policy.yml path (default: next to manifest)")
    check.add_argument(
        "--gate-inputs",
        default=None,
        help="gate-inputs.json path (default: next to manifest, if present)",
    )
    check.add_argument("--kind", default=None, help="override artifact kind")
    check.add_argument("--json", action="store_true", help="machine-readable output")

    report = sub.add_parser("report", help="print a compact governance report")
    report.add_argument("--manifest", required=True, help="artifact JSON path")
    report.add_argument("--policy", default=None, help="policy.yml path (default: next to manifest)")
    report.add_argument("--json", action="store_true", help="machine-readable output")

    validate = sub.add_parser("validate", help="validate a v1 research evidence manifest")
    validate.add_argument("--manifest", required=True, help="manifest JSON path")
    validate.add_argument("--json", action="store_true", help="machine-readable output")

    api = sub.add_parser("api", help="serve the HTTP JSON API")
    api.add_argument("--host", default="127.0.0.1")
    api.add_argument("--port", type=int, default=8000)

    sub.add_parser("mcp", help="serve the MCP stdio server (agents)")

    sub.add_parser("version", help="print version")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "version":
        print(__version__)
        return 0
    if args.command == "init":
        return cmd_init(args)
    if args.command == "check":
        return cmd_check(args)
    if args.command == "report":
        return cmd_report(args)
    if args.command == "validate":
        return cmd_validate(args)
    if args.command == "api":
        return cmd_api(args)
    if args.command == "mcp":
        return cmd_mcp(args)
    parser.error(f"unknown command: {args.command}")
    return 2


if __name__ == "__main__":
    sys.exit(main())

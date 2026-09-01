"""Command-line interface for Holdout research governance.

Subcommands (v0.2 artifacts):

- ``init``                 generate policy.yml + gate-inputs.json + artifact.json
- ``check``                run required gates (optional), decide, write back
- ``report``               human-readable decision report
- ``validate``             legacy v1 research-manifest validation
- ``version``              print version
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from . import __version__
from ._schemas import (
    ARTIFACT_SCHEMA_VERSION,
    DEFAULT_POLICY,
    GATE_INPUTS_TEMPLATE,
)
from .artifact import is_v1_manifest, load_artifact, merge_gate_result, save_artifact
from .contracts import build_report, validate_manifest
from .decide import decide
from .policy import load_policy, sha256_file
from .report import build_report_text, summary_json
from .runners import run_gate

_EXIT = {"release": 0, "review_needed": 1, "block": 2}
_SAFETY = {
    "places_orders": False,
    "changes_trading_rules": False,
    "provides_investment_advice": False,
}


def _now() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# --------------------------------------------------------------------------
# v0.2: init / check / report
# --------------------------------------------------------------------------


def _load_raw_manifest(path: str) -> dict:
    """Load any JSON manifest (v1 or v0.2) without schema validation."""
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected a JSON object: {path}")
    return value


def _load_manifest_or_exit(manifest: str, *, v1_ok: bool) -> tuple[dict | None, int | None]:
    path = Path(manifest)
    try:
        raw = _load_raw_manifest(manifest)
    except Exception as exc:  # includes ValueError + JSONDecodeError
        print(f"error: cannot load artifact {manifest}: {exc}", file=sys.stderr)
        return None, 2
    if is_v1_manifest(raw):
        if v1_ok:
            return raw, None
        print(
            "error: this is a v1 research manifest — use 'gov validate' instead of 'gov check'",
            file=sys.stderr,
        )
        return None, 2
    try:
        artifact = load_artifact(path)
    except Exception as exc:
        print(f"error: cannot load artifact {manifest}: {exc}", file=sys.stderr)
        return None, 2
    if artifact.get("schema_version") != ARTIFACT_SCHEMA_VERSION:
        print(
            f"error: unsupported schema_version {artifact.get('schema_version')!r}",
            file=sys.stderr,
        )
        return None, 2
    return artifact, None


def cmd_init(args: argparse.Namespace) -> int:
    out = Path(args.dir)
    out.mkdir(parents=True, exist_ok=True)

    policy_path = out / "policy.yml"
    if policy_path.exists():
        policy_ref = sha256_file(policy_path)
    else:
        policy_path.write_text(DEFAULT_POLICY, encoding="utf-8")
        policy_ref = sha256_file(policy_path)

    gate_inputs = out / "gate-inputs.json"
    if not gate_inputs.exists():
        gate_inputs.write_text(GATE_INPUTS_TEMPLATE, encoding="utf-8")

    artifact_path = out / "artifact.json"
    if artifact_path.exists():
        print(f"artifact.json already exists: {artifact_path} (not overwritten)")
    else:
        artifact = {
            "schema_version": ARTIFACT_SCHEMA_VERSION,
            "artifact": {
                "id": args.name or f"artifact-{_now().replace(':', '').replace('+', 'Z')[:19]}",
                "kind": args.kind,
                "created_at": _now(),
            },
            "producer": {"type": "human"},
            "gates": [],
            "attachments": {},
            "review": {"status": "not_recorded", "reviewer": ""},
            "safety": dict(_SAFETY),
            "policy_ref": policy_ref,
            "decision": "pending",
            "missing": [],
        }
        save_artifact(artifact_path, artifact)

    print(f"init: wrote policy.yml, gate-inputs.json, artifact.json in {out}")
    print(f"policy_ref: {policy_ref}  (matches policy.yml as written — re-hash after edits)")
    return 0


def _load_gate_inputs(base: Path, arg: str | None) -> dict:
    path = Path(arg) if arg else base / "gate-inputs.json"
    if not path.exists():
        return {}
    value = json.loads(path.read_text(encoding="utf-8"))
    return value if isinstance(value, dict) else {}


def cmd_check(args: argparse.Namespace) -> int:
    base = Path(args.manifest).parent
    artifact, err = _load_manifest_or_exit(args.manifest, v1_ok=False)
    if artifact is None:
        return err  # type: ignore[return-value]

    policy_path = Path(args.policy) if args.policy else base / "policy.yml"
    if not policy_path.exists():
        print(f"error: policy not found: {policy_path} (generate with 'gov init')", file=sys.stderr)
        return 2
    try:
        policy = load_policy(policy_path)
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    policy_ok = artifact.get("policy_ref") == sha256_file(policy_path)
    if not policy_ok:
        print(
            f"warning: policy_ref mismatch — expected {sha256_file(policy_path)}",
            file=sys.stderr,
        )

    kind = args.kind or artifact["artifact"]["kind"]
    kinds = policy.get("kinds", {})
    if kind not in kinds:
        print(f"error: no policy for kind {kind!r}", file=sys.stderr)
        return 2

    gate_inputs = _load_gate_inputs(base, args.gate_inputs)
    for gate_id in kinds[kind].get("required_gates", []):
        if gate_id in gate_inputs:
            result = run_gate(gate_id, gate_inputs[gate_id], base)
            artifact = merge_gate_result(artifact, gate_id, result)

    outcome = decide(artifact, policy)
    artifact["decision"] = outcome["decision"]
    artifact["missing"] = outcome["missing"]
    if not policy_ok:
        artifact["decision"] = "block"
        artifact["missing"] = artifact["missing"] + ["policy:ref_mismatch"]

    save_artifact(args.manifest, artifact)

    if args.json:
        print(json.dumps(summary_json(artifact, policy_ok), ensure_ascii=False, indent=2))
    else:
        print(build_report_text(artifact, policy_ok))
    return _EXIT[artifact["decision"]]


def cmd_report(args: argparse.Namespace) -> int:
    artifact, err = _load_manifest_or_exit(args.manifest, v1_ok=True)
    if artifact is None:
        return err  # type: ignore[return-value]
    if is_v1_manifest(artifact):
        report = build_report(artifact)
        print(json.dumps(report, indent=2))
        return 0 if report["passed"] else 1

    base = Path(args.manifest).parent
    policy_path = Path(args.policy) if args.policy else base / "policy.yml"
    if policy_path.exists():
        try:
            policy = load_policy(policy_path)
            policy_ok = artifact.get("policy_ref") == sha256_file(policy_path)
            outcome = decide(artifact, policy)
            if not policy_ok:
                outcome = {
                    "decision": "block",
                    "missing": outcome["missing"] + ["policy:ref_mismatch"],
                    "warns": outcome["warns"],
                }
        except Exception as exc:
            policy_ok, outcome = False, {
                "decision": "block",
                "missing": [f"policy:error:{exc}"],
                "warns": [],
            }
    else:
        policy_ok, outcome = False, {"decision": "block", "missing": ["policy:file"], "warns": []}
    artifact["decision"] = outcome["decision"]
    artifact["missing"] = outcome["missing"]
    if args.json:
        print(json.dumps(summary_json(artifact, policy_ok), ensure_ascii=False, indent=2))
    else:
        print(build_report_text(artifact, policy_ok))
    return _EXIT.get(artifact["decision"], 2)


# --------------------------------------------------------------------------
# legacy v1
# --------------------------------------------------------------------------


def _load_manifest(path: str) -> dict[str, Any]:
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected a JSON object: {path}")
    return value


def cmd_validate(args: argparse.Namespace) -> int:
    try:
        manifest = _load_manifest(args.manifest)
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


# --------------------------------------------------------------------------


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
    check.add_argument("--manifest", required=True, help="artifact JSON path")
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
    parser.error(f"unknown command: {args.command}")
    return 2


if __name__ == "__main__":
    sys.exit(main())

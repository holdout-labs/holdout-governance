"""Shared gov pipelines (check / report / init), used by the CLI, the HTTP
API and the MCP server so all three surfaces cannot drift apart.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ._schemas import ARTIFACT_SCHEMA_VERSION, DEFAULT_POLICY, GATE_INPUTS_TEMPLATE
from .artifact import is_v1_manifest, load_artifact, merge_gate_result, save_artifact
from .contracts import build_report
from .decide import decide
from .policy import load_policy, sha256_file
from .runners import run_gate

_EXIT = {"release": 0, "review_needed": 1, "block": 2}
_SAFETY = {
    "places_orders": False,
    "changes_trading_rules": False,
    "provides_investment_advice": False,
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _load_raw(path: str) -> dict:
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected a JSON object: {path}")
    return value


def _load_gate_inputs(base: Path, arg: str | None) -> dict:
    path = Path(arg) if arg else base / "gate-inputs.json"
    if not path.exists():
        return {}
    value = json.loads(path.read_text(encoding="utf-8"))
    return value if isinstance(value, dict) else {}


def _gate_summary(artifact: dict) -> list[dict]:
    return [
        {
            "gate_id": g["gate_id"],
            "tool": g.get("tool", ""),
            "status": g["status"],
            "report_ref": g.get("report_ref", ""),
        }
        for g in artifact.get("gates", [])
    ]


# --------------------------------------------------------------------------
# init
# --------------------------------------------------------------------------


def run_init(directory: str = ".", kind: str = "research_conclusion",
             name: str | None = None) -> dict[str, Any]:
    """Scaffold policy.yml + gate-inputs.json + artifact.json in `directory`."""
    out = Path(directory)
    out.mkdir(parents=True, exist_ok=True)
    files: list[str] = []

    policy_path = out / "policy.yml"
    if policy_path.exists():
        policy_ref = sha256_file(policy_path)
    else:
        policy_path.write_text(DEFAULT_POLICY, encoding="utf-8")
        policy_ref = sha256_file(policy_path)
        files.append("policy.yml")

    gate_inputs = out / "gate-inputs.json"
    if not gate_inputs.exists():
        gate_inputs.write_text(GATE_INPUTS_TEMPLATE, encoding="utf-8")
        files.append("gate-inputs.json")

    artifact_path = out / "artifact.json"
    if artifact_path.exists():
        return {"error": f"artifact.json already exists: {artifact_path} (not overwritten)",
                "files": files, "policy_ref": policy_ref, "created": False}
    artifact = {
        "schema_version": ARTIFACT_SCHEMA_VERSION,
        "artifact": {
            "id": name or f"artifact-{_now().replace(':', '').replace('+', 'Z')[:19]}",
            "kind": kind,
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
    files.append("artifact.json")
    return {"error": None, "files": files, "policy_ref": policy_ref, "created": True}


# --------------------------------------------------------------------------
# check
# --------------------------------------------------------------------------


def run_check(manifest: str, policy: str | None = None, gate_inputs: str | None = None,
              kind: str | None = None) -> dict[str, Any]:
    """Run the full gate chain on one v0.2 artifact and write it back.

    Returns a dict with ``error``/``warnings``/``exit_code``/``decision``/
    ``missing``/``gates``/``policy_ref_ok``/``artifact``.
    """
    result: dict[str, Any] = {
        "error": None,
        "warnings": [],
        "exit_code": 2,
        "decision": "block",
        "missing": [],
        "gates": [],
        "policy_ref_ok": False,
    }
    base = Path(manifest).parent

    try:
        raw = _load_raw(manifest)
    except Exception as exc:  # JSONDecodeError, ValueError, OSError
        result["error"] = f"cannot load artifact {manifest}: {exc}"
        return result
    if is_v1_manifest(raw):
        result["error"] = ("this is a v1 research manifest - use 'gov validate' "
                           "instead of 'gov check'")
        return result
    try:
        artifact = load_artifact(manifest)
    except Exception as exc:
        result["error"] = f"cannot load artifact {manifest}: {exc}"
        return result
    if artifact.get("schema_version") != ARTIFACT_SCHEMA_VERSION:
        result["error"] = f"unsupported schema_version {artifact.get('schema_version')!r}"
        return result

    policy_path = Path(policy) if policy else base / "policy.yml"
    if not policy_path.exists():
        result["error"] = f"policy not found: {policy_path} (generate with 'gov init')"
        return result
    try:
        loaded_policy = load_policy(policy_path)
    except Exception as exc:
        result["error"] = str(exc)
        return result

    policy_ok = artifact.get("policy_ref") == sha256_file(policy_path)
    if not policy_ok:
        result["warnings"].append(f"policy_ref mismatch - expected {sha256_file(policy_path)}")

    kinds = loaded_policy.get("kinds", {})
    artifact_kind = kind or artifact["artifact"]["kind"]
    if artifact_kind not in kinds:
        result["error"] = f"no policy for kind {artifact_kind!r}"
        return result

    inputs = _load_gate_inputs(base, gate_inputs)
    for gate_id in kinds[artifact_kind].get("required_gates", []):
        if gate_id in inputs:
            outcome = run_gate(gate_id, inputs[gate_id], base)
            artifact = merge_gate_result(artifact, gate_id, outcome)

    verdict = decide(artifact, loaded_policy)
    artifact["decision"] = verdict["decision"]
    artifact["missing"] = verdict["missing"]
    if not policy_ok:
        artifact["decision"] = "block"
        artifact["missing"] = artifact["missing"] + ["policy:ref_mismatch"]
    save_artifact(manifest, artifact)

    result.update(
        exit_code=_EXIT[artifact["decision"]],
        decision=artifact["decision"],
        missing=artifact["missing"],
        gates=_gate_summary(artifact),
        policy_ref_ok=policy_ok,
        artifact=artifact,
    )
    return result


# --------------------------------------------------------------------------
# attach
# --------------------------------------------------------------------------


def run_attach(
    manifest: str,
    *,
    gate: str | None = None,
    status: str | None = None,
    tool: str = "",
    report_ref: str = "",
    tool_version: str = "",
    reason: str | None = None,
    attachments: dict[str, str] | None = None,
    review: str | None = None,
    reviewer: str = "",
    declarations: dict[str, bool] | None = None,
) -> dict[str, Any]:
    """Attach evidence to a v0.2 artifact (agent-facing mutation step).

    One gate per call (call repeatedly for more). Attaching evidence resets
    ``decision`` to ``pending`` - the old decision is stale by definition and
    must be recomputed by ``gov check``.
    """
    result: dict[str, Any] = {"error": None, "exit_code": 0}
    try:
        raw = _load_raw(manifest)
    except Exception as exc:
        result["error"] = f"cannot load artifact {manifest}: {exc}"
        result["exit_code"] = 2
        return result
    if is_v1_manifest(raw):
        result["error"] = "this is a v1 research manifest - use 'gov validate'"
        result["exit_code"] = 2
        return result
    try:
        artifact = load_artifact(manifest)
    except Exception as exc:
        result["error"] = f"cannot load artifact {manifest}: {exc}"
        result["exit_code"] = 2
        return result

    valid_statuses = ("pass", "fail", "warn", "not_run")
    if gate is not None:
        if status not in valid_statuses:
            result["error"] = f"invalid gate status {status!r} (expected one of {valid_statuses})"
            result["exit_code"] = 2
            return result
        artifact = merge_gate_result(artifact, gate, {
            "status": status,
            "tool": tool or "manual",
            "report_ref": report_ref,
            "tool_version": tool_version,
            "run_at": _now(),
            "reason": reason,
        })

    if attachments:
        existing = artifact.get("attachments", {}) or {}
        existing.update(attachments)
        artifact["attachments"] = existing

    if declarations:
        existing = artifact.get("declarations", {}) or {}
        existing.update(declarations)
        artifact["declarations"] = existing

    if review is not None:
        if review not in ("approved", "not_recorded"):
            result["error"] = f"invalid review status {review!r} (expected approved|not_recorded)"
            result["exit_code"] = 2
            return result
        artifact["review"] = {"status": review, "reviewer": reviewer}

    # evidence changed -> any previous decision is stale
    artifact["decision"] = "pending"
    artifact["missing"] = []
    save_artifact(manifest, artifact)

    result.update(
        gates=_gate_summary(artifact),
        attachments=artifact.get("attachments", {}),
        declarations=artifact.get("declarations", {}),
        review=artifact.get("review", {}),
    )
    return result


# --------------------------------------------------------------------------
# report
# --------------------------------------------------------------------------


def run_report(manifest: str, policy: str | None = None) -> dict[str, Any]:
    """Read-only assessment of a manifest (v1 or v0.2). Never runs gates."""
    result: dict[str, Any] = {"error": None, "warnings": [], "exit_code": 2, "v1": False}
    try:
        raw = _load_raw(manifest)
    except Exception as exc:
        result["error"] = f"cannot load artifact {manifest}: {exc}"
        return result
    if is_v1_manifest(raw):
        report = build_report(raw)
        result.update(v1=True, passed=report["passed"], report=report,
                      exit_code=0 if report["passed"] else 1)
        return result
    try:
        artifact = load_artifact(manifest)
    except Exception as exc:
        result["error"] = f"cannot load artifact {manifest}: {exc}"
        return result

    base = Path(manifest).parent
    policy_path = Path(policy) if policy else base / "policy.yml"
    policy_ok = False
    if policy_path.exists():
        try:
            loaded_policy = load_policy(policy_path)
            policy_ok = artifact.get("policy_ref") == sha256_file(policy_path)
            outcome = decide(artifact, loaded_policy)
            if not policy_ok:
                outcome = {"decision": "block",
                           "missing": outcome["missing"] + ["policy:ref_mismatch"],
                           "warns": outcome["warns"]}
        except Exception as exc:
            policy_ok, outcome = False, {"decision": "block",
                                         "missing": [f"policy:error:{exc}"], "warns": []}
    else:
        outcome = {"decision": "block", "missing": ["policy:file"], "warns": []}
    artifact["decision"] = outcome["decision"]
    artifact["missing"] = outcome["missing"]
    result.update(
        v1=False,
        decision=artifact["decision"],
        missing=artifact["missing"],
        gates=_gate_summary(artifact),
        policy_ref_ok=policy_ok,
        exit_code=_EXIT.get(artifact["decision"], 2),
        artifact=artifact,
    )
    return result

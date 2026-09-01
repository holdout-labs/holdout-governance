"""Human-readable v0.2 governance report."""

from __future__ import annotations

from typing import Any

_MARK = {"pass": "PASS", "fail": "FAIL", "warn": "WARN", "not_run": "N/A"}


def build_report_text(artifact: dict, policy_ok: bool, policy_note: str = "") -> str:
    info = artifact["artifact"]
    producer = artifact.get("producer", {}) or {}
    review = artifact.get("review", {}) or {}
    lines: list[str] = []
    lines.append("== Holdout governance report ==")
    lines.append(f"artifact: {info['id']}  kind: {info['kind']}  created: {info['created_at']}")
    lines.append(
        f"producer: {producer.get('type', 'unknown')}"
        + (f" ({producer.get('model_id', '')})" if producer.get("type") == "ai" else "")
    )
    lines.append(f"review: {review.get('status', 'not_recorded')}")
    lines.append(f"policy_ref: {'OK' if policy_ok else 'MISMATCH'} {policy_note}".rstrip())
    attachments = artifact.get("attachments", {}) or {}
    if attachments:
        lines.append("attachments:")
        for key, value in attachments.items():
            lines.append(f"  {key}: {value}")
    declarations = artifact.get("declarations", {}) or {}
    if declarations:
        lines.append("declarations:")
        for key, value in declarations.items():
            lines.append(f"  {key}: {str(value).lower()}")
    lines.append("gates:")
    for gate in artifact.get("gates", []):
        mark = _MARK.get(gate.get("status", "not_run"), "?")
        ref = gate.get("report_ref", "")
        lines.append(
            f"  [{mark}] {gate['gate_id']} ({gate.get('tool', '')}"
            + (f" v{gate['tool_version']}" if gate.get("tool_version") else "")
            + f", {ref})"
        )
        if gate.get("reason"):
            lines.append(f"         reason: {gate['reason']}")
    lines.append(f"decision: {artifact.get('decision', 'unknown').upper()}")
    missing = artifact.get("missing", [])
    if missing:
        lines.append("missing:")
        lines.extend(f"  - {item}" for item in missing)
    warns = [g for g in artifact.get("gates", []) if g.get("status") == "warn"]
    if warns:
        lines.append("warnings:")
        lines.extend(f"  - gate:{g['gate_id']}" for g in warns)
    return "\n".join(lines)


def summary_json(artifact: dict, policy_ok: bool) -> dict[str, Any]:
    return {
        "schema_version": "holdout_governance.report.v0.2",
        "artifact_id": artifact["artifact"]["id"],
        "kind": artifact["artifact"]["kind"],
        "policy_ref_ok": policy_ok,
        "decision": artifact.get("decision", "unknown"),
        "missing": artifact.get("missing", []),
        "gates": [
            {"gate_id": g["gate_id"], "tool": g.get("tool", ""), "status": g["status"]}
            for g in artifact.get("gates", [])
        ],
    }

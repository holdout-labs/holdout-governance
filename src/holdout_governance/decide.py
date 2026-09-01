"""The v0.2 decision function (PRD §3.3).

    decision = release
    for gate in policy[kind].required_gates:
        status = artifact.gates[gate].status          # missing counts as not_run
        if status in (fail, not_run):  decision = block; missing.append(gate)
        if status == warn:             decision = max(decision, review_needed)
    for att in policy[kind].required_attachments:
        if att not in artifact.attachments:  decision = block; missing.append(att)
    if producer.type == "ai" and review.status != "approved":  decision = block
    # kinds with severity warn/info only downgrade, never hard-block
"""

from __future__ import annotations

from typing import Any

_ORDER = {"release": 0, "review_needed": 1, "block": 2}


def _worse(a: str, b: str) -> str:
    return a if _ORDER[a] >= _ORDER[b] else b


def decide(artifact: dict, policy: dict) -> dict[str, Any]:
    """Return {decision, missing, warns} for a v0.2 artifact under a policy."""
    kind = artifact["artifact"]["kind"]
    kinds = policy.get("kinds", {})
    if kind not in kinds:
        return {"decision": "block", "missing": [f"policy:kind:{kind}"], "warns": []}

    spec = kinds[kind]
    severity = spec.get("severity", "block")
    gates = {g.get("gate_id"): g for g in artifact.get("gates", [])}
    attachments = artifact.get("attachments", {}) or {}
    review = artifact.get("review", {}) or {}
    producer = artifact.get("producer", {}) or {}

    decision = "release"
    missing: list[str] = []
    warns: list[str] = []

    for gate_id in spec.get("required_gates", []):
        status = gates.get(gate_id, {}).get("status", "not_run")
        if status in ("fail", "not_run"):
            decision = _worse(decision, "block" if severity == "block" else "review_needed")
            missing.append(f"gate:{gate_id}")
        elif status == "warn":
            decision = _worse(decision, "review_needed")
            warns.append(f"gate:{gate_id}")

    for att in spec.get("required_attachments", []):
        if att not in attachments:
            decision = _worse(decision, "block")
            missing.append(f"attachment:{att}")

    # conditional attachments: e.g. public copy that declares return figures
    # must attach limitations (PRD scenario 3)
    declarations = artifact.get("declarations", {}) or {}
    for cond in spec.get("conditional_attachments", []):
        when = cond.get("when", {}) or {}
        if all(declarations.get(key) is value for key, value in when.items()):
            for att in cond.get("require", []):
                if att not in attachments:
                    decision = _worse(decision, "block")
                    missing.append(f"attachment:{att}")

    if producer.get("type") == "ai" and review.get("status") != "approved":
        decision = _worse(decision, "block")
        missing.append("review:approved")
    if spec.get("requires_review") and review.get("status") != "approved":
        decision = _worse(decision, "block")
        missing.append("review:approved")

    return {"decision": decision, "missing": missing, "warns": warns}

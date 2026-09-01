"""Validation and reporting for a financial AI research evidence manifest."""

from __future__ import annotations

from datetime import datetime
from typing import Any

SCHEMA_VERSION = "holdout_governance.research_manifest.v1"
REQUIRED_CHECKS = {"data_integrity", "temporal_integrity", "evidence_integrity"}
READ_ONLY_SAFETY = {
    "places_orders": False,
    "changes_trading_rules": False,
    "provides_investment_advice": False,
}


def _parse_timestamp(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    return parsed if parsed.tzinfo is not None else None


def validate_manifest(value: dict[str, Any]) -> list[str]:
    blockers: list[str] = []
    if value.get("schema_version") != SCHEMA_VERSION:
        blockers.append(f"schema_version must be {SCHEMA_VERSION!r}")
    if not isinstance(value.get("research_id"), str) or not value["research_id"].strip():
        blockers.append("research_id must be a non-empty string")

    scope = value.get("scope")
    cutoff = None
    if not isinstance(scope, dict):
        blockers.append("scope must be an object")
    else:
        cutoff = _parse_timestamp(scope.get("decision_cutoff"))
        if scope.get("purpose") != "research_only":
            blockers.append("scope.purpose must be 'research_only'")
        if cutoff is None:
            blockers.append("scope.decision_cutoff must be an ISO timestamp with timezone")

    inputs = value.get("inputs")
    if not isinstance(inputs, list) or not inputs:
        blockers.append("inputs must contain at least one evidence artifact")
    else:
        for index, artifact in enumerate(inputs):
            if not isinstance(artifact, dict):
                blockers.append(f"inputs[{index}] must be an object")
                continue
            artifact_id = artifact.get("artifact_id")
            if not isinstance(artifact_id, str) or not artifact_id.startswith("sha256:"):
                blockers.append(f"inputs[{index}].artifact_id must start with 'sha256:'")
            as_of = _parse_timestamp(artifact.get("as_of"))
            if as_of is None:
                blockers.append(f"inputs[{index}].as_of must be an ISO timestamp with timezone")
            elif cutoff is not None and as_of > cutoff:
                blockers.append(f"inputs[{index}].as_of is later than scope.decision_cutoff")

    safety = value.get("safety")
    if not isinstance(safety, dict):
        blockers.append("safety must be an object")
    else:
        for field, expected in READ_ONLY_SAFETY.items():
            if safety.get(field) is not expected:
                blockers.append(f"safety.{field} must be {expected!r}")

    checks = value.get("checks")
    found_checks: set[str] = set()
    if not isinstance(checks, list):
        blockers.append("checks must be a list")
    else:
        for index, check in enumerate(checks):
            if not isinstance(check, dict):
                blockers.append(f"checks[{index}] must be an object")
                continue
            check_id = check.get("check_id")
            if isinstance(check_id, str):
                found_checks.add(check_id)
            if check.get("status") != "passed":
                blockers.append(f"checks[{index}] must have status 'passed'")
        for required in sorted(REQUIRED_CHECKS - found_checks):
            blockers.append(f"checks must include {required!r}")

    agent = value.get("agent")
    if not isinstance(agent, dict):
        blockers.append("agent must be an object")
    elif agent.get("used") is True:
        for field in ("model_id", "prompt_version"):
            if not isinstance(agent.get(field), str) or not agent[field].strip():
                blockers.append(f"agent.{field} is required when agent.used is true")
        review = value.get("review")
        if not isinstance(review, dict) or review.get("status") != "approved":
            blockers.append("review.status must be 'approved' for AI-assisted research")
    elif agent.get("used") is not False:
        blockers.append("agent.used must be true or false")

    if value.get("conclusion") != "research_only":
        blockers.append("conclusion must be 'research_only'")
    return blockers


def build_report(value: dict[str, Any]) -> dict[str, Any]:
    blockers = validate_manifest(value)
    agent = value.get("agent") if isinstance(value.get("agent"), dict) else {}
    review = value.get("review") if isinstance(value.get("review"), dict) else {}
    return {
        "schema_version": "holdout_governance.report.v1",
        "research_id": value.get("research_id"),
        "verdict": "PASS - research evidence manifest is complete"
        if not blockers
        else "BLOCKED - research evidence manifest is incomplete",
        "passed": not blockers,
        "agent_used": agent.get("used"),
        "review_status": review.get("status", "not_recorded"),
        "blockers": blockers,
        "safety": READ_ONLY_SAFETY,
    }

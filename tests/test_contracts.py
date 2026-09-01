from __future__ import annotations

import json
from pathlib import Path

from holdout_governance.contracts import build_report, validate_manifest

EXAMPLE = Path(__file__).resolve().parents[1] / "examples" / "ai-research-manifest.json"


def load_example() -> dict:
    return json.loads(EXAMPLE.read_text(encoding="utf-8"))


def test_valid_ai_research_manifest_passes() -> None:
    assert validate_manifest(load_example()) == []


def test_future_input_is_blocked() -> None:
    manifest = load_example()
    manifest["inputs"][0]["as_of"] = "2026-09-01T15:01:00+08:00"
    assert "inputs[0].as_of is later than scope.decision_cutoff" in validate_manifest(manifest)


def test_timestamp_must_include_timezone() -> None:
    manifest = load_example()
    manifest["scope"]["decision_cutoff"] = "2026-09-01T15:00:00"
    assert "scope.decision_cutoff must be an ISO timestamp with timezone" in validate_manifest(
        manifest
    )


def test_ai_research_requires_human_approval() -> None:
    manifest = load_example()
    manifest["review"]["status"] = "pending"
    assert "review.status must be 'approved' for AI-assisted research" in validate_manifest(manifest)


def test_research_manifest_cannot_enable_orders() -> None:
    manifest = load_example()
    manifest["safety"]["places_orders"] = True
    assert "safety.places_orders must be False" in validate_manifest(manifest)


def test_report_is_blocked_when_required_evidence_is_missing() -> None:
    manifest = load_example()
    manifest["checks"] = [
        check for check in manifest["checks"] if check["check_id"] != "evidence_integrity"
    ]
    report = build_report(manifest)
    assert report["passed"] is False
    assert "checks must include 'evidence_integrity'" in report["blockers"]

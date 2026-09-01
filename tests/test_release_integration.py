"""Release integration: CI workflow / action / pre-commit hook metadata and
the multi-manifest CLI path the pre-commit hook relies on."""

from __future__ import annotations

import json
from pathlib import Path

import yaml

from holdout_governance._schemas import ARTIFACT_SCHEMA_VERSION, DEFAULT_POLICY
from holdout_governance.cli import main
from holdout_governance.policy import sha256_file

from m1_scenarios import build

REPO = Path(__file__).resolve().parents[1]


def test_ci_workflow_yaml_is_valid() -> None:
    data = yaml.safe_load((REPO / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8"))
    assert "test" in data["jobs"]
    assert "cli-smoke" in data["jobs"]
    assert data["jobs"]["cli-smoke"]["steps"][-2]["run"].count("gov check") >= 1


def test_composite_action_metadata_is_valid() -> None:
    data = yaml.safe_load((REPO / ".github" / "actions" / "gov-check" / "action.yml")
                          .read_text(encoding="utf-8"))
    assert data["runs"]["using"] == "composite"
    assert "manifest" in data["inputs"]
    assert "gov check" in data["runs"]["steps"][-1]["run"]


def test_pre_commit_hooks_metadata_is_valid() -> None:
    hooks = yaml.safe_load((REPO / ".pre-commit-hooks.yaml").read_text(encoding="utf-8"))
    assert hooks[0]["id"] == "gov-check"
    assert hooks[0]["entry"] == "gov check --manifest"
    assert hooks[0]["language"] == "python"


def _write_release_artifact(d: Path) -> None:
    d.mkdir()
    (d / "policy.yml").write_text(DEFAULT_POLICY, encoding="utf-8")
    artifact = {
        "schema_version": ARTIFACT_SCHEMA_VERSION,
        "artifact": {"id": d.name, "kind": "research_conclusion",
                     "created_at": "2026-09-01T12:00:00+00:00"},
        "producer": {"type": "human"},
        "gates": [
            {"gate_id": g, "tool": "recorded", "status": "pass", "report_ref": "sha256:recorded"}
            for g in ("data_integrity", "pit_integrity", "temporal_integrity", "evidence_integrity")
        ],
        "attachments": {},
        "review": {"status": "approved", "reviewer": "research-owner"},
        "safety": {"places_orders": False, "changes_trading_rules": False,
                   "provides_investment_advice": False},
        "policy_ref": sha256_file(d / "policy.yml"),
        "decision": "pending",
        "missing": [],
    }
    (d / "artifact.json").write_text(json.dumps(artifact, indent=2), encoding="utf-8")


def test_check_multi_manifest_worst_decision_wins(tmp_path, monkeypatch) -> None:
    """pre-commit passes several artifact.json paths; one block blocks all."""
    clean = tmp_path / "clean"
    _write_release_artifact(clean)
    defect = tmp_path / "defect"
    defect.mkdir()
    build(defect, "no_evidence_record")
    monkeypatch.chdir(tmp_path)

    code = main(["check", "--manifest", "clean/artifact.json", "defect/artifact.json"])
    assert code == 2

    clean_artifact = json.loads((clean / "artifact.json").read_text(encoding="utf-8"))
    assert clean_artifact["decision"] == "release"

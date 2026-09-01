"""v0.2 CLI tests: init / check / report lifecycle."""

from __future__ import annotations

import json

from holdout_governance._schemas import ARTIFACT_SCHEMA_VERSION, DEFAULT_POLICY
from holdout_governance.cli import main
from holdout_governance.policy import sha256_file

V1_EXAMPLE = """
{
  "schema_version": "holdout_governance.research_manifest.v1",
  "research_id": "momentum-oos-review-2026-09-01",
  "scope": {
    "purpose": "research_only",
    "decision_cutoff": "2026-09-01T15:00:00+08:00"
  },
  "inputs": [
    {
      "artifact_id": "sha256:38d7db75548d1810113970802329252788f03f1f9390f5cf2355f76e3844c291",
      "source": "approved daily-bar snapshot",
      "as_of": "2026-09-01T15:00:00+08:00"
    }
  ],
  "checks": [
    {"check_id": "data_integrity", "tool": "ashare-data-immunity", "status": "passed"},
    {"check_id": "temporal_integrity", "tool": "lookahead-free", "status": "passed"},
    {"check_id": "evidence_integrity", "tool": "falsification-ledger", "status": "passed"},
    {"check_id": "statistical_quality", "tool": "factor-qc", "status": "passed"}
  ],
  "agent": {"used": true, "model_id": "research-agent-1", "prompt_version": "2026-09-01.1"},
  "review": {"status": "approved", "reviewer": "research-owner"},
  "safety": {"places_orders": false, "changes_trading_rules": false, "provides_investment_advice": false},
  "conclusion": "research_only"
}
"""


def _clean_artifact(tmp_path, *, policy_mutator=None) -> None:
    (tmp_path / "policy.yml").write_text(DEFAULT_POLICY, encoding="utf-8")
    policy_path = tmp_path / "policy.yml"
    policy_ref = sha256_file(policy_path)
    if policy_mutator:
        policy_mutator(policy_path)
    artifact = {
        "schema_version": ARTIFACT_SCHEMA_VERSION,
        "artifact": {"id": "clean-1", "kind": "research_conclusion",
                     "created_at": "2026-09-01T12:00:00+00:00"},
        "producer": {"type": "human"},
        "gates": [
            {"gate_id": "data_integrity", "tool": "ashare-data-immunity", "status": "pass",
             "report_ref": "sha256:recorded", "tool_version": "0.1.1"},
            {"gate_id": "pit_integrity", "tool": "pit-adjuster", "status": "pass",
             "report_ref": "sha256:recorded", "tool_version": "0.1.1"},
            {"gate_id": "temporal_integrity", "tool": "lookahead-free", "status": "pass",
             "report_ref": "sha256:recorded", "tool_version": "0.1.1"},
            {"gate_id": "evidence_integrity", "tool": "falsification-ledger", "status": "pass",
             "report_ref": "sha256:recorded", "tool_version": "0.1.1"},
        ],
        "attachments": {},
        "review": {"status": "approved", "reviewer": "research-owner"},
        "safety": {"places_orders": False, "changes_trading_rules": False,
                   "provides_investment_advice": False},
        "policy_ref": policy_ref,
        "decision": "pending",
        "missing": [],
    }
    (tmp_path / "artifact.json").write_text(json.dumps(artifact, indent=2), encoding="utf-8")


def test_init_writes_three_files(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    assert main(["init", "--dir", str(tmp_path), "--name", "m1-demo"]) == 0
    for name in ("policy.yml", "gate-inputs.json", "artifact.json"):
        assert (tmp_path / name).exists()
    artifact = json.loads((tmp_path / "artifact.json").read_text(encoding="utf-8"))
    assert artifact["artifact"]["id"] == "m1-demo"
    assert artifact["artifact"]["kind"] == "research_conclusion"
    assert artifact["policy_ref"] == sha256_file(tmp_path / "policy.yml")
    assert (tmp_path / "policy.yml").read_text(encoding="utf-8") == DEFAULT_POLICY


def test_check_releases_on_recorded_evidence(tmp_path, monkeypatch) -> None:
    _clean_artifact(tmp_path)
    monkeypatch.chdir(tmp_path)
    assert main(["check", "--manifest", "artifact.json"]) == 0
    artifact = json.loads((tmp_path / "artifact.json").read_text(encoding="utf-8"))
    assert artifact["decision"] == "release"
    assert artifact["missing"] == []


def test_check_policy_ref_mismatch_blocks(tmp_path, monkeypatch) -> None:
    _clean_artifact(tmp_path, policy_mutator=lambda p: p.write_text(
        DEFAULT_POLICY + "  # edited\n", encoding="utf-8"))
    monkeypatch.chdir(tmp_path)
    assert main(["check", "--manifest", "artifact.json"]) == 2
    artifact = json.loads((tmp_path / "artifact.json").read_text(encoding="utf-8"))
    assert artifact["decision"] == "block"
    assert "policy:ref_mismatch" in artifact["missing"]


def test_check_rejects_v1_manifest(tmp_path) -> None:
    (tmp_path / "manifest.json").write_text(V1_EXAMPLE, encoding="utf-8")
    assert main(["check", "--manifest", str(tmp_path / "manifest.json")]) == 2


def test_check_rejects_invalid_artifact(tmp_path) -> None:
    (tmp_path / "artifact.json").write_text("{}", encoding="utf-8")
    assert main(["check", "--manifest", str(tmp_path / "artifact.json")]) == 2


def test_check_unknown_kind_rejected(tmp_path, monkeypatch) -> None:
    _clean_artifact(tmp_path)
    monkeypatch.chdir(tmp_path)
    assert main(["check", "--manifest", "artifact.json", "--kind", "quantum"]) == 2


def test_report_human_and_json(tmp_path, monkeypatch, capsys) -> None:
    _clean_artifact(tmp_path)
    monkeypatch.chdir(tmp_path)
    assert main(["report", "--manifest", "artifact.json"]) == 0
    out = capsys.readouterr().out
    assert "decision: RELEASE" in out
    assert "gates:" in out

    assert main(["report", "--manifest", "artifact.json", "--json"]) == 0
    body = json.loads(capsys.readouterr().out)
    assert body["decision"] == "release"
    assert body["artifact_id"] == "clean-1"


def test_report_v1_manifest_still_works(tmp_path) -> None:
    (tmp_path / "manifest.json").write_text(V1_EXAMPLE, encoding="utf-8")
    assert main(["report", "--manifest", str(tmp_path / "manifest.json")]) == 0

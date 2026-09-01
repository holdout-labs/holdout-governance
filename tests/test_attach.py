"""gov attach tests: evidence mutation, decision reset, agent workflow."""

from __future__ import annotations

import json

from holdout_governance.cli import main

from m1_scenarios import build as build_m1
from m2_scenarios import build as build_m2


def _load(d, name="artifact.json") -> dict:
    return json.loads((d / name).read_text(encoding="utf-8"))


def test_attach_gate_records_and_resets_decision(tmp_path, monkeypatch) -> None:
    d = tmp_path / "defect"
    d.mkdir()
    build_m1(d, "no_evidence_record")
    monkeypatch.chdir(d)

    assert main(["attach", "--manifest", "artifact.json",
                 "--gate", "evidence_integrity", "--status", "pass",
                 "--tool", "falsification-ledger", "--report-ref", "sha256:abc"]) == 0

    artifact = _load(d)
    gates = {g["gate_id"]: g for g in artifact["gates"]}
    assert gates["evidence_integrity"]["status"] == "pass"
    assert gates["evidence_integrity"]["tool"] == "falsification-ledger"
    assert gates["evidence_integrity"]["report_ref"] == "sha256:abc"
    assert artifact["decision"] == "pending"  # stale decision invalidated
    assert artifact["missing"] == []


def test_attach_attachment_and_declaration(tmp_path, monkeypatch) -> None:
    d = tmp_path / "copy"
    d.mkdir()
    build_m2(d, "copy_missing_sources")
    monkeypatch.chdir(d)

    assert main(["attach", "--manifest", "artifact.json",
                 "--attachment", "sources=docs/sources.md",
                 "--attachment", "limitations=docs/limitations.md",
                 "--declaration", "contains_returns=true"]) == 0

    artifact = _load(d)
    assert artifact["attachments"]["sources"] == "docs/sources.md"
    assert artifact["attachments"]["limitations"] == "docs/limitations.md"
    assert artifact["declarations"] == {"contains_returns": True}


def test_attach_review(tmp_path, monkeypatch) -> None:
    d = tmp_path / "review"
    d.mkdir()
    build_m1(d, "ai_without_approval")
    monkeypatch.chdir(d)

    assert main(["attach", "--manifest", "artifact.json",
                 "--review", "approved", "--reviewer", "research-owner"]) == 0
    assert _load(d)["review"] == {"status": "approved", "reviewer": "research-owner"}


def test_attach_invalid_status_rejected(tmp_path, monkeypatch) -> None:
    import pytest

    d = tmp_path / "x"
    d.mkdir()
    build_m1(d, "no_evidence_record")
    monkeypatch.chdir(d)

    with pytest.raises(SystemExit) as exc_info:
        main(["attach", "--manifest", "artifact.json",
              "--gate", "evidence_integrity", "--status", "maybe"])
    assert exc_info.value.code == 2


def test_attach_v1_manifest_rejected(tmp_path) -> None:
    from test_cli_v02 import V1_EXAMPLE

    (tmp_path / "manifest.json").write_text(V1_EXAMPLE, encoding="utf-8")
    assert main(["attach", "--manifest", str(tmp_path / "manifest.json"),
                 "--gate", "data_integrity", "--status", "pass"]) == 2


def test_agent_workflow_attach_then_check_releases(tmp_path, monkeypatch) -> None:
    """The agent story: run tools -> attach evidence -> gov check releases."""
    d = tmp_path / "agent"
    d.mkdir()
    build_m1(d, "no_evidence_record")
    monkeypatch.chdir(d)

    assert main(["attach", "--manifest", "artifact.json",
                 "--gate", "evidence_integrity", "--status", "pass",
                 "--tool", "falsification-ledger", "--report-ref", "sha256:ledger-1"]) == 0
    assert main(["check", "--manifest", "artifact.json"]) == 0

    artifact = _load(d)
    assert artifact["decision"] == "release"
    assert artifact["missing"] == []


def test_attach_json_output(tmp_path, monkeypatch, capsys) -> None:
    d = tmp_path / "json"
    d.mkdir()
    build_m1(d, "no_evidence_record")
    monkeypatch.chdir(d)

    assert main(["attach", "--manifest", "artifact.json",
                 "--gate", "evidence_integrity", "--status", "pass", "--json"]) == 0
    body = json.loads(capsys.readouterr().out)
    assert body["error"] is None
    assert any(g["gate_id"] == "evidence_integrity" for g in body["gates"])

"""M2 acceptance: scenario 2 (strategy_advice) and scenario 3 (public_copy).

Scenario 2: backtest evidence + robustness gate (real `qc` runs).
Scenario 3: sources + conditional limitations (declared return figures).
"""

from __future__ import annotations

import json
import shutil

import pytest

from holdout_governance.cli import main

from m2_scenarios import build

SC2 = [
    # name, expected exit, expected decision, missing marker
    ("strategy_no_backtest_attachment", 2, "block", "attachment:backtest_report"),
    ("strategy_qc_refused", 1, "review_needed", None),
    ("strategy_qc_overfit", 2, "block", "gate:statistical_quality"),
    ("strategy_complete", 0, "release", None),
]
SC3 = [
    ("copy_missing_sources", 2, "block", "attachment:sources"),
    ("copy_returns_without_limitations", 2, "block", "attachment:limitations"),
    ("copy_complete", 0, "release", None),
    ("copy_no_returns_declared", 0, "release", None),
]


def _run(name: str, tmp_path, monkeypatch) -> dict:
    d = tmp_path / name
    d.mkdir()
    build(d, name)
    monkeypatch.chdir(d)
    code = main(["check", "--manifest", "artifact.json"])
    artifact = json.loads((d / "artifact.json").read_text(encoding="utf-8"))
    return {"code": code, "artifact": artifact}


@pytest.mark.parametrize("name,exit_code,decision,missing_marker", SC2)
def test_scenario2_strategy_advice(tmp_path, monkeypatch, name, exit_code, decision,
                                   missing_marker) -> None:
    if name in ("strategy_qc_refused", "strategy_qc_overfit", "strategy_complete") \
            and shutil.which("qc") is None:
        pytest.skip("qc not installed")
    result = _run(name, tmp_path, monkeypatch)
    artifact = result["artifact"]
    assert result["code"] == exit_code, f"{name}: exit {result['code']} != {exit_code}"
    assert artifact["decision"] == decision, f"{name}: {artifact['decision']}"
    if missing_marker:
        assert missing_marker in artifact["missing"], f"{name}: {artifact['missing']}"


@pytest.mark.parametrize("name,exit_code,decision,missing_marker", SC3)
def test_scenario3_public_copy(tmp_path, monkeypatch, name, exit_code, decision,
                               missing_marker) -> None:
    result = _run(name, tmp_path, monkeypatch)
    artifact = result["artifact"]
    assert result["code"] == exit_code, f"{name}: exit {result['code']} != {exit_code}"
    assert artifact["decision"] == decision, f"{name}: {artifact['decision']}"
    if missing_marker:
        assert missing_marker in artifact["missing"], f"{name}: {artifact['missing']}"


def test_qc_refusal_does_not_hard_block(tmp_path, monkeypatch) -> None:
    if shutil.which("qc") is None:
        pytest.skip("qc not installed")
    result = _run("strategy_qc_refused", tmp_path, monkeypatch)
    assert result["code"] == 1
    assert result["artifact"]["missing"] == []


def test_report_serves_as_publication_note(tmp_path, monkeypatch, capsys) -> None:
    """Through a complete public_copy, gov report shows sources/limitations."""
    d = tmp_path / "copy_complete"
    d.mkdir()
    build(d, "copy_complete")
    monkeypatch.chdir(d)
    assert main(["check", "--manifest", "artifact.json"]) == 0
    capsys.readouterr()
    assert main(["report", "--manifest", "artifact.json"]) == 0
    out = capsys.readouterr().out
    assert "attachments:" in out
    assert "sources: docs/sources.md" in out
    assert "limitations: docs/limitations.md" in out
    assert "declarations:" in out
    assert "contains_returns: true" in out
    assert "decision: RELEASE" in out

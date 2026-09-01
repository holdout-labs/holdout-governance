"""M1 scenario 1 acceptance: 10 seeded defects -> 0 false pass, clean -> release.

The 10 defect samples are caught by *real* tool runs (imm / lf / padj) or by
the decision layer (missing evidence, missing human approval). The clean
control proves the suite is not trivially "block everything".
"""

from __future__ import annotations

import json
import shutil

import pytest

from holdout_governance.cli import main

from m1_scenarios import build

SCENARIOS = [
    ("survivorship_low_coverage", "gate:data_integrity", "imm"),
    ("survivorship_missing_code", "gate:data_integrity", "imm"),
    ("survivorship_continuity_gap", "gate:data_integrity", "imm"),
    ("lookahead_window_after_decision", "gate:temporal_integrity", "lf"),
    ("lookahead_read_release_after_decision", "gate:temporal_integrity", "lf"),
    ("lookahead_pit_cutoff_after_decision", "gate:temporal_integrity", "lf"),
    ("adjustment_archive_corrected_drift", "gate:pit_integrity", "padj"),
    ("adjustment_live_mismatch", "gate:pit_integrity", "padj"),
    ("no_evidence_record", "gate:evidence_integrity", None),
    ("ai_without_approval", "review:approved", None),
]


@pytest.mark.parametrize("name,expected_missing,tool", SCENARIOS)
def test_seeded_defect_is_blocked(tmp_path, monkeypatch, name, expected_missing, tool) -> None:
    if tool and shutil.which(tool) is None:
        pytest.skip(f"{tool} not installed")
    d = tmp_path / name
    d.mkdir()
    build(d, name)
    monkeypatch.chdir(d)

    code = main(["check", "--manifest", "artifact.json"])

    artifact = json.loads((d / "artifact.json").read_text(encoding="utf-8"))
    assert code == 2, f"{name}: expected block exit code, got {code}"
    assert artifact["decision"] == "block", f"{name}: expected block decision"
    assert expected_missing in artifact["missing"], f"{name}: missing={artifact['missing']}"
    # the block must come from evidence, not from policy plumbing
    assert "policy:ref_mismatch" not in artifact["missing"]


def test_clean_control_releases(tmp_path, monkeypatch) -> None:
    for tool in ("imm", "lf", "padj"):
        if shutil.which(tool) is None:
            pytest.skip(f"{tool} not installed")
    d = tmp_path / "clean"
    d.mkdir()
    build(d, "clean")
    monkeypatch.chdir(d)

    code = main(["check", "--manifest", "artifact.json"])

    artifact = json.loads((d / "artifact.json").read_text(encoding="utf-8"))
    assert code == 0
    assert artifact["decision"] == "release"
    assert artifact["missing"] == []
    # real tool runs must have written evidence reports (drift-check reports
    # are prefixed "== drift-check ==", hence the .txt extension)
    reports = [p.name for p in (d / "reports").glob("*")]
    assert {"data_integrity.report.json", "temporal_integrity.report.json"} <= set(reports)
    assert list((d / "reports").glob("pit_integrity.report.*"))

"""Tests for evidence-semantics checks (gov evidence / check integration).

Motivating production findings (2026-09 evidence grill): a dual-snapshot
generator stamped its outputs with a historical cutoff it never honoured
(data read until "now", declared "as of now minus lag"), and same-source
snapshots were presented as two independent pieces of evidence.  These
tests lock the fail-closed semantics: impossible data cutoffs and
same-source same-slice double counting can never release.
"""

from __future__ import annotations

import hashlib
import json
import tempfile
from pathlib import Path

import pytest

from holdout_governance.artifact import load_artifact, save_artifact
from holdout_governance.engine import run_attach, run_check, run_report
from holdout_governance.evidence import check_artifact_evidence

REF_A = "sha256:" + "a" * 64
REF_B = "sha256:" + "b" * 64
RUN_AT = "2026-09-06T15:02:30+00:00"
CUTOFF_OK = "2026-09-06T14:59:00+00:00"      # earlier than run: fine
CUTOFF_LATE = "2026-09-06T15:05:00+00:00"    # later than run: impossible


def _gate(gate_id: str, status: str = "pass", **overrides) -> dict:
    gate = {
        "gate_id": gate_id,
        "tool": "test-tool",
        "status": status,
        "report_ref": REF_B if gate_id == "g2" else REF_A,
        "tool_version": "1.0.0",
        "run_at": RUN_AT,
    }
    gate.update(overrides)
    return gate


def _artifact(*gates: dict) -> dict:
    return {
        "schema_version": "holdout.artifact.v0.2",
        "artifact": {
            "id": "evidence-test",
            "kind": "research_conclusion",
            "created_at": RUN_AT,
        },
        "producer": {"type": "human"},
        "gates": list(gates),
        "attachments": {},
        "review": {"status": "approved", "reviewer": "tester"},
        "safety": {
            "places_orders": False,
            "changes_trading_rules": False,
            "provides_investment_advice": False,
        },
        "policy_ref": "sha256:" + "c" * 64,
        "decision": "release",
        "missing": [],
    }


# --- pure rules -------------------------------------------------------------


def test_no_gates_ok() -> None:
    report = check_artifact_evidence(_artifact())
    assert report["ok"] is True
    assert report["attested"] is False


def test_distinct_evidence_without_attestation_ok() -> None:
    report = check_artifact_evidence(_artifact(_gate("g1"), _gate("g2")))
    assert report["ok"] is True
    assert report["attested"] is False


def test_duplicate_report_content_blocked_when_attested() -> None:
    """Attested artifacts may not count the same report bytes twice."""
    gates = [
        _gate("g1", evidence_source="feed-a", data_cutoff=CUTOFF_OK,
              report_ref=REF_A),
        _gate("g2", evidence_source="feed-b", data_cutoff=CUTOFF_OK,
              report_ref=REF_A),  # same bytes counted twice
    ]
    report = check_artifact_evidence(_artifact(*gates))
    assert report["ok"] is False
    assert any("duplicate_evidence_content:g1,g2" in b for b in report["blockers"])


def test_unattested_duplicate_ref_keeps_legacy_semantics() -> None:
    """Manual-attach flows may legitimately back several gate entries with
    one placeholder report_ref — untouched until attestation is declared."""
    gates = [
        _gate("g1", report_ref=REF_A),
        _gate("g2", report_ref=REF_A),
    ]
    report = check_artifact_evidence(_artifact(*gates))
    assert report["ok"] is True
    assert report["attested"] is False


def test_data_cutoff_after_run_at_blocked() -> None:
    """The now-minus-lag forgery: declared 'as of' later than the run."""
    gates = [
        _gate("g1", evidence_source="feed-a", data_cutoff=CUTOFF_LATE),
    ]
    report = check_artifact_evidence(_artifact(*gates))
    assert report["attested"] is True
    assert any("data_cutoff_after_run_at:g1" in b for b in report["blockers"])


def test_data_cutoff_before_run_at_ok() -> None:
    gates = [
        _gate("g1", evidence_source="feed-a", data_cutoff=CUTOFF_OK),
    ]
    report = check_artifact_evidence(_artifact(*gates))
    assert report["ok"] is True


def test_same_source_same_cutoff_not_independent() -> None:
    """Two pass gates, one source, one declared time slice -> one piece of
    evidence, regardless of byte content."""
    gates = [
        _gate("g1", evidence_source="feed-a", data_cutoff=CUTOFF_OK),
        _gate("g2", evidence_source="feed-a", data_cutoff=CUTOFF_OK),
    ]
    report = check_artifact_evidence(_artifact(*gates))
    assert report["ok"] is False
    assert any("same_source_slice_not_independent:g1,g2:feed-a" in b
               for b in report["blockers"])


def test_same_source_different_cutoff_warns_only() -> None:
    gates = [
        _gate("g1", evidence_source="feed-a", data_cutoff=CUTOFF_OK),
        _gate("g2", evidence_source="feed-a", data_cutoff="2026-09-06T14:30:00+00:00"),
    ]
    report = check_artifact_evidence(_artifact(*gates))
    assert report["ok"] is True
    assert any("same_source_multiple:feed-a:g1,g2" in w for w in report["warns"])


def test_different_sources_independent_ok() -> None:
    gates = [
        _gate("g1", evidence_source="feed-a", data_cutoff=CUTOFF_OK),
        _gate("g2", evidence_source="feed-b", data_cutoff=CUTOFF_OK),
    ]
    report = check_artifact_evidence(_artifact(*gates))
    assert report["ok"] is True


def test_cutoff_without_source_warns() -> None:
    gates = [_gate("g1", data_cutoff=CUTOFF_OK)]
    report = check_artifact_evidence(_artifact(*gates))
    assert report["ok"] is True
    assert any("attestation_incomplete:g1" in w for w in report["warns"])


def test_schema_accepts_attestation_fields(tmp_path) -> None:
    artifact = _artifact(
        _gate("g1", evidence_source="feed-a", data_cutoff=CUTOFF_OK)
    )
    path = tmp_path / "artifact.json"
    save_artifact(path, artifact)
    loaded = load_artifact(path)  # raises on schema violation
    assert loaded["gates"][0]["evidence_source"] == "feed-a"


# --- CLI --------------------------------------------------------------------


def test_cli_evidence_blocks_same_source_slice(tmp_path, capsys) -> None:
    artifact = _artifact(
        _gate("g1", evidence_source="feed-a", data_cutoff=CUTOFF_OK),
        _gate("g2", evidence_source="feed-a", data_cutoff=CUTOFF_OK),
    )
    path = tmp_path / "artifact.json"
    save_artifact(path, artifact)
    from holdout_governance.cli import main

    code = main(["evidence", "--manifest", str(path), "--json"])
    assert code == 1
    body = json.loads(capsys.readouterr().out)
    assert body["ok"] is False
    assert any("same_source_slice_not_independent" in b for b in body["blockers"])


def test_attach_records_attestation(tmp_path) -> None:
    from holdout_governance.engine import run_init

    run_init(str(tmp_path), kind="research_conclusion", name="attest-me")
    manifest = str(tmp_path / "artifact.json")
    run_attach(
        manifest, gate="data_integrity", status="pass", tool="imm",
        report_ref=REF_A, evidence_source="feed-a", data_cutoff=CUTOFF_OK,
    )
    artifact = load_artifact(manifest)
    entry = artifact["gates"][0]
    assert entry["evidence_source"] == "feed-a"
    assert entry["data_cutoff"] == CUTOFF_OK


# --- check integration (fail-closed release gate) ---------------------------


def _policy_file(tmp_path: Path) -> Path:
    text = (
        "schema_version: holdout.policy.v0.1\n"
        "kinds:\n"
        "  research_conclusion:\n"
        "    required_gates: [g1, g2]\n"
        "    severity: block\n"
        "defaults:\n"
        "  missing_gate: block\n"
        "  gate_warn: review_needed\n"
    )
    path = tmp_path / "policy.yml"
    path.write_text(text, encoding="utf-8")
    return path


def test_run_check_blocks_same_source_release(tmp_path) -> None:
    """Two passing same-source same-slice gates would release under the
    policy alone; the evidence semantics must block."""
    from holdout_governance._schemas import ARTIFACT_SCHEMA_VERSION

    policy_path = _policy_file(tmp_path)
    policy_sha = "sha256:" + hashlib.sha256(
        policy_path.read_bytes()
    ).hexdigest()
    artifact = {
        "schema_version": ARTIFACT_SCHEMA_VERSION,
        "artifact": {"id": "x", "kind": "research_conclusion", "created_at": RUN_AT},
        "producer": {"type": "human"},
        "gates": [
            _gate("g1", evidence_source="feed-a", data_cutoff=CUTOFF_OK),
            _gate("g2", evidence_source="feed-a", data_cutoff=CUTOFF_OK),
        ],
        "attachments": {},
        "review": {"status": "approved", "reviewer": "tester"},
        "safety": {"places_orders": False, "changes_trading_rules": False,
                   "provides_investment_advice": False},
        "policy_ref": policy_sha,
        "decision": "pending",
        "missing": [],
    }
    manifest = tmp_path / "artifact.json"
    save_artifact(manifest, artifact)
    result = run_check(str(manifest))
    assert result["decision"] == "block"
    assert any(m.startswith("evidence:same_source_slice") for m in result["missing"])
    saved = load_artifact(manifest)
    assert saved["decision"] == "block"


def test_run_report_warns_but_does_not_block_legacy_duplicate_free(tmp_path) -> None:
    """Non-attested, distinct evidence stays release under report."""
    policy_path = _policy_file(tmp_path)
    policy_sha = "sha256:" + hashlib.sha256(policy_path.read_bytes()).hexdigest()
    artifact = _artifact(_gate("g1"), _gate("g2"))
    artifact["policy_ref"] = policy_sha
    manifest = tmp_path / "artifact.json"
    save_artifact(manifest, artifact)
    result = run_report(str(manifest))
    assert result["decision"] == "release"
    assert result["exit_code"] == 0

"""Unit tests for the v0.2 decision function (PRD §3.3)."""

from __future__ import annotations

import copy

import yaml

from holdout_governance._schemas import DEFAULT_POLICY
from holdout_governance.decide import decide

POLICY = yaml.safe_load(DEFAULT_POLICY)


def _art(kind: str = "research_conclusion", gates: list | None = None,
         producer: str = "human", review: dict | None = None,
         attachments: dict | None = None) -> dict:
    body = {"type": producer}
    if producer == "ai":
        body.update({"model_id": "m1", "prompt_version": "p1"})
    return {
        "schema_version": "holdout.artifact.v0.2",
        "artifact": {"id": "x", "kind": kind, "created_at": "2026-09-01T00:00:00+00:00"},
        "producer": body,
        "gates": gates or [],
        "attachments": attachments or {},
        "review": review or {"status": "approved", "reviewer": "r"},
        "safety": {"places_orders": False, "changes_trading_rules": False,
                   "provides_investment_advice": False},
        "policy_ref": "sha256:policy",
        "decision": "",
        "missing": [],
    }


def _gate(gate_id: str, status: str) -> dict:
    return {"gate_id": gate_id, "tool": "tool", "status": status}


def _all_pass() -> list[dict]:
    return [_gate(g, "pass") for g in
            ("data_integrity", "pit_integrity", "temporal_integrity", "evidence_integrity")]


def test_clean_releases() -> None:
    outcome = decide(_art(gates=_all_pass()), POLICY)
    assert outcome["decision"] == "release"
    assert outcome["missing"] == []


def test_missing_gate_blocks() -> None:
    outcome = decide(_art(gates=_all_pass()[:3]), POLICY)
    assert outcome["decision"] == "block"
    assert "gate:evidence_integrity" in outcome["missing"]


def test_fail_gate_blocks() -> None:
    gates = _all_pass()
    gates[0] = _gate("data_integrity", "fail")
    outcome = decide(_art(gates=gates), POLICY)
    assert outcome["decision"] == "block"
    assert "gate:data_integrity" in outcome["missing"]


def test_warn_gate_only_reviews() -> None:
    gates = _all_pass()
    gates[1] = _gate("pit_integrity", "warn")
    outcome = decide(_art(gates=gates), POLICY)
    assert outcome["decision"] == "review_needed"
    assert "gate:pit_integrity" in outcome["warns"]


def test_warn_plus_missing_still_blocks() -> None:
    gates = _all_pass()[:3]
    gates[1] = _gate("pit_integrity", "warn")
    outcome = decide(_art(gates=gates), POLICY)
    assert outcome["decision"] == "block"


def test_missing_attachment_blocks() -> None:
    outcome = decide(_art(kind="strategy_advice", gates=_all_pass()), POLICY)
    assert outcome["decision"] == "block"
    assert "attachment:backtest_report" in outcome["missing"]
    assert "attachment:robustness_report" in outcome["missing"]


def test_ai_without_approval_blocks() -> None:
    outcome = decide(
        _art(gates=_all_pass(), producer="ai",
             review={"status": "not_recorded", "reviewer": ""}),
        POLICY,
    )
    assert outcome["decision"] == "block"
    assert "review:approved" in outcome["missing"]


def test_unknown_kind_blocks() -> None:
    outcome = decide(_art(kind="quantum_thesis", gates=_all_pass()), POLICY)
    assert outcome["decision"] == "block"
    assert outcome["missing"] == ["policy:kind:quantum_thesis"]


def test_warn_severity_kind_downgrades_instead_of_blocking() -> None:
    # kind "code" has severity: warn -> a failing gate must NOT hard-block
    outcome = decide(_art(kind="code", gates=[_gate("temporal_integrity", "fail")]), POLICY)
    assert outcome["decision"] == "review_needed"
    assert "gate:temporal_integrity" in outcome["missing"]


def test_requires_review_blocks_without_approval() -> None:
    policy = copy.deepcopy(POLICY)
    policy["kinds"]["research_conclusion"]["requires_review"] = True
    outcome = decide(_art(gates=_all_pass(), producer="human",
                          review={"status": "not_recorded", "reviewer": ""}), policy)
    assert outcome["decision"] == "block"
    assert "review:approved" in outcome["missing"]

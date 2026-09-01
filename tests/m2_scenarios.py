"""M2 scenario fixtures: strategy_advice (scenario 2) and public_copy (scenario 3).

Scenario 2 acceptance: no backtest record -> block; qc refuses to judge
(no honest n_trials) -> review_needed; overfitting -> block; complete
evidence -> release.
Scenario 3 acceptance: missing sources -> block; return figures without
limitations -> block; complete -> release (report serves as publication note).
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from holdout_governance._schemas import ARTIFACT_SCHEMA_VERSION, DEFAULT_POLICY
from holdout_governance.policy import sha256_file

QC = {
    "statistical_quality": {
        "cmd": ["qc", "check", "--returns", "returns.json", "--n-trials", "5", "--json"],
        "warn_verdict_prefix": "FAIL - n_trials",
    }
}
QC_REFUSED = {
    "statistical_quality": {
        "cmd": ["qc", "check", "--returns", "returns.json", "--json"],
        "warn_verdict_prefix": "FAIL - n_trials",
    }
}


def _returns(mean: float, std: float, n: int = 300, seed: int = 7) -> list[float]:
    rng = np.random.default_rng(seed)
    return [round(float(x), 6) for x in rng.normal(mean, std, n)]


def _write_policy(d: Path) -> None:
    (d / "policy.yml").write_text(DEFAULT_POLICY, encoding="utf-8")


def _write_gate_inputs(d: Path, spec: dict) -> None:
    (d / "gate-inputs.json").write_text(json.dumps(spec, indent=2), encoding="utf-8")


def _rec(gate_id: str, status: str, tool: str = "recorded") -> dict:
    return {"gate_id": gate_id, "tool": tool, "status": status, "report_ref": "sha256:recorded"}


def _artifact(d: Path, kind: str, gates: list[dict], attachments: dict,
              declarations: dict | None = None) -> None:
    artifact = {
        "schema_version": ARTIFACT_SCHEMA_VERSION,
        "artifact": {"id": d.name, "kind": kind, "created_at": "2026-09-01T12:00:00+00:00"},
        "producer": {"type": "human"},
        "gates": gates,
        "attachments": attachments,
        "review": {"status": "approved", "reviewer": "research-owner"},
        "safety": {"places_orders": False, "changes_trading_rules": False,
                   "provides_investment_advice": False},
        "policy_ref": sha256_file(d / "policy.yml"),
        "decision": "pending",
        "missing": [],
    }
    if declarations:
        artifact["declarations"] = declarations
    (d / "artifact.json").write_text(json.dumps(artifact, indent=2), encoding="utf-8")


STRATEGY_PASS = [
    _rec("data_integrity", "pass"),
    _rec("temporal_integrity", "pass"),
    _rec("evidence_integrity", "pass"),
]
STRATEGY_ATTACHMENTS = {
    "backtest_report": "reports/backtest.md",
    "robustness_report": "reports/robustness.md",
}


def build(d: Path, name: str) -> None:
    _write_policy(d)

    if name == "strategy_no_backtest_attachment":
        _write_gate_inputs(d, {})
        _artifact(d, "strategy_advice", STRATEGY_PASS + [_rec("statistical_quality", "pass")],
                  attachments={})

    elif name == "strategy_qc_refused":
        (d / "returns.json").write_text(json.dumps(_returns(0.003, 0.01)), encoding="utf-8")
        _write_gate_inputs(d, dict(QC_REFUSED))
        _artifact(d, "strategy_advice", STRATEGY_PASS + [_rec("statistical_quality", "not_run")],
                  attachments=dict(STRATEGY_ATTACHMENTS))

    elif name == "strategy_qc_overfit":
        (d / "returns.json").write_text(json.dumps(_returns(-0.001, 0.01)), encoding="utf-8")
        _write_gate_inputs(d, dict(QC))
        _artifact(d, "strategy_advice", STRATEGY_PASS + [_rec("statistical_quality", "not_run")],
                  attachments=dict(STRATEGY_ATTACHMENTS))

    elif name == "strategy_complete":
        (d / "returns.json").write_text(json.dumps(_returns(0.003, 0.01)), encoding="utf-8")
        _write_gate_inputs(d, dict(QC))
        _artifact(d, "strategy_advice", STRATEGY_PASS + [_rec("statistical_quality", "not_run")],
                  attachments=dict(STRATEGY_ATTACHMENTS))

    elif name == "copy_missing_sources":
        _write_gate_inputs(d, {})
        _artifact(d, "public_copy", [_rec("provenance", "pass")], attachments={})

    elif name == "copy_returns_without_limitations":
        _write_gate_inputs(d, {})
        _artifact(d, "public_copy", [_rec("provenance", "pass")],
                  attachments={"sources": "docs/sources.md"},
                  declarations={"contains_returns": True})

    elif name == "copy_complete":
        _write_gate_inputs(d, {})
        _artifact(d, "public_copy", [_rec("provenance", "pass")],
                  attachments={"sources": "docs/sources.md", "limitations": "docs/limitations.md"},
                  declarations={"contains_returns": True})

    elif name == "copy_no_returns_declared":
        _write_gate_inputs(d, {})
        _artifact(d, "public_copy", [_rec("provenance", "pass")],
                  attachments={"sources": "docs/sources.md"})

    else:
        raise ValueError(f"unknown scenario: {name}")

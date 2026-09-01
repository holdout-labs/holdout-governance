"""M1 scenario-1 fixtures: 10 seeded-defect research conclusions + 1 clean.

Defect taxonomy (PRD acceptance for scenario 1):

- survivorship bias  x3  -> data_integrity      (real `imm audit` run)
- look-ahead         x3  -> temporal_integrity  (real `lf check` run)
- adjustment drift   x2  -> pit_integrity       (real `padj drift-check` run)
- no sources         x2  -> decision layer      (evidence_integrity / review)

Every builder writes a self-contained directory: policy.yml, gate-inputs.json,
artifact.json and the tool inputs. `gov check` is then run against it; the
runners spawn the real tools (imm / lf / padj).
"""

from __future__ import annotations

import json
from pathlib import Path

from holdout_governance._schemas import ARTIFACT_SCHEMA_VERSION, DEFAULT_POLICY
from holdout_governance.policy import sha256_file

ALL_CODES = ["600000", "600001", "600002", "600003", "600004"]

RAW = [100.0, 101.0, 60.0, 61.0, 62.0, 63.0]
DATES = ["2026-05-08", "2026-05-09", "2026-06-15", "2026-06-16", "2026-06-17", "2026-06-18"]
FACTORS = [("2026-05-09", 0.95), ("2026-06-15", 0.99)]
AS_OF = "2026-08-11"

IMM = {
    "data_integrity": {
        "cmd": ["imm", "audit", "--watchlist", "watchlist.json",
                "--history-root", "history", "--audit-root", "audit"]
    }
}
LF = {"temporal_integrity": {"cmd": ["lf", "check", "--pipeline", "pipeline.json", "--json"]}}
PADJ = {
    "pit_integrity": {
        "steps": [
            ["padj", "rebuild", "--bars", "bars.json", "--actions", "actions.json",
             "--as-of", AS_OF, "--code", "600000", "--out", "rebuilt.json"],
            ["padj", "drift-check", "--bars", "rebuilt.json", "--actions", "actions.json",
             "--as-of", AS_OF, "--live", "live.json"],
        ]
    }
}


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------


def _write_policy(d: Path) -> None:
    (d / "policy.yml").write_text(DEFAULT_POLICY, encoding="utf-8")


def _write_gate_inputs(d: Path, spec: dict) -> None:
    (d / "gate-inputs.json").write_text(json.dumps(spec, indent=2), encoding="utf-8")


def _artifact(d: Path, gates: list[dict], *, producer: str = "human",
              review: dict | None = None) -> None:
    producer_body = {"type": producer}
    if producer == "ai":
        producer_body.update({"model_id": "research-agent-1", "prompt_version": "2026-09-01.1"})
    artifact = {
        "schema_version": ARTIFACT_SCHEMA_VERSION,
        "artifact": {
            "id": d.name,
            "kind": "research_conclusion",
            "created_at": "2026-09-01T12:00:00+00:00",
        },
        "producer": producer_body,
        "gates": gates,
        "attachments": {},
        "review": review or {"status": "approved", "reviewer": "research-owner"},
        "safety": {
            "places_orders": False,
            "changes_trading_rules": False,
            "provides_investment_advice": False,
        },
        "policy_ref": sha256_file(d / "policy.yml"),
        "decision": "pending",
        "missing": [],
    }
    (d / "artifact.json").write_text(json.dumps(artifact, indent=2), encoding="utf-8")


def _rec(gate_id: str, status: str, tool: str = "recorded") -> dict:
    return {"gate_id": gate_id, "tool": tool, "status": status, "report_ref": "sha256:recorded"}


def _clean_gates() -> list[dict]:
    return [
        _rec("data_integrity", "pass"),
        _rec("pit_integrity", "pass"),
        _rec("temporal_integrity", "pass"),
        _rec("evidence_integrity", "pass"),
    ]


def _imm_fixture(d: Path, codes_with_bars: list[str], *, gap_code: str | None = None) -> None:
    (d / "watchlist.json").write_text(json.dumps({"eligible_codes": ALL_CODES}), encoding="utf-8")
    hist = d / "history"
    hist.mkdir()
    for code in codes_with_bars:
        dates = ["2026-07-01", "2026-08-20"] if code == gap_code else ["2026-08-01"]
        (hist / f"{code}.json").write_text(
            json.dumps({"bars": [{"date": day} for day in dates]}), encoding="utf-8"
        )


def _lf_pipeline(d: Path, operations: list[dict]) -> None:
    (d / "pipeline.json").write_text(
        json.dumps({"name": d.name, "operations": operations}, indent=2), encoding="utf-8"
    )


def _read_op(op_id: str, release: str) -> dict:
    return {"op_id": op_id, "kind": "read", "release": release, "outputs": [op_id]}


def _window_op(op_id: str, window_end: str, inputs: list[str]) -> dict:
    return {"op_id": op_id, "kind": "window", "window_end": window_end,
            "inputs": inputs, "outputs": [op_id]}


def _pit_op(op_id: str, cutoff: str) -> dict:
    return {"op_id": op_id, "kind": "pit_read", "read_cutoff": cutoff, "outputs": [op_id]}


def _decision_op(inputs: list[str]) -> dict:
    return {"op_id": "decide", "kind": "decision", "decision_time": "2026-08-01T15:00:00",
            "inputs": inputs, "outputs": ["signal"]}


def _qfq_bars() -> list[dict]:
    bars = []
    for day, raw in zip(DATES, RAW):
        pending = [factor for ex_date, factor in FACTORS if ex_date > day]
        mult = 1.0
        for factor in pending:
            mult *= factor
        close = round(raw * mult, 6)
        bars.append({
            "date": day, "open": close, "high": close, "low": close, "close": close,
            "volume": 1200.0, "amount": round(close * 1200.0, 2), "turnover": 1.0,
        })
    return bars


def _actions(factors: list[tuple[str, float]]) -> list[dict]:
    return [
        {
            "action_id": f"demo-{ex_date}",
            "action_type": "cash_dividend_stock_distribution",
            "ex_date": ex_date,
            "available_at": f"{ex_date}T18:00:00",
            "adjustment_factor": factor,
        }
        for ex_date, factor in factors
    ]


def _padj_fixture(d: Path, *, actions_factors: list[tuple[str, float]], live_mult: float = 1.0) -> None:
    (d / "bars.json").write_text(json.dumps(_qfq_bars(), indent=2), encoding="utf-8")
    (d / "actions.json").write_text(json.dumps(_actions(actions_factors), indent=2), encoding="utf-8")
    (d / "live.json").write_text(
        json.dumps({day: round(raw * live_mult, 6) for day, raw in zip(DATES, RAW)}),
        encoding="utf-8",
    )


# --------------------------------------------------------------------------
# scenarios
# --------------------------------------------------------------------------


def build(d: Path, name: str) -> None:
    _write_policy(d)

    if name == "survivorship_low_coverage":          # imm: coverage 3/5 = 0.6
        _imm_fixture(d, ALL_CODES[:3])
        _write_gate_inputs(d, dict(IMM))
        _artifact(d, [_rec("data_integrity", "not_run")] + _clean_gates()[1:])

    elif name == "survivorship_missing_code":        # imm: coverage 2/5 = 0.4
        _imm_fixture(d, ALL_CODES[:2])
        _write_gate_inputs(d, dict(IMM))
        _artifact(d, [_rec("data_integrity", "not_run")] + _clean_gates()[1:])

    elif name == "survivorship_continuity_gap":      # imm: 50-day calendar gap
        _imm_fixture(d, ALL_CODES, gap_code="600002")
        _write_gate_inputs(d, dict(IMM))
        _artifact(d, [_rec("data_integrity", "not_run")] + _clean_gates()[1:])

    elif name == "lookahead_window_after_decision":  # lf: window ends after decision
        _lf_pipeline(d, [
            _read_op("quotes", "2026-07-31T16:00:00"),
            _window_op("momentum", "2026-08-01T16:00:00", ["quotes"]),
            _decision_op(["momentum"]),
        ])
        _write_gate_inputs(d, dict(LF))
        _artifact(d, [_rec("temporal_integrity", "not_run")] + _clean_gates()[:1]
                  + _clean_gates()[2:])

    elif name == "lookahead_read_release_after_decision":  # lf: read released after decision
        _lf_pipeline(d, [
            _read_op("quotes", "2026-08-01T16:00:00"),
            _window_op("momentum", "2026-08-01T15:00:00", ["quotes"]),
            _decision_op(["momentum"]),
        ])
        _write_gate_inputs(d, dict(LF))
        _artifact(d, [_rec("temporal_integrity", "not_run")] + _clean_gates()[:1]
                  + _clean_gates()[2:])

    elif name == "lookahead_pit_cutoff_after_decision":  # lf: PIT cutoff after decision
        _lf_pipeline(d, [
            _read_op("quotes", "2026-07-31T16:00:00"),
            _pit_op("fundamentals", "2026-08-01T16:00:00"),
            _decision_op(["fundamentals"]),
        ])
        _write_gate_inputs(d, dict(LF))
        _artifact(d, [_rec("temporal_integrity", "not_run")] + _clean_gates()[:1]
                  + _clean_gates()[2:])

    elif name == "adjustment_archive_corrected_drift":   # padj: archive factor corrected
        _padj_fixture(d, actions_factors=[("2026-05-09", 0.95), ("2026-06-15", 0.94)])
        _write_gate_inputs(d, dict(PADJ))
        _artifact(d, [_rec("pit_integrity", "not_run")] + _clean_gates()[:1] + _clean_gates()[2:])

    elif name == "adjustment_live_mismatch":             # padj: live closes 5% off
        _padj_fixture(d, actions_factors=FACTORS, live_mult=1.05)
        _write_gate_inputs(d, dict(PADJ))
        _artifact(d, [_rec("pit_integrity", "not_run")] + _clean_gates()[:1] + _clean_gates()[2:])

    elif name == "no_evidence_record":                   # decision layer: no evidence gate at all
        _write_gate_inputs(d, {})
        _artifact(d, _clean_gates()[:3])

    elif name == "ai_without_approval":                  # decision layer: AI, no human review
        _write_gate_inputs(d, {})
        _artifact(d, _clean_gates()[:3] + [_rec("evidence_integrity", "not_run")],
                  producer="ai", review={"status": "not_recorded", "reviewer": ""})

    elif name == "clean":                                # control: must RELEASE
        _imm_fixture(d, ALL_CODES)
        _lf_pipeline(d, [
            _read_op("quotes", "2026-07-31T16:00:00"),
            _window_op("momentum", "2026-08-01T15:00:00", ["quotes"]),
            _decision_op(["momentum"]),
        ])
        _padj_fixture(d, actions_factors=FACTORS)
        _write_gate_inputs(d, {**IMM, **LF, **PADJ})
        _artifact(d, [_rec("data_integrity", "not_run"), _rec("pit_integrity", "not_run"),
                      _rec("temporal_integrity", "not_run"), _rec("evidence_integrity", "pass")])

    else:
        raise ValueError(f"unknown scenario: {name}")

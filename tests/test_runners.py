"""Gate runner tests: subprocess plumbing, evidence persistence, fail-closed."""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

from holdout_governance.runners import run_gate

FAKE = [
    sys.executable,
    "-c",
    "import json,sys;print(json.dumps({'ok': True}));sys.exit(int(sys.argv[1]))",
]


def _fake(exit_code: int) -> dict:
    return {"cmd": FAKE + [str(exit_code)]}


def _report(path, name: str) -> str:
    return (path / "reports" / name).read_text(encoding="utf-8")


def test_exit0_is_pass_with_persisted_report(tmp_path) -> None:
    result = run_gate("g1", _fake(0), tmp_path)
    assert result["status"] == "pass"
    assert result["tool"] == sys.executable
    content = _report(tmp_path, "g1.report.json")
    assert json.loads(content) == {"ok": True}
    assert result["report_ref"] == "sha256:" + hashlib.sha256(content.encode("utf-8")).hexdigest()
    assert Path(result["report_path"]) == Path("reports") / "g1.report.json"


def test_exit1_is_fail(tmp_path) -> None:
    result = run_gate("g2", _fake(1), tmp_path)
    assert result["status"] == "fail"
    assert (tmp_path / "reports" / "g2.report.json").exists()


def test_exit2_is_not_run(tmp_path) -> None:
    result = run_gate("g3", _fake(2), tmp_path)
    assert result["status"] == "not_run"
    assert "exit 2" in result["reason"]


def test_missing_command_is_not_run(tmp_path) -> None:
    result = run_gate("g4", {"cmd": ["definitely-not-a-real-tool-xyz"]}, tmp_path)
    assert result["status"] == "not_run"
    assert "not found" in result["reason"]
    # tool must stay non-empty (schema: minLength 1) so the artifact
    # remains valid for `gov report` after a fail-closed check
    assert result["tool"] == "definitely-not-a-real-tool-xyz"


def test_no_cmd_is_not_run(tmp_path) -> None:
    result = run_gate("g5", {}, tmp_path)
    assert result["status"] == "not_run"
    assert "no cmd" in result["reason"]
    assert result["tool"] == "unknown"


def test_non_json_output_uses_txt_extension(tmp_path) -> None:
    spec = {"cmd": [sys.executable, "-c", "print('plain text output')"]}
    result = run_gate("g6", spec, tmp_path)
    assert result["status"] == "pass"
    assert (tmp_path / "reports" / "g6.report.txt").exists()


def test_steps_chain_runs_in_order_and_last_step_counts(tmp_path) -> None:
    spec = {
        "steps": [
            [sys.executable, "-c", "print('step1 ok')"],
            [sys.executable, "-c", "import json;print(json.dumps({'final': True}))"],
        ]
    }
    result = run_gate("g7", spec, tmp_path)
    assert result["status"] == "pass"
    content = (tmp_path / "reports" / "g7.report.json").read_text(encoding="utf-8")
    assert json.loads(content) == {"final": True}


def test_steps_fail_closed_on_intermediate_failure(tmp_path) -> None:
    spec = {
        "steps": [
            [sys.executable, "-c", "import json,sys;print(json.dumps({'boom': True}));sys.exit(1)"],
            [sys.executable, "-c", "print('never reached')"],
        ]
    }
    result = run_gate("g8", spec, tmp_path)
    assert result["status"] == "fail"
    content = (tmp_path / "reports" / "g8.report.json").read_text(encoding="utf-8")
    assert json.loads(content) == {"boom": True}


def test_warn_verdict_prefix_maps_refusal_to_warn(tmp_path) -> None:
    spec = {
        "cmd": [sys.executable, "-c",
                "import json,sys;print(json.dumps({'verdict': 'FAIL - n_trials must be declared'}));sys.exit(1)"],
        "warn_verdict_prefix": "FAIL - n_trials",
    }
    result = run_gate("g9", spec, tmp_path)
    assert result["status"] == "warn"
    assert "refused to judge" in result["reason"]


def test_warn_verdict_prefix_does_not_mask_real_failures(tmp_path) -> None:
    spec = {
        "cmd": [sys.executable, "-c",
                "import json,sys;print(json.dumps({'verdict': 'FAIL - P0 blocker(s): dsr'}));sys.exit(1)"],
        "warn_verdict_prefix": "FAIL - n_trials",
    }
    result = run_gate("g10", spec, tmp_path)
    assert result["status"] == "fail"


# ---- stable evidence fingerprints (volatile_keys normalization) ------------

_VOLATILE_CMD = [
    sys.executable,
    "-c",
    "import json,sys;print(json.dumps({'checked_at': sys.argv[1], 'audit_date': '2026-09-02', "
    "'passed': True, 'nested': {'checked_at': 'x', 'value': 1}}))",
]


def _raw_file_hash(path) -> str:
    content = Path(path).read_text(encoding="utf-8")
    return "sha256:" + hashlib.sha256(content.encode("utf-8")).hexdigest()


def test_volatile_keys_give_stable_fingerprint_across_runs(tmp_path) -> None:
    spec_a = {"cmd": _VOLATILE_CMD + ["2026-09-02T10:00:00"],
              "volatile_keys": ["checked_at", "audit_date"]}
    spec_b = {"cmd": _VOLATILE_CMD + ["2026-09-03T22:00:00"],
              "volatile_keys": ["checked_at", "audit_date"]}
    ref_a = run_gate("gv1", spec_a, tmp_path)["report_ref"]
    ref_b = run_gate("gv2", spec_b, tmp_path)["report_ref"]
    assert ref_a == ref_b
    assert ref_a.startswith("sha256:")
    # raw reports on disk still differ: timestamps stay available for audit
    assert (tmp_path / "reports" / "gv1.report.json").read_text(encoding="utf-8") != \
           (tmp_path / "reports" / "gv2.report.json").read_text(encoding="utf-8")


def test_volatile_normalized_ref_differs_from_raw_hash(tmp_path) -> None:
    result = run_gate("gv3", {"cmd": _VOLATILE_CMD + ["2026-09-02T10:00:00"],
                              "volatile_keys": ["checked_at", "audit_date"]}, tmp_path)
    raw = _raw_file_hash(tmp_path / "reports" / "gv3.report.json")
    assert result["report_ref"] != raw


def test_no_volatile_keys_keeps_byte_exact_hash(tmp_path) -> None:
    result = run_gate("gv4", {"cmd": _VOLATILE_CMD + ["2026-09-02T10:00:00"]}, tmp_path)
    raw = _raw_file_hash(tmp_path / "reports" / "gv4.report.json")
    assert result["report_ref"] == raw


def test_volatile_keys_ignored_for_non_json_output(tmp_path) -> None:
    spec = {"cmd": [sys.executable, "-c", "print('plain text output')"],
            "volatile_keys": ["checked_at"]}
    result = run_gate("gv5", spec, tmp_path)
    raw = _raw_file_hash(tmp_path / "reports" / "gv5.report.txt")
    assert result["report_ref"] == raw

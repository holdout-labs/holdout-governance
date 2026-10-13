"""Real-tool green/tamper/block/restore demo, confined to a disposable copy.

Also checks strategy_advice with real qc returns. Data and attachments are
synthetic fixtures; no market, model, publication or trading action occurs.
"""
from __future__ import annotations
import hashlib
import json
import os
from pathlib import Path
import random
import shutil
import subprocess
import sys
import sysconfig
import tempfile


def _check(directory: Path, expected: int, *, failed_gate: str | None = None) -> dict:
    env = dict(os.environ)
    env["PATH"] = sysconfig.get_path("scripts") + os.pathsep + env.get("PATH", "")
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUTF8"] = "1"
    result = subprocess.run([sys.executable, "-m", "holdout_governance.cli", "check",
                             "--manifest", "artifact.json", "--json"], cwd=directory,
                            capture_output=True, text=True, encoding="utf-8", env=env)
    print(result.stdout, end="")
    if result.stderr:
        print(result.stderr, end="", file=sys.stderr)
    if result.returncode != expected:
        raise RuntimeError(f"expected gov exit {expected}, got {result.returncode}")
    summary = json.loads(result.stdout)
    expected_decision = "release" if expected == 0 else "block"
    if summary.get("decision") != expected_decision or not summary.get("policy_ref_ok"):
        raise RuntimeError("gov did not return the expected policy-backed decision")
    artifact = json.loads((directory / "artifact.json").read_text(encoding="utf-8"))
    statuses = {gate["gate_id"]: gate["status"] for gate in artifact["gates"]}
    # Missing binaries and errors also block; they must not impersonate tamper detection.
    if not statuses or any(status != ("fail" if gate == failed_gate else "pass")
                           for gate, status in statuses.items()):
        raise RuntimeError(f"unexpected gate results: {statuses}")
    if failed_gate and statuses.get(failed_gate) != "fail":
        raise RuntimeError(f"expected real tool failure for {failed_gate}")
    return artifact


def run_demo(fixtures: Path | None = None) -> None:
    fixtures = fixtures or Path(__file__).resolve().parent
    with tempfile.TemporaryDirectory(prefix="holdout-gov-demo-") as temporary:
        work = Path(temporary) / "demo"
        shutil.copytree(fixtures, work, ignore=shutil.ignore_patterns("__pycache__"))
        artifact_path = work / "artifact.json"
        artifact = json.loads(artifact_path.read_text(encoding="utf-8"))
        artifact["gates"] = []  # evidence must come from this run
        artifact["decision"] = "pending"
        artifact["missing"] = []
        artifact["policy_ref"] = "sha256:" + hashlib.sha256((work / "policy.yml").read_bytes()).hexdigest()
        artifact_path.write_text(json.dumps(artifact, indent=2), encoding="utf-8")
        ledger = work / "ledger" / "ledger.jsonl"
        original_ledger = ledger.read_bytes()
        print("1. GREEN: real imm / padj / lf / fl checks in a temporary copy")
        _check(work, 0)
        print("2. TAMPER: append an unchained synthetic event")
        with ledger.open("ab") as handle:
            handle.write(b'{"event":"register","case_id":"FAKE-CASE","recorded_at":"2026-09-02T00:00:00+08:00","reason":"tampered"}\n')
        print("3. BLOCK: require exit 2 and evidence_integrity=fail")
        _check(work, 2, failed_gate="evidence_integrity")
        ledger.write_bytes(original_ledger)
        print("4. RESTORE: exact original ledger bytes, then green again")
        _check(work, 0)
        print("5. STRATEGY: real qc gate on synthetic returns")
        artifact["artifact"]["kind"] = "strategy_advice"
        artifact["gates"] = []
        artifact["attachments"] = {"backtest_report": "reports/backtest.md",
                                   "robustness_report": "reports/robustness.md"}
        (work / "reports").mkdir(exist_ok=True)
        for name in ("backtest", "robustness"):
            (work / "reports" / f"{name}.md").write_text("Synthetic demo fixture only.\n", encoding="utf-8")
        artifact_path.write_text(json.dumps(artifact, indent=2), encoding="utf-8")
        inputs = json.loads((work / "gate-inputs.json").read_text(encoding="utf-8"))
        inputs["statistical_quality"]["cmd"] = ["qc", "check", "--returns", "returns.json",
                                                 "--n-trials", "5", "--json"]
        (work / "gate-inputs.json").write_text(json.dumps(inputs, indent=2), encoding="utf-8")
        rng = random.Random(7)
        returns = [round(rng.gauss(0.004, 0.01), 6) for _ in range(600)]
        (work / "returns.json").write_text(json.dumps(returns), encoding="utf-8")
        _check(work, 0)
        print("6. STRATEGY BLOCK: real qc rejects negative synthetic returns")
        (work / "returns.json").write_text(json.dumps([-abs(value) for value in returns]), encoding="utf-8")
        _check(work, 2, failed_gate="statistical_quality")
    print("Done. Temporary copy removed; source fixtures were never written.")


if __name__ == "__main__":
    try:
        run_demo()
    except (OSError, ValueError, RuntimeError) as exc:
        print(f"Demo failed: {exc}", file=sys.stderr)
        sys.exit(1)

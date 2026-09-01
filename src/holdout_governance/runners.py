"""Gate runners: execute one gate's tool via subprocess and record evidence.

Semantics (fail-closed):
- exit 0            -> ``pass`` (stdout saved as the gate report)
- exit 1            -> ``fail`` (the tool found violations)
- exit 2 or crash   -> ``not_run`` (configuration/execution problem -> blocks)
- missing command / timeout -> ``not_run``
"""

from __future__ import annotations

import hashlib
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_TIMEOUT = 120.0


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _not_run(reason: str) -> dict:
    return {
        "status": "not_run",
        "tool": "",
        "report_ref": "",
        "report_path": "",
        "tool_version": "",
        "run_at": _now(),
        "reason": reason,
    }


def run_gate(
    gate_id: str,
    spec: dict,
    base_dir: Path | str,
    timeout: float = DEFAULT_TIMEOUT,
) -> dict:
    """Run the tool(s) configured for one gate; return a mergeable result dict.

    ``spec`` supports either a single ``cmd`` list or ``steps`` (a list of
    cmd lists, e.g. rebuild -> drift-check). Steps run in order with the same
    cwd; any nonzero exit stops the chain (fail-closed). The last step's
    stdout becomes the gate report.
    """
    if spec.get("steps"):
        steps = spec["steps"]
    elif spec.get("cmd"):
        steps = [spec["cmd"]]
    else:
        return _not_run("no cmd/steps configured for gate")
    cwd = Path(spec.get("cwd") or base_dir)
    if not cwd.is_absolute():
        cwd = Path(base_dir) / cwd

    proc = None
    for cmd in steps:
        if not cmd:
            return _not_run("empty step in gate")
        try:
            proc = subprocess.run(
                cmd,
                cwd=str(cwd),
                capture_output=True,
                text=True,
                timeout=timeout,
            )
        except FileNotFoundError:
            return _not_run(f"command not found: {cmd[0]}")
        except subprocess.TimeoutExpired:
            return _not_run(f"timeout after {timeout:g}s")
        if proc.returncode != 0:
            break
    assert proc is not None

    stdout = proc.stdout or ""
    stderr = (proc.stderr or "").strip()

    # persist the raw tool output as the gate report (evidence over assertion)
    reports_dir = Path(base_dir) / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    ext = ".json" if stdout.lstrip()[:1] in ("{", "[") else ".txt"
    report_path = reports_dir / f"{gate_id}.report{ext}"
    report_path.write_text(stdout, encoding="utf-8")
    report_ref = "sha256:" + hashlib.sha256(stdout.encode("utf-8")).hexdigest()
    try:
        rel = str(report_path.relative_to(base_dir))
    except ValueError:
        rel = str(report_path)

    if proc.returncode == 0:
        status, reason = "pass", ""
    elif proc.returncode == 1:
        status, reason = "fail", stderr[-300:]
        # optional: a tool that *refuses to judge* (e.g. qc without an
        # honest n_trials) maps to warn -> review_needed, not hard block
        prefix = spec.get("warn_verdict_prefix")
        if prefix:
            try:
                verdict = json.loads(stdout).get("verdict", "")
            except (json.JSONDecodeError, AttributeError):
                verdict = ""
            if str(verdict).startswith(prefix):
                status = "warn"
                reason = f"tool refused to judge: {verdict[:160]}"
    else:
        status, reason = "not_run", f"exit {proc.returncode}: {stderr[-300:]}"

    return {
        "status": status,
        "tool": (steps[0][0] if steps else ""),
        "report_ref": report_ref,
        "report_path": rel,
        "tool_version": str(spec.get("version") or ""),
        "run_at": _now(),
        "reason": reason,
    }

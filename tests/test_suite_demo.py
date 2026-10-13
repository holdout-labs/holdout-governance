"""Full demo uses installed tools and never writes the fixture directory."""
import importlib.util
from pathlib import Path
import shutil
import subprocess
import pytest
ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("suite_demo", ROOT / "examples/gov-demo/run_demo.py")
demo = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(demo)


def _snapshot(directory):
    return {path.relative_to(directory): path.read_bytes() for path in directory.rglob("*")
            if path.is_file() and "__pycache__" not in path.parts}


def test_real_chain_preserves_fixtures():
    if any(shutil.which(command) is None for command in ("imm", "padj", "lf", "fl", "qc")):
        pytest.skip("full suite not installed; suite-chain CI requires gov doctor first")
    fixtures = ROOT / "examples/gov-demo"
    original = _snapshot(fixtures)
    demo.run_demo(fixtures)
    assert _snapshot(fixtures) == original


def test_failure_preserves_fixtures(monkeypatch):
    fixtures = ROOT / "examples/gov-demo"
    original = _snapshot(fixtures)
    seen = []
    def interrupted(directory, *args, **kwargs):
        seen.append(directory)
        if len(seen) == 2:
            assert b'FAKE-CASE' in (directory / "ledger/ledger.jsonl").read_bytes()
            raise KeyboardInterrupt
        return {}
    monkeypatch.setattr(demo, "_check", interrupted)
    with pytest.raises(KeyboardInterrupt):
        demo.run_demo(fixtures)
    assert _snapshot(fixtures) == original
    assert not seen[-1].exists()


def test_review_exit_is_not_mistaken_for_tamper_block(tmp_path, monkeypatch):
    monkeypatch.setattr(demo.subprocess, "run", lambda *a, **kw:
                        subprocess.CompletedProcess(a[0], 1, "{}", ""))
    with pytest.raises(RuntimeError, match="expected gov exit 2, got 1"):
        demo._check(tmp_path, 2, failed_gate="evidence_integrity")


def test_configuration_block_is_not_tamper_detection(tmp_path, monkeypatch):
    (tmp_path / "artifact.json").write_text(
        '{"gates":[{"gate_id":"evidence_integrity","status":"not_run"}]}')
    monkeypatch.setattr(demo.subprocess, "run", lambda *a, **kw:
                        subprocess.CompletedProcess(a[0], 2,
                                                    '{"decision":"block","policy_ref_ok":true}', ""))
    with pytest.raises(RuntimeError, match="unexpected gate results"):
        demo._check(tmp_path, 2, failed_gate="evidence_integrity")

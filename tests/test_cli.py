from __future__ import annotations

import json
from pathlib import Path

from holdout_governance import __version__
from holdout_governance.cli import main

EXAMPLE = Path(__file__).resolve().parents[1] / "examples" / "ai-research-manifest.json"


def test_cli_version(capsys) -> None:
    assert main(["version"]) == 0
    assert capsys.readouterr().out.strip() == __version__


def test_cli_validate_example(capsys) -> None:
    assert main(["validate", "--manifest", str(EXAMPLE), "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["passed"] is True


def test_cli_report_blocks_unsafe_manifest(tmp_path, capsys) -> None:
    manifest = json.loads(EXAMPLE.read_text(encoding="utf-8"))
    manifest["safety"]["provides_investment_advice"] = True
    path = tmp_path / "unsafe.json"
    path.write_text(json.dumps(manifest), encoding="utf-8")
    assert main(["report", "--manifest", str(path)]) == 1
    report = json.loads(capsys.readouterr().out)
    assert report["passed"] is False
    assert "safety.provides_investment_advice must be False" in report["blockers"]

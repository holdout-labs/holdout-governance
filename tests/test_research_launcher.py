"""Useful startup guidance without opening a UI or consuming test samples."""
from pathlib import Path
import os
import subprocess
import sys

import pytest

from holdout_governance import research_ui


def test_default_output_does_not_follow_shell_directory(tmp_path, monkeypatch):
    expected = research_ui.default_directory()
    monkeypatch.chdir(tmp_path)
    assert research_ui.default_directory() == expected
    assert expected == Path.home() / ".holdout" / "research-runs"


def test_environment_check_never_launches_or_creates_study(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(research_ui, "launch", lambda *_: (_ for _ in ()).throw(AssertionError("opened UI")))
    assert research_ui.main(["--check", "--dir", str(tmp_path / "unused")]) == 0
    assert not (tmp_path / "unused").exists()
    assert "没有创建研究" in capsys.readouterr().out


def test_missing_research_dependency_has_install_instruction(monkeypatch, capsys):
    def missing():
        raise ModuleNotFoundError("missing numpy", name="numpy")
    monkeypatch.setattr(research_ui, "check_environment", missing)
    assert research_ui.main(["--check"]) == 2
    assert "pip install" in capsys.readouterr().err


def test_missing_tkinter_has_desktop_instruction(monkeypatch, capsys):
    def missing():
        raise ModuleNotFoundError("missing tkinter", name="tkinter")
    monkeypatch.setattr(research_ui, "check_environment", missing)
    assert research_ui.main(["--check"]) == 2
    assert "Tcl/Tk" in capsys.readouterr().err


def test_source_launcher_check_works_from_other_directory(tmp_path):
    script = Path(__file__).resolve().parents[1] / "examples" / "factor_research.py"
    result = subprocess.run([sys.executable, str(script), "--check"], cwd=tmp_path,
                            capture_output=True, text=True, encoding="utf-8",
                            env={**os.environ, "PYTHONIOENCODING": "utf-8"})
    assert result.returncode == 0, result.stderr
    assert "研究运行环境已就绪" in result.stdout
    assert not list(tmp_path.iterdir())


def test_source_launcher_without_dependencies_has_guidance(tmp_path):
    script = Path(__file__).resolve().parents[1] / "examples" / "factor_research.py"
    result = subprocess.run([sys.executable, "-S", str(script), "--check"], cwd=tmp_path,
                            capture_output=True, text=True, encoding="utf-8",
                            env={**os.environ, "PYTHONIOENCODING": "utf-8"})
    assert result.returncode == 2
    assert "pip install" in result.stderr
    assert "Traceback" not in result.stderr
    assert not list(tmp_path.iterdir())


@pytest.mark.skipif(os.name != "nt", reason="Windows double-click launcher")
def test_windows_launcher_without_python_keeps_actionable_message(tmp_path):
    launcher = Path(__file__).resolve().parents[1] / "Start-Factor-Research.cmd"
    copied = tmp_path / launcher.name
    copied.write_bytes(launcher.read_bytes())
    command = Path(os.environ["SystemRoot"]) / "System32" / "cmd.exe"
    result = subprocess.run([str(command), "/d", "/c", str(copied)], cwd=tmp_path,
                            input="\n", capture_output=True, text=True, encoding="utf-8",
                            env={**os.environ, "PATH": str(tmp_path)}, timeout=10)
    assert result.returncode == 2
    assert "Python 3.11" in result.stdout
    assert "python.org/downloads/windows" in result.stdout

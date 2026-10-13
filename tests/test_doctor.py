"""Diagnosis exposes missing tools and metadata/PATH version conflicts."""
import importlib.metadata
from pathlib import Path
import subprocess
import tomllib
from holdout_governance import doctor
from holdout_governance.cli import main


def test_profile_matches_extra_and_constraints():
    root = Path(__file__).resolve().parents[1]
    project = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    pins = {name: version for name, _, version in doctor.SUITE}
    assert pins["holdout-governance"] == project["version"]
    assert set(project["optional-dependencies"]["suite"]) == {
        f"{name}=={version}" for name, version in pins.items() if name != "holdout-governance"}
    constraints = {line for line in (root / "tools/suite-constraints.txt").read_text().splitlines()
                   if line and not line.startswith("#")}
    assert constraints == {f"{name}=={version}" for name, version in pins.items()}


def test_missing_install_and_path_are_reported(monkeypatch):
    def missing(package):
        raise importlib.metadata.PackageNotFoundError(package)
    monkeypatch.setattr(doctor.importlib.metadata, "version", missing)
    monkeypatch.setattr(doctor.shutil, "which", lambda command: None)
    result = doctor.check_suite()
    assert not result["ok"]
    assert all(len(tool["issues"]) == 2 for tool in result["tools"])


def test_wrong_path_version_cannot_pass(monkeypatch):
    pins = {name: version for name, _, version in doctor.SUITE}
    monkeypatch.setattr(doctor.importlib.metadata, "version", lambda package: pins[package])
    monkeypatch.setattr(doctor.shutil, "which", lambda command: f"/other-env/{command}")
    monkeypatch.setattr(doctor.subprocess, "run", lambda *a, **k:
                        subprocess.CompletedProcess(a[0], 0, "999.0.0\n", ""))
    result = doctor.check_suite()
    assert not result["ok"]
    assert all("does not match" in tool["issues"][0] for tool in result["tools"])


def test_doctor_json_exit_is_not_a_release(monkeypatch, capsys):
    monkeypatch.setattr(doctor, "check_suite", lambda: {"ok": False, "python": "p", "tools": []})
    assert main(["doctor", "--json"]) == 1
    assert '"ok": false' in capsys.readouterr().out


def test_unexpected_version_output_is_not_echoed(monkeypatch):
    pins = {name: version for name, _, version in doctor.SUITE}
    monkeypatch.setattr(doctor.importlib.metadata, "version", lambda package: pins[package])
    monkeypatch.setattr(doctor.shutil, "which", lambda command: f"/other-env/{command}")
    monkeypatch.setattr(doctor.subprocess, "run", lambda *a, **k:
                        subprocess.CompletedProcess(a[0], 0, "sensitive response text", ""))
    result = doctor.check_suite()
    assert not result["ok"]
    assert "sensitive response text" not in str(result)

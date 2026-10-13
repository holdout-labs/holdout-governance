"""Make the src-layout package importable when running pytest from the repo."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pytest


@pytest.fixture(autouse=True)
def isolated_test_registry(tmp_path, monkeypatch):
    # Tests must never consume, reset or contaminate an operator's real registry.
    monkeypatch.setenv("HOLDOUT_TEST_REGISTRY", str(tmp_path/"custodian"/"test-use.sqlite"))

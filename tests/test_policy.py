"""Policy loading tests."""

from __future__ import annotations

import pytest
import yaml

from holdout_governance._schemas import DEFAULT_POLICY
from holdout_governance.policy import load_policy, sha256_file, sha256_text


def test_default_policy_loads(tmp_path) -> None:
    path = tmp_path / "policy.yml"
    path.write_text(DEFAULT_POLICY, encoding="utf-8")
    policy = load_policy(path)
    assert set(policy["kinds"]) == {
        "research_conclusion", "strategy_advice", "public_copy", "code",
    }
    assert policy["kinds"]["research_conclusion"]["required_gates"] == [
        "data_integrity", "pit_integrity", "temporal_integrity", "evidence_integrity",
    ]


def test_invalid_policy_rejected(tmp_path) -> None:
    path = tmp_path / "policy.yml"
    path.write_text("schema_version: holdout.policy.v0.1\n", encoding="utf-8")  # missing kinds
    with pytest.raises(ValueError):
        load_policy(path)


def test_sha256_helpers() -> None:
    assert sha256_text("abc") == "sha256:" + "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"
    path = "data.txt"
    import pathlib

    p = pathlib.Path(path)
    p.write_text("abc", encoding="utf-8")
    try:
        assert sha256_file(path) == sha256_text("abc")
    finally:
        p.unlink()

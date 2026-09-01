"""MCP tool tests — call the agent-facing functions directly."""

from __future__ import annotations

import json

import pytest

pytest.importorskip("mcp")

from holdout_governance.mcp_server import (  # noqa: E402
    build_mcp_server,
    mcp_gov_check,
    mcp_gov_init,
    mcp_gov_report,
)

from m1_scenarios import build  # noqa: E402


def test_mcp_check_blocks_defect(tmp_path) -> None:
    d = tmp_path / "defect"
    d.mkdir()
    build(d, "no_evidence_record")
    payload = json.loads(mcp_gov_check(str(d / "artifact.json")))
    assert payload["decision"] == "block"
    assert payload["exit_code"] == 2
    assert "gate:evidence_integrity" in payload["missing"]


def test_mcp_report_assesses(tmp_path) -> None:
    d = tmp_path / "defect"
    d.mkdir()
    build(d, "no_evidence_record")
    payload = json.loads(mcp_gov_report(str(d / "artifact.json")))
    assert payload["decision"] == "block"


def test_mcp_init_scaffolds(tmp_path) -> None:
    target = tmp_path / "proj"
    payload = json.loads(mcp_gov_init(str(target), kind="research_conclusion", name="mcp-demo"))
    assert payload["error"] is None
    assert (target / "artifact.json").exists()
    assert payload["policy_ref"].startswith("sha256:")


def test_mcp_server_builds() -> None:
    server = build_mcp_server()
    assert server is not None
    assert callable(server.run)

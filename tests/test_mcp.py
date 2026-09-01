"""MCP tool tests — call the agent-facing functions directly."""

from __future__ import annotations

import json

import pytest

pytest.importorskip("mcp")

from holdout_governance.mcp_server import (  # noqa: E402
    build_mcp_server,
    mcp_gov_attach,
    mcp_gov_check,
    mcp_gov_init,
    mcp_gov_report,
)

from m1_scenarios import build as build_m1  # noqa: E402
from m2_scenarios import build as build_m2  # noqa: E402


def test_mcp_check_blocks_defect(tmp_path) -> None:
    d = tmp_path / "defect"
    d.mkdir()
    build_m1(d, "no_evidence_record")
    payload = json.loads(mcp_gov_check(str(d / "artifact.json")))
    assert payload["decision"] == "block"
    assert payload["exit_code"] == 2
    assert "gate:evidence_integrity" in payload["missing"]


def test_mcp_report_assesses(tmp_path) -> None:
    d = tmp_path / "defect"
    d.mkdir()
    build_m1(d, "no_evidence_record")
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


def test_mcp_attach_then_check_releases(tmp_path) -> None:
    d = tmp_path / "agent"
    d.mkdir()
    build_m1(d, "no_evidence_record")
    attached = json.loads(mcp_gov_attach(
        str(d / "artifact.json"), gate="evidence_integrity", status="pass",
        tool="falsification-ledger", report_ref="sha256:ledger-1"))
    assert attached["error"] is None
    payload = json.loads(mcp_gov_check(str(d / "artifact.json")))
    assert payload["decision"] == "release"
    assert payload["exit_code"] == 0


def test_mcp_attach_public_copy_declaration(tmp_path) -> None:
    d = tmp_path / "copy"
    d.mkdir()
    build_m2(d, "copy_missing_sources")
    attached = json.loads(mcp_gov_attach(
        str(d / "artifact.json"),
        attachment="sources=docs/sources.md",
        declaration="contains_returns=true"))
    assert attached["attachments"]["sources"] == "docs/sources.md"
    assert attached["declarations"] == {"contains_returns": True}

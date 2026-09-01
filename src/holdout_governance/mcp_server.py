"""MCP server: exposes gov as agent-callable tools.

Requires the optional dependency: ``pip install 'holdout-governance[mcp]'``.

Tools:

- ``gov_check(manifest, policy?, gate_inputs?, kind?)`` — run the gate chain
- ``gov_report(manifest, policy?)`` — read-only assessment
- ``gov_init(dir, kind?, name?)`` — scaffold policy + artifact

Run with: ``gov mcp`` (stdio transport, standard for Claude / Cursor / etc.)
"""

from __future__ import annotations

import json
from typing import Any

from . import engine


def _json(result: dict[str, Any]) -> str:
    return json.dumps({k: v for k, v in result.items() if k != "artifact"},
                      ensure_ascii=False)


def mcp_gov_check(manifest: str, policy: str | None = None,
                  gate_inputs: str | None = None, kind: str | None = None) -> str:
    """Run the holdout gate chain on an artifact and decide.

    Args:
        manifest: path to artifact.json (v0.2)
        policy: optional path to policy.yml (default: next to manifest)
        gate_inputs: optional path to gate-inputs.json (default: next to manifest)
        kind: optional artifact kind override

    Returns:
        JSON with decision (release|review_needed|block), exit_code, missing,
        gates and policy_ref_ok. exit_code 2 means block — the artifact must
        not be published.
    """
    return _json(engine.run_check(manifest, policy=policy, gate_inputs=gate_inputs, kind=kind))


def mcp_gov_report(manifest: str, policy: str | None = None) -> str:
    """Read-only assessment of an artifact (v1 manifest or v0.2 artifact).

    Returns:
        JSON with decision/exit_code (v0.2) or passed/report (v1).
    """
    return _json(engine.run_report(manifest, policy=policy))


def mcp_gov_init(directory: str, kind: str = "research_conclusion",
                 name: str | None = None) -> str:
    """Scaffold policy.yml, gate-inputs.json and artifact.json in a directory.

    Returns:
        JSON with the created files and the policy_ref to record in the artifact.
    """
    return _json(engine.run_init(directory, kind=kind, name=name))


def build_mcp_server():
    """Build the FastMCP server (imports mcp lazily)."""
    try:
        from mcp.server.fastmcp import FastMCP
    except ImportError:  # older mcp layouts
        try:
            from mcp import FastMCP  # type: ignore[no-redef]
        except ImportError as exc:
            raise ImportError(
                "mcp not installed — run: pip install 'holdout-governance[mcp]'"
            ) from exc

    mcp = FastMCP("holdout-gov")

    def _register(fn, name: str, description: str):
        fn.__name__ = name
        fn.__doc__ = description
        return mcp.tool()(fn)

    _register(mcp_gov_check, "gov_check",
              "Run the holdout gate chain on a research artifact and decide "
              "release / review_needed / block.")
    _register(mcp_gov_report, "gov_report",
              "Read-only governance assessment of a research artifact.")
    _register(mcp_gov_init, "gov_init",
              "Scaffold a holdout policy + artifact project in a directory.")
    return mcp

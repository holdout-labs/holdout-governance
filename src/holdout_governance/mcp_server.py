"""MCP server: exposes gov as agent-callable tools.

Requires the optional dependency: ``pip install 'holdout-governance[mcp]'``.

Tools:

- ``gov_check(manifest, policy?, gate_inputs?, kind?)`` — run the gate chain
- ``gov_report(manifest, policy?)`` — read-only assessment
- ``gov_init(directory, kind?, name?)`` — scaffold policy + artifact
- ``gov_attach(...)`` — record evidence / review before checking

Run with: ``gov mcp`` (stdio transport, standard for Claude / Cursor / etc.)
"""

from __future__ import annotations

import json
from typing import Annotated, Any

from . import engine

try:  # pydantic is a hard dependency of the mcp SDK
    from pydantic import Field
except ImportError:  # pragma: no cover - only reachable without the mcp extra
    Field = None  # type: ignore[assignment]


def _json(result: dict[str, Any]) -> str:
    return json.dumps({k: v for k, v in result.items() if k != "artifact"},
                      ensure_ascii=False)


def mcp_gov_check(
    manifest: Annotated[
        str,
        Field(description="Path to artifact.json (holdout v0.2 manifest) that records the research run."),
    ],
    policy: Annotated[
        str | None,
        Field(description="Optional path to policy.yml. Defaults to policy.yml next to the manifest."),
    ] = None,
    gate_inputs: Annotated[
        str | None,
        Field(description="Optional path to gate-inputs.json. Defaults to gate-inputs.json next to the manifest."),
    ] = None,
    kind: Annotated[
        str | None,
        Field(
            description="Optional kind override, e.g. research_conclusion. Only use when the manifest's declared kind is wrong; otherwise leave unset."
        ),
    ] = None,
) -> str:
    """Run the full holdout gate chain on a research artifact and return the verdict as JSON.

    Executes every required gate of the artifact's kind with the real tools configured in
    gate-inputs (fail-closed: a missing tool, crash or timeout records not_run and blocks),
    then decides release / review_needed / block and writes the result back to the manifest.

    Use this as the final step before publishing any AI-assisted research claim — after
    gov_init created the project and gov_attach recorded the evidence. Do NOT call it before
    evidence is attached: missing required gates produce review_needed or block by design.

    The returned JSON includes decision, exit_code, missing, gates and policy_ref_ok.
    Treat exit_code 2 (block) as do-not-publish: the artifact must not be released.
    """
    return _json(engine.run_check(manifest, policy=policy, gate_inputs=gate_inputs, kind=kind))


def mcp_gov_report(
    manifest: Annotated[
        str,
        Field(description="Path to artifact.json (v0.2) or a v1 manifest to assess."),
    ],
    policy: Annotated[
        str | None,
        Field(description="Optional path to policy.yml. Defaults to policy.yml next to the manifest."),
    ] = None,
) -> str:
    """Read-only governance assessment of a research artifact, returned as JSON.

    Reports the current decision state, which required gates are missing, which passed or
    failed, and whether the policy reference matches — WITHOUT running any gate or changing
    any file.

    Use this to inspect an artifact before deciding what evidence to attach, or to check why
    a previous check did not release. Prefer gov_check when you want fresh gate execution;
    gov_report never mutates and never spawns tools.

    The returned JSON includes decision/exit_code (v0.2) or passed/report (v1).
    """
    return _json(engine.run_report(manifest, policy=policy))


def mcp_gov_init(
    directory: Annotated[
        str,
        Field(description="Directory to scaffold into. Created if missing (like mkdir -p)."),
    ],
    kind: Annotated[
        str,
        Field(
            description="Artifact kind, which selects the required gates: research_conclusion, strategy_advice, public_copy or code.",
        ),
    ] = "research_conclusion",
    name: Annotated[
        str | None,
        Field(description="Optional human-readable artifact id. Defaults to a timestamped id."),
    ] = None,
) -> str:
    """Scaffold a holdout governance project in a directory, returned as JSON.

    Writes policy.yml (kinds -> required_gates with severity) and gate-inputs.json if they do
    not exist yet, and creates a new artifact.json with decision=pending. Never overwrites an
    existing artifact.json: if one is already present it returns an error and writes nothing.

    Use this once at the start of a research run, before any evidence exists. Existing
    policy.yml / gate-inputs.json are kept untouched (policy-as-data: do not regenerate a
    hand-tuned policy). The returned JSON lists the created files and the policy_ref SHA to
    record; attach evidence afterwards with gov_attach, then decide with gov_check.
    """
    return _json(engine.run_init(directory, kind=kind, name=name))


def mcp_gov_attach(
    manifest: Annotated[
        str,
        Field(description="Path to artifact.json (v0.2) that will receive the evidence."),
    ],
    gate: Annotated[
        str | None,
        Field(description="gate_id to record together with status, e.g. data_integrity or temporal_integrity."),
    ] = None,
    status: Annotated[
        str | None,
        Field(description="Gate outcome: pass, fail, warn or not_run."),
    ] = None,
    tool: Annotated[
        str,
        Field(description="Name of the tool that produced the evidence, e.g. imm, padj, lf, fl, qc."),
    ] = "",
    report_ref: Annotated[
        str,
        Field(description="Evidence reference for the report file, e.g. sha256:<hex> or a relative path."),
    ] = "",
    attachment: Annotated[
        str | None,
        Field(description="Attachment as name=value, e.g. sources=docs/sources.md. Repeat by calling again."),
    ] = None,
    declaration: Annotated[
        str | None,
        Field(description="Declaration as name=true|false, e.g. contains_returns=true."),
    ] = None,
    review: Annotated[
        str | None,
        Field(description="Human review outcome: approved or not_recorded."),
    ] = None,
    reviewer: Annotated[
        str,
        Field(description="Name of the human reviewer (auditable declaration, not authentication)."),
    ] = "",
) -> str:
    """Attach gate evidence, attachments, declarations or a human review to an artifact.

    The decision is reset to pending — run gov_check afterwards to re-decide. Use this after a
    gate tool produced evidence (record gate + status + tool + report_ref) or after a human
    reviewed the run (review + reviewer). Attachments and declarations travel as name=value
    strings; repeated calls merge, they never drop existing entries.

    Do NOT use gov_attach to claim a gate passed when no tool ran — the journaled status is
    what gov_check trusts. The returned JSON shows the updated gates, attachments,
    declarations and review state.
    """
    attachments = {}
    if attachment and "=" in attachment:
        key, _, value = attachment.partition("=")
        attachments[key.strip()] = value.strip()
    declarations = {}
    if declaration and "=" in declaration:
        key, _, value = declaration.partition("=")
        if value in ("true", "false"):
            declarations[key.strip()] = value == "true"
    return _json(engine.run_attach(
        manifest, gate=gate, status=status, tool=tool, report_ref=report_ref,
        attachments=attachments, declarations=declarations,
        review=review, reviewer=reviewer,
    ))


def build_mcp_server():
    """Build the FastMCP server (imports mcp lazily)."""
    try:
        from mcp.server.fastmcp import FastMCP
    except ImportError:  # older mcp layouts
        try:
            from mcp import FastMCP  # type: ignore[no-redef]
        except ImportError as exc:
            raise ImportError(
                "mcp not installed - run: pip install 'holdout-governance[mcp]'"
            ) from exc

    mcp = FastMCP("holdout-gov")

    def _register(fn, name: str, description: str):
        fn.__name__ = name
        fn.__doc__ = description
        return mcp.tool()(fn)

    _register(mcp_gov_check, "gov_check",
              "Run the full holdout gate chain on a research artifact and return the "
              "verdict (release / review_needed / block) as JSON. Executes every required "
              "gate of the artifact kind with the real tools (fail-closed: missing tool, "
              "crash or timeout records not_run and blocks) and writes the result back. "
              "Use as the final step before publishing any AI-assisted research claim — "
              "after gov_init created the project and gov_attach recorded the evidence. "
              "Do NOT call it before evidence is attached: missing required gates produce "
              "review_needed or block by design. Returns decision, exit_code, missing, "
              "gates and policy_ref_ok; treat exit_code 2 (block) as do-not-publish.")
    _register(mcp_gov_report, "gov_report",
              "Read-only governance assessment of a research artifact, returned as JSON: "
              "current decision state, missing required gates, pass/fail per recorded gate, "
              "and policy reference check — WITHOUT running any gate or changing any file. "
              "Use to inspect an artifact before attaching evidence or to understand why a "
              "previous check did not release. Prefer gov_check for fresh gate execution; "
              "gov_report never mutates and never spawns tools.")
    _register(mcp_gov_init, "gov_init",
              "Scaffold a holdout governance project in a directory (created if missing): "
              "writes policy.yml and gate-inputs.json only if absent, and creates a new "
              "artifact.json with decision=pending. Never overwrites an existing "
              "artifact.json — if present it returns an error and writes nothing. Use once "
              "at the start of a research run, then attach evidence with gov_attach and "
              "decide with gov_check. Returns the created files and the policy_ref SHA.")
    _register(mcp_gov_attach, "gov_attach",
              "Attach gate evidence, attachments, declarations or a human review to an "
              "artifact (decision resets to pending — run gov_check afterwards). Record "
              "gate + status + tool + report_ref after a gate tool produced evidence, or "
              "review + reviewer after a human reviewed. Attachments/declarations are "
              "name=value strings; repeated calls merge, never drop existing entries. "
              "Do NOT claim a gate passed when no tool ran — gov_check trusts the journaled "
              "status. Returns the updated gates, attachments, declarations and review.")
    return mcp

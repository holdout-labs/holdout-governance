# Holdout Governance — Roadmap

Status: active development. `holdout-governance` is the release gate of the
Holdout toolchain: one artifact, one verdict, before anything ships. This
roadmap tracks both the product and the paradigm (evidence before assertion,
fail-closed by default, AI may propose but humans approve release).

## Shipped

- **Manifest model**: artifact (evidence, checks, AI usage, approval) +
  policy-as-data (`kinds` → `required_gates`, severity, missing-gate
  behaviour) + gate-inputs (per-gate tool commands).
- **Decision function**: fail-closed gate chain with `block` /
  `review_needed` / `release`, hash-chained evidence, policy-ref pinning.
- **CLI + MCP**: `gov init/check/report/attach/attach-run` and `gov mcp`
  (stdio server exposing `gov_check` / `gov_report` / `gov_init`), via the
  official MCP SDK (pinned `mcp<2` — mcp 2.x renamed FastMCP to MCPServer).
- **Real family wiring (verified end-to-end, 2026-09-02)**: `examples/gov-demo`
  runs the whole chain with the real Holdout tools — `imm audit`
  (ashare-data-immunity), `padj rebuild` + `padj drift-check` (pit-adjuster),
  `lf check` (lookahead-free), `fl verify` (falsification-ledger). Green path
  releases; appending one fake event to the hash-chained ledger flips the
  verdict to block (exit 2); restore flips it back. `qc check` (factor-qc) is
  wired for the `strategy_advice` kind.
- **Glama readiness**: Dockerfile (`pip install '.[mcp]'`, `CMD gov mcp`),
  `mcp.json`, `glama.json`; MCP handshake (initialize + tools/list) verified
  locally.

## Architecture direction: one agent entry, not one server per tool

The Holdout family is a *chain*, not a pile of CLI tools. Agents should face a
single governance entry — `gov` (CLI + MCP) — while the underlying tools
(`imm`, `padj`, `lf`, `fl`, `qc`) stay subprocess gates configured in
`gate-inputs`. Rationale:

- Each tool already speaks fail-closed exit codes (0 pass / 1 fail / 2 crash)
  and `--json`; the runner contract costs them nothing.
- One journal, one verdict, one policy file per artifact — splitting MCP
  endpoints per tool would fragment exactly the accountability this project
  exists to provide.
- Per-tool MCP servers are a distribution play, not an architecture play:
  add one only when a tool shows real agent-side demand (see below).

## Next

- **`strategy_advice` demo**: exercise the `qc check` (statistical_quality)
  path end-to-end with a real backtest artifact (requires NumPy; demo data +
  walkthrough).
- **Agent-framework session hooks**: end-of-session `gov check` for research
  agents (DSH / Claude Code), mirroring workspace-metabolism's
  end-of-loop ritual; wire via the MCP bridge.
- **Per-tool MCP (on demand only)**: if agents genuinely call `factor-qc` or
  `lookahead-free` mid-research-loop, expose that single tool as its own MCP
  server (TDQS-grade tool descriptions, Glama listing, same playbook as
  workspace-metabolism). Do not pre-build six servers with zero users.
- **Policy schema v2**: conditional gates by attachment content, gate
  provenance attestation, artifact diffing between revisions.
- **Benchmark**: gate-chain latency budget (N tools × M artifacts), worst-case
  ledger growth, `gc` for compacted evidence.

## Long term

- Governance as a standard research artifact: `artifact.json` as common as
  `.gitignore` for any AI-assisted research output.
- Cross-toolchain gate registry: reuse `imm`/`padj`/`lf`/`fl`/`qc` as gates in
  other governance layers (not just Holdout).

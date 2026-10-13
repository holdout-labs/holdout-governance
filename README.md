# Holdout Governance

Fail-closed evidence manifests for AI-assisted quantitative research.

This is not a factor library, a backtest engine, or a trading system.
`holdout-governance` is infrastructure for the moment when a financial AI
agent drafts a research conclusion, calls tools, attaches evidence, and asks
whether the result can move forward.

[![PyPI version](https://img.shields.io/pypi/v/holdout-governance)](https://pypi.org/project/holdout-governance)
[![Python](https://img.shields.io/pypi/pyversions/holdout-governance)](https://pypi.org/project/holdout-governance)
[![CI](https://img.shields.io/github/actions/workflow/status/holdout-labs/holdout-governance/ci.yml)](https://github.com/holdout-labs/holdout-governance/actions)
[![License: MIT](https://img.shields.io/github/license/holdout-labs/holdout-governance)](LICENSE)
[![Glama score](https://glama.ai/mcp/servers/holdout-labs/holdout-governance/badges/score.svg)](https://glama.ai/mcp/servers/holdout-labs/holdout-governance)

`holdout-governance` records one research run or AI-generated output as a small JSON manifest:

- what evidence artifacts were used;
- the latest allowed timestamp for the decision;
- which checks passed;
- whether AI was used, and which prompt version;
- whether a person approved the run; and
- that the result stays research-only.

It is a local validation tool. It does not fetch market data, call a model,
place orders, or give investment advice.

## Agent boundary

`holdout-governance` is the boundary around an AI-assisted research workflow.
An agent may draft a conclusion, run tools, and attach evidence, but the
manifest and policy decide whether the result can move forward. Missing
evidence blocks by default; warnings can be downgraded only when the policy
says so; final publication still belongs to a person or an external release
process.

This is the intended contract: AI can help produce research, but it cannot
silently skip evidence, erase accountability, or turn a draft into a released
decision on its own.

That makes Holdout different from the usual quant stack. The usual stack helps
you generate signals, test portfolios, and run execution. Holdout governs the
research artifact around that work: what evidence exists, what checks passed,
what policy was applied, and where human approval is required.

## Philosophy

Part of the [Holdout](https://github.com/holdout-labs) toolchain — the
governance layer. The name comes from the holdout set and the holdout juror:
the thing you do not touch early, and the person who does not go along until
the evidence is in.

The product philosophy is:

- evidence before assertion;
- default deny when evidence is missing;
- policy as data, not hard-coded judgment;
- AI may propose, but humans still approve release.

That means one manifest, one verdict, before anything ships.

## Product flow

This package is the wrapper above the other Holdout tools. The main flow is:

`data -> adjust -> timing -> backtest -> falsify -> review -> publish`

`holdout-governance` sits across that flow as the final release gate. It
records what was checked, what was attached, what remains missing, and whether
the result is approved for release.

## Quick start

```bash
python -m pip install -c tools/suite-constraints.txt ".[suite,research]"
gov doctor
python examples/demo.py
```

Validate a manifest:

```bash
gov validate --manifest examples/ai-research-manifest.json
gov report --manifest examples/ai-research-manifest.json
```

Check ledger health (fail-closed: bad json / duplicate ids / hash-chain
breaks / out-of-order timestamps):

```bash
gov health --ledger examples/gov-demo/ledger/ledger.jsonl
```

## Install and diagnose the toolchain

The `suite` extra installs the six companion tools at exact versions:

```bash
python -m pip install "holdout-governance[suite,research]==0.5.0"
gov doctor
```

From a source checkout, use
`python -m pip install -c tools/suite-constraints.txt ".[suite,research]"`.
[`tools/suite-constraints.txt`](tools/suite-constraints.txt) documents the supported
Holdout package combination; it does not lock transitive dependencies. The new
extra and commands are introduced in version 0.5.0.

`gov doctor` prints every package version, expected version, actual command path
and CLI version. Missing packages, missing commands, unsupported versions and
commands from a conflicting Python environment produce exit 1. `gov doctor --json`
provides the same diagnosis for automation; it does not run research or install
anything. Activate the Python environment where you installed the tools first.

The local synthetic research workbench uses the separate `research` extra:
run `holdout-research` after installing the extras above, or use
`Start-Factor-Research.cmd` from the source checkout. `holdout-research --check`
checks dependencies without creating a study or exposing final-test data.
The workbench uses public, reproducible synthetic data, not market-calibrated
returns. Final evaluation consumes one opportunity before accessing samples;
the shared registry rejects already used or overlapping samples across studies.
It is a trusted local workflow, not an OS sandbox. See the
[workbench guide](docs/factor-research-workbench.md) for limits and saved-run behavior.
Version 0.4.3 does not include this workbench.

## Real end-to-end demo

`examples/gov-demo/run_demo.py` runs **real** `imm` / `padj` / `lf` / `fl`
commands through `gov check` in a disposable copy of the fixtures. All generated
manifests, ledger edits and reports stay in that temporary directory. Failure
or interruption leaves the source fixtures unchanged.

```bash
python examples/gov-demo/run_demo.py        # Windows / Linux / macOS
bash examples/gov-demo/run-demo.sh          # Linux / macOS
pwsh -File examples/gov-demo/run-demo.ps1    # Windows PowerShell
```

What you should see:

```
1. GREEN PATH   real gate chain -> release (exit 0)
2. TAMPER       append an unchained synthetic ledger event
3. BLOCK        exit 2 AND evidence_integrity=fail
4. RESTORE      original ledger bytes -> release (exit 0)
5. STRATEGY     real qc gate on positive synthetic returns -> release (exit 0)
6. STRATEGY BLOCK negative synthetic returns -> block (exit 2), qc gate=fail
```

Exit 1, missing binaries and configuration errors are rejected as demo failures;
they cannot stand in for ledger tamper detection. The strategy attachments and
returns are synthetic fixtures, not a verified trading strategy or release
approval. CI installs this checkout plus six companion packages from fixed
commit IDs into a clean environment on Windows and Linux, runs `gov doctor`,
and then runs this chain. Unit tests with substituted processes do not replace
that integration check.

## GitHub Action (fail-closed gate in CI)

`holdout-labs/holdout-governance` is a reusable action that runs `gov check`
on your manifest. When the gate chain blocks (missing or stale evidence), the
action step fails — which is the point: nothing ships without evidence.

```yaml
steps:
  - uses: holdout-labs/holdout-governance@v0.5.0
    with:
      manifest: research/artifact.json     # path to your artifact.json
      # policy: research/policy.yml        # optional; defaults to beside the manifest
      # suite: "true"                     # install the supported companion tools
```

Notes:

- The updated action installs from its own downloaded source directory by default:
  `uses: ...@<tag-or-SHA>` selects both the action and the installed package.
  `ref` is an optional explicit installation override; it no longer defaults to `main`.
  Set `suite: "true"` to install the supported companion tools. Use a commit SHA for
  an immutable action reference. This behavior is introduced in v0.5.0.
- The gate needs its evidence tools on `PATH` (`imm` / `padj` / `lf` / `fl`)
  to ever pass; without them it **fails closed by design**. The tools live in
  the sibling repos: `falsification-ledger`, `pit-adjuster`, `factor-qc`,
  `lookahead-free`, `ashare-data-immunity`.
- Exit codes: `0` = release, `1` = review needed, `2` = block.

## Contract (v0.2, frozen)

The governance contract lives in `schema/` and is locked by tests:

- [`schema/artifact.schema.json`](schema/artifact.schema.json) — `holdout.artifact.v0.2`
- [`schema/policy.schema.json`](schema/policy.schema.json) + [`schema/policy.example.yml`](schema/policy.example.yml) — `holdout.policy.v0.1`
- [`examples/artifact.example.json`](examples/artifact.example.json) — a conforming `research_conclusion` artifact
- [`docs/migration-v1-to-v0.2.md`](docs/migration-v1-to-v0.2.md) — upgrade path from the v1 manifest

## gov check — scenario 1 (done, M1)

AI-generated research conclusions must pass data + timing + evidence gates
before they can ship:

```bash
# scaffold a research-conclusion project
gov init --dir research/ --name momentum-oos-review
# point gate-inputs.json at your data (imm / padj / lf / fl commands),
# then run the gate chain and decide:
gov check --manifest research/artifact.json
#   exit 0 = release, 1 = review_needed, 2 = block
# artifact.json is written back with decision, missing and gate evidence;
# raw tool outputs are persisted under research/reports/ (sha256-referenced)

gov report --manifest research/artifact.json   # human-readable
```

## gov attach (done)

Attach evidence to an artifact before checking — the agent workflow:

```bash
gov attach --manifest research/artifact.json \
  --gate data_integrity --status pass --tool imm --report-ref sha256:...
gov attach --manifest research/artifact.json --attachment sources=docs/sources.md
gov attach --manifest research/artifact.json --declaration contains_returns=true
gov attach --manifest research/artifact.json --review approved --reviewer research-owner
```

Attaching evidence **resets `decision` to `pending`** — a decision is only as
good as the evidence it was computed from, so any evidence change invalidates
it until the next `gov check`. The same operation is exposed to agents as the
`gov_attach` MCP tool.

## Stable evidence fingerprints (done)

`report_ref` is a `sha256:` of the gate's tool output. Some tools stamp their
output with run-time fields (`imm audit` emits `checked_at` / `audit_date`),
so re-running the same check on the same data would change the fingerprint
and dirty every `artifact.json` diff. Gate specs can declare those fields:

```json
{
  "data_integrity": {
    "cmd": ["imm", "audit", "--watchlist", "watchlist.json", "--history-root", "history", "--audit-root", "audit"],
    "volatile_keys": ["audit_date", "checked_at"]
  }
}
```

`volatile_keys` are stripped (deep) from the JSON before hashing, with keys
sorted for a canonical form. The **raw** tool output is still persisted as
the gate report and the real run time stays in the gate entry's `run_at` —
nothing is lost, only the noise stops changing the fingerprint. Non-JSON
output keeps its byte-exact hash.

The acceptance suite (`tests/test_m1_scenario1.py`) runs 10 seeded-defect
samples (survivorship ×3, look-ahead ×3, adjustment drift ×2, missing
evidence ×2) against the *real* `imm` / `lf` / `padj` binaries — all 10 are
blocked, zero false passes — plus a clean control that must release.

## Evidence semantics (done)

Two attestation failures found by a production evidence grill (2026-09) are
machine-checkable on the manifest: *same-source evidence counted as
independent* and *a claimed data cutoff later than the run that produced
it* (a `now - lag` stamp pretending to be a historical section).

Gate entries may attest two optional fields (`gov attach`, CLI or MCP):

```bash
gov attach --manifest research/artifact.json --gate pit_integrity \
  --status pass --tool padj --report-ref sha256:... \
  --evidence-source feed-a --data-cutoff 2026-09-06T14:59:00+08:00
```

- `evidence_source` — which data lineage the gate evidence rests on;
- `data_cutoff` — the data time the evidence reflects (not the run time).

Attestation is **opt-in**: an artifact that declares neither field anywhere
keeps the legacy semantics (a placeholder `report_ref` may legitimately
back several gate entries in manual-attach flows). Once any gate attests,
`gov check` / `gov report` enforce these rules fail-closed on the whole
artifact:

- `duplicate_evidence_content` — two gate entries with the same
  `report_ref`: the same bytes counted twice;
- `data_cutoff_after_run_at` — declared data time later than the run that
  produced the evidence: impossible by construction;
- `same_source_slice_not_independent` — two `pass` gates declaring the same
  `evidence_source` *and* the same `data_cutoff`: one time slice cannot
  confirm twice, whatever the byte content (volatile stamps differ, the
  information does not);
- warnings (not blockers): `same_source_multiple` (sequential slices from
  one source are complementary, not independent) and
  `attestation_incomplete` (a cutoff without a source cannot be checked).

Run the same check standalone (read-only):

```bash
gov evidence --manifest research/artifact.json
```

## Scenarios 2 & 3 (done, M2)

- **strategy_advice** — must carry backtest evidence: `backtest_report` and
  `robustness_report` attachments, plus the `statistical_quality` gate
  (real `qc` run). A backtest whose `n_trials` is not declared is a
  *refusal*, not a failure: `qc` refuses to judge → `review_needed`. A real
  overfitting blocker (DSR/PBO/haircut/MinTRL) → `block`. Acceptance suite:
  `tests/test_m2_scenario23.py`.
- **public_copy** — must carry `sources`; when the copy declares return
  figures (`declarations.contains_returns`), `limitations` becomes required
  (conditional attachment, expressed in `policy.yml`, not code). A passing
  `gov report` prints the attachments and serves as the publication note.

Contract extension (frozen): `artifact.declarations` (boolean flags) and
policy `conditional_attachments` (`when`/`require`).

## Release integration (done, M3)

- **CI** — `.github/workflows/ci.yml`: pytest matrix (3.11/3.12) + a
  fail-closed smoke (scaffold → `gov check` must exit 2 without evidence).
- **Reusable action** — `.github/actions/gov-check`: composite action that
  runs `gov check` on any artifact in your workflows.
- **pre-commit hook** — `.pre-commit-hooks.yaml`: `gov check --manifest`
  on every `artifact.json`; a block refuses the commit. Wire it with:

  ```yaml
  # .pre-commit-config.yaml
  repos:
    - repo: https://github.com/holdout-labs/holdout-governance
      rev: v0.5.0
      hooks:
        - id: gov-check
  ```

- **Agent interface** — two ways to call gov from code/agents:
  - `gov api --port 8000` — stdlib HTTP JSON API: `GET /health`,
    `POST /check` / `/report` / `/init` (no extra dependencies).
  - `gov mcp` — MCP stdio server (`pip install 'holdout-governance[mcp]'`)
    exposing `gov_check`, `gov_report`, `gov_init`, `gov_attach` tools for
    Claude / Cursor / any MCP client.

## Fit

Use this package as the wrapper above the existing Holdout tools:

| Need | Existing tool |
| --- | --- |
| Data quality and snapshots | `ashare-data-immunity` |
| Point-in-time price meaning | `pit-adjuster` |
| Timing and future-data leakage | `lookahead-free` |
| Backtest quality | `factor-qc` |
| Claims and evidence trail | `falsification-ledger` |
| Past mistakes and reminders | `lesson-book` |

This package records that the checks passed. It does not authorize execution.

## Verify a PyPI release

Each of the seven package repositories now has `verify-pypi.yml`. A published
GitHub release verifies its tag version on PyPI; the same workflow can be started
manually with an explicit version after a separate upload. It uses a pinned
`pypi-verify-action`, installs the exact version into a fresh environment and checks
packaged modules, package/CLI version consistency and help output. It never uploads
anything. A GitHub release made before the PyPI upload will fail verification until
the version is available; rerun after uploading rather than treating the release
page alone as proof of a usable package.

## Development

```bash
python -m pip install -e .[test] pytest
python -m pytest
```

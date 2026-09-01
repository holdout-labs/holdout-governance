# Holdout Governance

Fail-closed evidence manifests for financial AI research.

`holdout-governance` records one research run as a small JSON manifest:

- what evidence artifacts were used;
- the latest allowed timestamp for the decision;
- which checks passed;
- whether AI was used, and which prompt version;
- whether a person approved the run; and
- that the result stays research-only.

It is a local validation tool. It does not fetch market data, call a model,
place orders, or give investment advice.

## Why the name

Part of the [Holdout](https://github.com/holdout-labs) toolchain — the
governance layer. A *holdout set* is the data you don't touch until the very
end; a *holdout juror* is the one who won't go along until the evidence is
in. This package is the juror: one manifest, one verdict, before anything
ships.

## Quick start

```bash
python -m pip install -e . pytest
python examples/demo.py
```

Validate a manifest:

```bash
gov validate --manifest examples/ai-research-manifest.json
gov report --manifest examples/ai-research-manifest.json
```

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

The acceptance suite (`tests/test_m1_scenario1.py`) runs 10 seeded-defect
samples (survivorship ×3, look-ahead ×3, adjustment drift ×2, missing
evidence ×2) against the *real* `imm` / `lf` / `padj` binaries — all 10 are
blocked, zero false passes — plus a clean control that must release.

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

## Development

```bash
python -m pip install -e .[test] pytest
python -m pytest
```

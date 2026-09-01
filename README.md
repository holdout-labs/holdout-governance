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

## Contract (v0.2, freezing)

The governance contract lives in `schema/` and is locked by tests:

- [`schema/artifact.schema.json`](schema/artifact.schema.json) — `holdout.artifact.v0.2`
- [`schema/policy.schema.json`](schema/policy.schema.json) + [`schema/policy.example.yml`](schema/policy.example.yml) — `holdout.policy.v0.1`
- [`examples/artifact.example.json`](examples/artifact.example.json) — a conforming `research_conclusion` artifact
- [`docs/migration-v1-to-v0.2.md`](docs/migration-v1-to-v0.2.md) — upgrade path from the v1 manifest

Next: `gov check` / `gov report` evaluate artifacts against a policy
(decision = `release | review_needed | block`).

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

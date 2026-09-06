# Changelog

## [0.4.3] - 2026-09-06
- feat: evidence-semantics attestation — gate entries may declare
  `evidence_source` (which data lineage the evidence rests on) and
  `data_cutoff` (the data time the evidence reflects) via `gov attach`
  (`--evidence-source` / `--data-cutoff`, also on the `gov_attach` MCP
  tool). Opt-in: once any gate attests, `gov check` / `gov report` enforce
  fail-closed — `duplicate_evidence_content` (same report_ref counted
  twice), `data_cutoff_after_run_at` (a `now - lag` cutoff forgery is
  impossible by construction), `same_source_slice_not_independent` (two
  pass gates, one source, one declared time slice = one piece of
  evidence); warnings: `same_source_multiple` (sequential slices are
  complementary, not independent) and `attestation_incomplete`. Standalone
  read-only check: `gov evidence --manifest`. Backfilled from a 2026-09
  production evidence grill (dual-snapshot generator + same-source
  double-counting).

## [0.4.1] - 2026-09-03
- feat: `gov health` — fail-closed ledger health check (bad json / missing fields / duplicate record ids / event-hash & prev-hash chain / recorded-at order; legacy rows re-anchored). Dogfood backfill of the internal governance ledger health check.

## [0.4.0] - 2026-09-01
- Initial release: fail-closed evidence manifests — policy + gates + decision (`gov check/report/attach`), legacy v1 validation, HTTP JSON API and MCP server, gov-demo end-to-end chain, stable evidence fingerprints, Glama packaging.

# Changelog

## [0.4.1] - 2026-09-03
- feat: `gov health` — fail-closed ledger health check (bad json / missing fields / duplicate record ids / event-hash & prev-hash chain / recorded-at order; legacy rows re-anchored). Dogfood backfill of the internal governance ledger health check.

## [0.4.0] - 2026-09-01
- Initial release: fail-closed evidence manifests — policy + gates + decision (`gov check/report/attach`), legacy v1 validation, HTTP JSON API and MCP server, gov-demo end-to-end chain, stable evidence fingerprints, Glama packaging.

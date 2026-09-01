#!/usr/bin/env bash
# gov chain demo - real tools, real verdicts
# Green path -> tamper -> block path -> restore -> green path
set -euo pipefail

d="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ledger="$d/ledger/ledger.jsonl"
cd "$d"

echo
echo '== 1. GREEN PATH: run the full gate chain (imm, padj, lf, fl) =='
gov check --manifest artifact.json --json
echo '=> decision: release (exit 0)'

echo
echo '== 2. TAMPER: append a fake event to the hash-chained ledger =='
printf '%s\n' '{"event":"register","case_id":"FAKE-CASE","recorded_at":"2026-09-02T00:00:00+08:00","reason":"tampered"}' >> "$ledger"

echo
echo '== 3. RED PATH: the chain must block =='
if gov check --manifest artifact.json --json; then
  echo 'ERROR: expected block' >&2
  exit 1
fi
echo '=> decision: block (exit 2) - hash chain detected the edit'

echo
echo '== 4. RESTORE ledger and re-check =='
sed -i '$d' "$ledger"
gov check --manifest artifact.json --json
echo '=> decision: release (exit 0) - restored'

echo
echo 'Done. The gate chain is wired: real tools, fail-closed verdicts, hash-chained audit.'

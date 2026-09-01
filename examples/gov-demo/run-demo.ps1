# gov chain demo - real tools, real verdicts
# Green path -> tamper -> block path -> restore -> green path
$ErrorActionPreference = 'Stop'
$d = Split-Path -Parent $MyInvocation.MyCommand.Path
Push-Location $d
$ledger = Join-Path $d 'ledger\ledger.jsonl'

Write-Host ''
Write-Host '== 1. GREEN PATH: run the full gate chain (imm, padj, lf, fl) ==' -ForegroundColor Cyan
gov check --manifest artifact.json --json
if ($LASTEXITCODE -ne 0) { throw 'expected release' }
Write-Host '=> decision: release (exit 0)' -ForegroundColor Green

Write-Host ''
Write-Host '== 2. TAMPER: append a fake event to the hash-chained ledger ==' -ForegroundColor Cyan
$fake = '{"event":"register","case_id":"FAKE-CASE","recorded_at":"2026-09-02T00:00:00+08:00","reason":"tampered"}'
[System.IO.File]::AppendAllText($ledger, $fake + "`n", (New-Object System.Text.UTF8Encoding($false)))

Write-Host ''
Write-Host '== 3. RED PATH: the chain must block ==' -ForegroundColor Cyan
gov check --manifest artifact.json --json
if ($LASTEXITCODE -eq 0) { throw 'expected block' }
Write-Host '=> decision: block (exit 2) - hash chain detected the edit' -ForegroundColor Red

Write-Host ''
Write-Host '== 4. RESTORE ledger and re-check ==' -ForegroundColor Cyan
$lines = Get-Content $ledger
[System.IO.File]::WriteAllLines($ledger, $lines[0..($lines.Count - 2)], (New-Object System.Text.UTF8Encoding($false)))
gov check --manifest artifact.json --json
if ($LASTEXITCODE -ne 0) { throw 'expected release after restore' }
Write-Host '=> decision: release (exit 0) - restored' -ForegroundColor Green

Pop-Location
Write-Host ''
Write-Host 'Done. The gate chain is wired: real tools, fail-closed verdicts, hash-chained audit.' -ForegroundColor Cyan

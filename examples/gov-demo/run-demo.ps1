param([string]$Python = 'python')
# All writes happen in the Python runner's disposable copy.
$ErrorActionPreference = 'Stop'
& $Python (Join-Path $PSScriptRoot 'run_demo.py')
exit $LASTEXITCODE

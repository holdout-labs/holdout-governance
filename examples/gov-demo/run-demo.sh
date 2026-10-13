#!/usr/bin/env bash
# All writes happen in the Python runner's disposable copy.
set -euo pipefail
d="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec "${PYTHON:-python}" "$d/run_demo.py"

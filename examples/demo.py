"""Run the included AI research governance example."""

from __future__ import annotations

from pathlib import Path

from holdout_governance.cli import main

MANIFEST = Path(__file__).with_name("ai-research-manifest.json")

assert main(["validate", "--manifest", str(MANIFEST)]) == 0
assert main(["report", "--manifest", str(MANIFEST)]) == 0

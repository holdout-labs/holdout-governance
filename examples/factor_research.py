"""Launch the local workbench, or pass research CLI arguments explicitly."""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

if __name__ == "__main__":
    arguments = sys.argv[1:]
    if not arguments or arguments == ["--check"]:
        from holdout_governance.research_ui import main as desktop
        raise SystemExit(desktop(["--dir", str(ROOT / "research-runs"), *arguments]))
    from holdout_governance.cli import main
    raise SystemExit(main(["research", *arguments]))

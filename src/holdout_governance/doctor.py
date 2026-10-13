"""Read-only diagnosis of the supported Holdout tool version combination."""
from __future__ import annotations
import importlib.metadata
import re
import shutil
import subprocess
import sys
from . import __version__

# A tested package combination, not a lock of transitive dependencies.
SUITE = (
    ("holdout-governance", "gov", __version__),
    ("ashare-data-immunity", "imm", "0.1.4"),
    ("pit-adjuster", "padj", "0.1.5"),
    ("lookahead-free", "lf", "0.1.3"),
    ("factor-qc", "qc", "0.1.3"),
    ("falsification-ledger", "fl", "0.1.4"),
    ("lesson-book", "lb", "0.1.2"),
)


def check_suite() -> dict:
    """Compare package metadata and each PATH command's actual version."""
    tools = []
    for package, command, expected in SUITE:
        issues = []
        try:
            version = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:
            version = None
            issues.append("package is missing from this Python environment")
        if version is not None and version != expected:
            issues.append(f"unsupported package version: expected {expected}, got {version}")
        path = shutil.which(command)
        cli_version = None
        if not path:
            issues.append("command is missing from PATH; activate the install environment")
        else:
            try:
                result = subprocess.run([path, "version"], capture_output=True, text=True,
                                        timeout=10, encoding="utf-8", errors="replace")
                if result.returncode:
                    issues.append(f"version command failed with exit {result.returncode}")
                else:
                    output = result.stdout.strip()
                    if len(output) > 128 or not re.fullmatch(r"[0-9]+(?:\.[0-9]+)*(?:a[0-9]+|b[0-9]+|rc[0-9]+|\.post[0-9]+|\.dev[0-9]+)?", output):
                        issues.append("version command returned an unexpected response (body omitted)")
                    else:
                        cli_version = output
                        if cli_version != version:
                            issues.append(f"PATH command version {cli_version!r} does not match "
                                          f"this Python's package version {version!r}")
            except (OSError, subprocess.TimeoutExpired) as exc:
                issues.append(f"cannot read command version: {type(exc).__name__}")
        tools.append({"package": package, "command": command, "version": version,
                      "expected_version": expected, "path": path,
                      "cli_version": cli_version, "issues": issues})
    return {"ok": all(not tool["issues"] for tool in tools),
            "python": sys.executable, "tools": tools}

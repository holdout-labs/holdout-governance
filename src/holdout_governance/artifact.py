"""Artifact (v0.2) loading, validation and mutation."""

from __future__ import annotations

import json
from pathlib import Path

import jsonschema

from ._schemas import ARTIFACT_SCHEMA, V1_MANIFEST_PREFIX


def load_artifact(path: Path | str) -> dict:
    """Load and validate a holdout.artifact.v0.2 file. Raises ValueError."""
    p = Path(path)
    data = json.loads(p.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"artifact must be a JSON object: {p}")
    try:
        jsonschema.validate(data, ARTIFACT_SCHEMA, format_checker=jsonschema.FormatChecker())
    except jsonschema.ValidationError as exc:
        raise ValueError(f"artifact does not conform to artifact.schema.json: {exc.message}") from exc
    return data


def save_artifact(path: Path | str, artifact: dict) -> None:
    text = json.dumps(artifact, ensure_ascii=False, indent=2) + "\n"
    Path(path).write_text(text, encoding="utf-8")


def is_v1_manifest(data: dict) -> bool:
    return str(data.get("schema_version", "")).startswith(V1_MANIFEST_PREFIX)


def merge_gate_result(artifact: dict, gate_id: str, result: dict) -> dict:
    """Record a runner result into the artifact's gates list (replace or append)."""
    entry = {
        "gate_id": gate_id,
        "tool": result.get("tool", ""),
        "status": result["status"],
        "report_ref": result.get("report_ref", ""),
        "tool_version": result.get("tool_version", ""),
        "run_at": result.get("run_at", ""),
    }
    if result.get("reason"):
        entry["reason"] = result["reason"][:500]
    gates = [gate for gate in artifact.get("gates", []) if gate.get("gate_id") != gate_id]
    gates.append(entry)
    artifact["gates"] = gates
    return artifact

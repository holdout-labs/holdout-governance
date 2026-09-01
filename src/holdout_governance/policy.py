"""Policy loading for holdout v0.2: YAML + schema validation + hashing."""

from __future__ import annotations

import hashlib
from pathlib import Path

import jsonschema
import yaml

from ._schemas import POLICY_SCHEMA


def sha256_file(path: Path | str) -> str:
    """Content hash in the ``sha256:`` form used by policy_ref / report_ref."""
    digest = hashlib.sha256(Path(path).read_bytes()).hexdigest()
    return f"sha256:{digest}"


def sha256_text(text: str) -> str:
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    return f"sha256:{digest}"


def load_policy(path: Path | str) -> dict:
    """Load and validate a policy.yml. Raises ValueError on any problem."""
    p = Path(path)
    text = p.read_text(encoding="utf-8")
    data = yaml.safe_load(text)
    if not isinstance(data, dict):
        raise ValueError(f"policy must be a YAML mapping: {p}")
    try:
        jsonschema.validate(data, POLICY_SCHEMA)
    except jsonschema.ValidationError as exc:
        raise ValueError(f"policy does not conform to policy.schema.json: {exc.message}") from exc
    return data

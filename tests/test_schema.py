"""Lock the v0.2 contract: both schemas must be valid JSON Schemas, and the
included examples must conform to them."""

from __future__ import annotations

import json
from pathlib import Path

import jsonschema
import yaml

REPO = Path(__file__).resolve().parents[1]
SCHEMAS = REPO / "schema"


def _load_schema(name: str) -> dict:
    return json.loads((SCHEMAS / name).read_text(encoding="utf-8"))


def test_artifact_schema_is_valid_json_schema() -> None:
    jsonschema.Draft202012Validator.check_schema(_load_schema("artifact.schema.json"))


def test_policy_schema_is_valid_json_schema() -> None:
    jsonschema.Draft202012Validator.check_schema(_load_schema("policy.schema.json"))


def test_example_artifact_conforms_to_schema() -> None:
    artifact = json.loads(
        (REPO / "examples" / "artifact.example.json").read_text(encoding="utf-8")
    )
    jsonschema.validate(
        artifact,
        _load_schema("artifact.schema.json"),
        format_checker=jsonschema.FormatChecker(),
    )


def test_example_policy_conforms_to_schema() -> None:
    policy = yaml.safe_load((SCHEMAS / "policy.example.yml").read_text(encoding="utf-8"))
    jsonschema.validate(policy, _load_schema("policy.schema.json"))


def test_embedded_schemas_match_schema_files() -> None:
    """The package embeds the contract; the drift test keeps both in sync."""
    from holdout_governance._schemas import ARTIFACT_SCHEMA, DEFAULT_POLICY, POLICY_SCHEMA

    assert ARTIFACT_SCHEMA == _load_schema("artifact.schema.json")
    assert POLICY_SCHEMA == _load_schema("policy.schema.json")
    assert yaml.safe_load(DEFAULT_POLICY) == yaml.safe_load(
        (SCHEMAS / "policy.example.yml").read_text(encoding="utf-8")
    )

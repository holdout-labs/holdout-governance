"""Embedded copies of the v0.2 contract: schemas and templates.

Kept in sync with ``schema/*.json`` and ``schema/policy.example.yml`` by
``tests/test_schema.py`` (drift test). Do not edit the embedded copies
without updating the schema files, and vice versa.
"""

from __future__ import annotations

import json

ARTIFACT_SCHEMA = json.loads(
    r"""
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "https://github.com/holdout-labs/holdout-governance/blob/main/schema/artifact.schema.json",
  "title": "holdout artifact v0.2",
  "description": "Evidence manifest for any research artifact (conclusion, strategy advice, public copy, code). Evolved from grand_truth_governance.research_manifest.v1 — see docs/migration-v1-to-v0.2.md.",
  "type": "object",
  "required": ["schema_version", "artifact", "producer", "gates", "policy_ref", "decision"],
  "properties": {
    "schema_version": {
      "const": "holdout.artifact.v0.2"
    },
    "artifact": {
      "type": "object",
      "required": ["id", "kind", "created_at"],
      "properties": {
        "id": { "type": "string", "minLength": 1 },
        "kind": {
          "enum": ["research_conclusion", "strategy_advice", "public_copy", "code"]
        },
        "created_at": { "type": "string", "format": "date-time" }
      }
    },
    "producer": {
      "type": "object",
      "required": ["type"],
      "properties": {
        "type": { "enum": ["ai", "human", "hybrid"] },
        "model_id": { "type": "string", "minLength": 1 },
        "prompt_version": { "type": "string", "minLength": 1 },
        "input_refs": {
          "type": "array",
          "items": { "type": "string", "pattern": "^sha256:" }
        }
      }
    },
    "gates": {
      "type": "array",
      "items": {
        "type": "object",
        "required": ["gate_id", "tool", "status"],
        "properties": {
          "gate_id": { "type": "string", "minLength": 1 },
          "tool": { "type": "string", "minLength": 1 },
          "status": { "enum": ["pass", "fail", "warn", "not_run"] },
          "report_ref": { "type": "string" },
          "tool_version": { "type": "string" }
        }
      }
    },
    "attachments": {
      "type": "object",
      "additionalProperties": { "type": "string" }
    },
    "declarations": {
      "type": "object",
      "additionalProperties": { "type": "boolean" }
    },
    "review": {
      "type": "object",
      "properties": {
        "status": { "enum": ["approved", "not_recorded"] },
        "reviewer": { "type": "string" }
      }
    },
    "safety": {
      "type": "object",
      "properties": {
        "places_orders": { "const": false },
        "changes_trading_rules": { "const": false },
        "provides_investment_advice": { "const": false }
      }
    },
    "policy_ref": { "type": "string", "pattern": "^sha256:" },
    "decision": { "enum": ["release", "review_needed", "block", "pending"] },
    "missing": { "type": "array", "items": { "type": "string" } }
  }
}
"""
)

POLICY_SCHEMA = json.loads(
    r"""
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "https://github.com/holdout-labs/holdout-governance/blob/main/schema/policy.schema.json",
  "title": "holdout policy v0.1",
  "description": "Policy-as-data: what gates and attachments each artifact kind requires, and how missing/warned items are treated.",
  "type": "object",
  "required": ["schema_version", "kinds", "defaults"],
  "properties": {
    "schema_version": {
      "const": "holdout.policy.v0.1"
    },
    "kinds": {
      "type": "object",
      "propertyNames": {
        "enum": ["research_conclusion", "strategy_advice", "public_copy", "code"]
      },
      "additionalProperties": {
        "type": "object",
        "required": ["required_gates", "severity"],
        "properties": {
          "required_gates": {
            "type": "array",
            "items": { "type": "string" }
          },
          "required_attachments": {
            "type": "array",
            "items": { "type": "string" }
          },
          "conditional_attachments": {
            "type": "array",
            "items": {
              "type": "object",
              "required": ["when", "require"],
              "properties": {
                "when": {
                  "type": "object",
                  "additionalProperties": { "type": "boolean" }
                },
                "require": {
                  "type": "array",
                  "items": { "type": "string" }
                }
              }
            }
          },
          "severity": { "enum": ["block", "warn", "info"] },
          "requires_review": { "type": "boolean" }
        }
      }
    },
    "defaults": {
      "type": "object",
      "properties": {
        "missing_gate": { "enum": ["block", "review_needed"] },
        "gate_warn": { "enum": ["block", "review_needed"] }
      }
    }
  }
}
"""
)

DEFAULT_POLICY = """# Holdout policy — default generated by `gov init`.
# See schema/policy.schema.json for the contract and PRD §3.3 for the
# decision function. Edit freely, then update artifact.policy_ref:
#   python -c "import hashlib;print('sha256:'+hashlib.sha256(open('policy.yml','rb').read()).hexdigest())"

schema_version: holdout.policy.v0.1

kinds:
  research_conclusion:
    required_gates: [data_integrity, pit_integrity, temporal_integrity, evidence_integrity]
    severity: block

  strategy_advice:
    required_gates: [data_integrity, temporal_integrity, statistical_quality, evidence_integrity]
    required_attachments: [backtest_report, robustness_report]
    severity: block

  public_copy:
    required_gates: [provenance]
    required_attachments: [sources]
    conditional_attachments:
      - when: {contains_returns: true}
        require: [limitations]
    severity: block

  code:
    required_gates: [temporal_integrity]
    severity: warn

defaults:
  missing_gate: block
  gate_warn: review_needed
"""

GATE_INPUTS_TEMPLATE = """{
  "data_integrity": {
    "cmd": ["imm", "audit", "--watchlist", "watchlist.json", "--history-root", "history", "--audit-root", "audit"]
  },
  "pit_integrity": {
    "steps": [
      ["padj", "rebuild", "--bars", "bars.json", "--actions", "actions.json", "--as-of", "YYYY-MM-DD", "--code", "600000", "--out", "rebuilt.json"],
      ["padj", "drift-check", "--bars", "rebuilt.json", "--actions", "actions.json", "--as-of", "YYYY-MM-DD", "--live", "live.json"]
    ]
  },
  "temporal_integrity": {
    "cmd": ["lf", "check", "--pipeline", "pipeline.json", "--json"]
  },
  "evidence_integrity": {
    "cmd": ["fl", "verify", "--ledger", "ledger.jsonl"]
  },
  "statistical_quality": {
    "cmd": ["qc", "check", "--returns", "returns.json", "--n-trials", "200", "--json"],
    "warn_verdict_prefix": "FAIL - n_trials"
  }
}
"""

ARTIFACT_SCHEMA_VERSION = "holdout.artifact.v0.2"
POLICY_SCHEMA_VERSION = "holdout.policy.v0.1"
V1_MANIFEST_PREFIX = "holdout_governance.research_manifest.v1"

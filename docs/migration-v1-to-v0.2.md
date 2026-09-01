# Migration: research_manifest.v1 → holdout.artifact.v0.2

The v1 manifest (`holdout_governance.research_manifest.v1`, formerly
`grand_truth_governance.research_manifest.v1`) is the single-kind prototype.
v0.2 generalizes it to any artifact kind and moves policy out of code into
`policy.yml`.

## Field mapping

| v1 (research_manifest.v1)            | v0.2 (holdout.artifact.v0.2)          | Notes |
| :---                                 | :---                                  | :--- |
| `schema_version`                     | `schema_version`                      | value changes to `holdout.artifact.v0.2` |
| `research_id`                        | `artifact.id`                         | renamed |
| *(none — always research manifest)*  | `artifact.kind`                       | **new**; v1 research manifest maps to `research_conclusion` |
| `created_at` *(absent in v1)*        | `artifact.created_at`                 | **new**, required |
| `scope.purpose` (`research_only`)    | *(dropped)*                           | kind + safety carry the semantics now |
| `scope.decision_cutoff`              | *(dropped — see Notes)*               | becomes the `as_of`/`run_at` discipline of gates; keep as an attachment if needed |
| `inputs[].artifact_id` (`sha256:`)   | `producer.input_refs[]`               | renamed |
| `inputs[].source`                    | *(dropped)*                           | free text; keep in gate report_refs instead |
| `inputs[].as_of`                     | *(dropped — see decision_cutoff)*     | same as above |
| `checks[]` (`check_id`/`tool`/`status: passed`) | `gates[]` (`gate_id`/`tool`/`status: pass\|fail\|warn\|not_run`) | statuses widened; `report_ref`/`tool_version` added |
| `agent.used`                         | `producer.type` (`ai\|human\|hybrid`) | `used: true` → `type: ai`; `used: false` → `type: human` |
| `agent.model_id`                     | `producer.model_id`                   | only required when `type: ai` |
| `agent.prompt_version`               | `producer.prompt_version`             | only required when `type: ai` |
| `review.status` (`approved`)         | `review.status` (`approved\|not_recorded`) | unchanged semantics; required when `type: ai` |
| `safety.*`                           | `safety.*`                            | unchanged, still all `false` |
| `conclusion` (`research_only`)       | *(dropped)*                           | governed by kind + policy, not a free-text field |
| *(hardcoded REQUIRED_CHECKS)*        | `policy_ref` + `policy.yml`           | **new**; policy becomes data |
| *(absent)*                           | `decision` / `missing`                | **new**; written by `gov check` |

## Breaking changes

1. Schema id and version strings change (`holdout.artifact.v0.2`,
   `holdout.policy.v0.1`).
2. `research_id` → `artifact.id`; manifests must declare `artifact.kind`.
3. `checks[]` requires `gate_id` (v1 `check_id`) and allows `fail`/`warn`.
4. AI runs require `producer.type: "ai"` + `model_id` + `prompt_version` +
   `review.status: approved` (same rule as v1, new location).
5. Policy is no longer hardcoded: `policy_ref` points at the `policy.yml`
   used; a manifest without a policy is invalid.
6. v1 files validate as *research_conclusion* only after migration; run the
   field mapping above mechanically, then re-run `gov validate`.

## Migration procedure

1. Map fields per the table (scripted one-liner is fine — no logic changes).
2. Pick the kind: research manifests → `research_conclusion`.
3. Keep `safety` unchanged; keep `review` when AI was used.
4. Point `policy_ref` at the sha256 of the active `policy.yml`.
5. `gov validate` must pass before `gov report` is meaningful.

Schema files: `schema/artifact.schema.json`, `schema/policy.schema.json`.

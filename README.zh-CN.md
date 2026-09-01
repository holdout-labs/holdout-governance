# Holdout Governance（治理层）

**金融 AI 研究的 fail-closed 证据清单（evidence manifest）。**

`holdout-governance` 把一次研究过程记录成一份小型 JSON 清单：

- 用了哪些证据工件；
- 决策允许的最新时间戳；
- 哪些检查通过了；
- 是否用了 AI、用的哪个 prompt 版本；
- 是否有人审批；
- 结果仅限研究用途。

它是本地校验工具：**不拉行情、不调模型、不下单、不给投资建议。**

## 为什么叫这个名字

[Holdout](https://github.com/holdout-labs) 工具链的治理层。*holdout set* 是
你直到最后都不碰的数据；*holdout juror* 是那个证据没到齐就不肯随大流的
陪审员。这个包就是那个陪审员：一个清单、一个判定、发布之前先过堂。

## 快速上手

```bash
python -m pip install -e .[test] pytest
python examples/demo.py
```

校验清单：

```bash
gov validate --manifest examples/ai-research-manifest.json
gov report --manifest examples/ai-research-manifest.json
```

## 契约（v0.2，已冻结）

契约在 `schema/`，由测试锁定：

- [`schema/artifact.schema.json`](schema/artifact.schema.json) — `holdout.artifact.v0.2`
- [`schema/policy.schema.json`](schema/policy.schema.json) + [`schema/policy.example.yml`](schema/policy.example.yml) — `holdout.policy.v0.1`
- [`examples/artifact.example.json`](examples/artifact.example.json) — 一份合规的 `research_conclusion` 示例
- [`docs/migration-v1-to-v0.2.md`](docs/migration-v1-to-v0.2.md) — v1 清单的升级路径

## gov check — 场景 1（M1，已完成）

AI 生成的研究结论，发布前必须过数据 + 时序 + 证据门禁：

```bash
# 脚手架一个研究结论项目
gov init --dir research/ --name momentum-oos-review
# 把 gate-inputs.json 指向你的数据（imm / padj / lf / fl 命令），然后：
gov check --manifest research/artifact.json
#   exit 0 = release（可发），1 = review_needed（要人看），2 = block（拦下）
# artifact.json 会写回 decision、missing 和门禁证据；
# 工具原始输出落在 research/reports/ 下（sha256 引用）

gov report --manifest research/artifact.json   # 人可读报告
```

验收套件（`tests/test_m1_scenario1.py`）对**真实** `imm` / `lf` / `padj`
二进制运行 10 个埋了缺陷的样例（幸存者偏差 ×3、未来函数 ×3、复权口径 ×2、
缺证据 ×2）——全部被拦，0 漏放；外加一个干净对照组必须放行。

## gov attach（已完成）

先挂证据、再判定——agent 工作流的关键一步：

```bash
gov attach --manifest research/artifact.json \
  --gate data_integrity --status pass --tool imm --report-ref sha256:...
gov attach --manifest research/artifact.json --attachment sources=docs/sources.md
gov attach --manifest research/artifact.json --declaration contains_returns=true
gov attach --manifest research/artifact.json --review approved --reviewer research-owner
```

挂证据会**把 `decision` 重置为 `pending`**——判定只对生成它的证据有效，
证据一变，判定作废，必须重新 `gov check`。同样的操作对 agent 暴露为
`gov_attach` MCP 工具。

## 场景 2 & 3（M2，已完成）

- **strategy_advice（策略建议）** — 必须挂回测证据：`backtest_report` 和
  `robustness_report` 附件，外加 `statistical_quality` 门禁（真实 `qc`
  运行）。没声明 `n_trials` 的回测是"拒绝判定"而不是"失败"：`qc` 拒审 →
  `review_needed`；真正的过拟合（DSR/PBO/haircut/MinTRL）→ `block`。
  验收套件：`tests/test_m2_scenario23.py`。
- **public_copy（公开文案）** — 必须挂 `sources`；当文案声明含收益数字
  （`declarations.contains_returns`）时，`limitations` 变成必挂（条件附件，
  在 `policy.yml` 里表达，不是写死在代码里）。通过的 `gov report` 会打印
  附件，可直接当发布附注用。

契约扩展（已冻结）：`artifact.declarations`（布尔声明）+ policy
`conditional_attachments`（`when` / `require`）。

## 发布集成（M3，已完成）

- **CI** — `.github/workflows/ci.yml`：pytest 矩阵（3.11/3.12）+ fail-closed
  smoke（脚手架 → 无证据时 `gov check` 必须 exit 2）。
- **可复用 Action** — `.github/actions/gov-check`：composite action，任何
  workflow 里一行即可对 artifact 跑 `gov check`。
- **pre-commit hook** — `.pre-commit-hooks.yaml`：对每个 `artifact.json`
  跑 `gov check --manifest`，block 即拒提交。接入方式：

  ```yaml
  # .pre-commit-config.yaml
  repos:
    - repo: https://github.com/holdout-labs/holdout-governance
      rev: v0.4.0
      hooks:
        - id: gov-check
  ```

- **Agent 接口** — 两种方式从代码/agent 调 gov：
  - `gov api --port 8000` — 纯 stdlib HTTP JSON API：`GET /health`、
    `POST /check` / `/report` / `/init`（零额外依赖）。
  - `gov mcp` — MCP stdio 服务（`pip install 'holdout-governance[mcp]'`），
    暴露 `gov_check`、`gov_report`、`gov_init`、`gov_attach` 四个工具，
    Claude / Cursor 等任意 MCP 客户端可用。

## 定位

这个包是现有 Holdout 工具之上的包装层：

| 需求 | 现有工具 |
| --- | --- |
| 数据质量与快照 | `ashare-data-immunity` |
| 时点价格口径 | `pit-adjuster` |
| 时序与未来数据泄漏 | `lookahead-free` |
| 回测质量 | `factor-qc` |
| 结论与证据链 | `falsification-ledger` |
| 历史错误复盘 | `lesson-book` |

这个包记录检查是否通过。它不授权任何执行。

## 开发

```bash
python -m pip install -e .[test] pytest
python -m pytest
```

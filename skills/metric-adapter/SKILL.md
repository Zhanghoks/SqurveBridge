---
name: metric-adapter
description: 为可选 benchmark-specific/外部评估指标生成用户确认的 metric/spec.json；默认不启用、不运行外部指标。
disable-model-invocation: true
---

# Metric Adapter

**前置阅读**：

- `shared-references/reproduce-workspace-contract.md`
- `shared-references/evaluation-system.md`
- `shared-references/adapter-integration-dag.md`

**接收**：`manifest.components.metric` 中的候选指标线索、reader handoff、benchmark 文档或已有离线评估证据  
**产出**：`artifacts/<slug>/metric/spec.json` → 供 `config-adapter` 合成 reproduce config 的 `external_eval`

外部指标是 option，不是默认评估。没有用户确认时，必须保持 disabled。

---

## 适用范围

使用本 skill 的情况：

- benchmark 有官方指标、第三方脚本或项目特定指标，且 Squrve 内置指标不能表达。
- 已有离线指标实现需要被登记为可选外部指标，例如 EHRSQL reliability。
- 用户要求在 reproduce config 中保留可选择的外部评估开关。

不使用本 skill 的情况：

- 常规 EX/EM/SF1/SC/VES/RVES/CF1/FD 等内置 SQL 指标：归 `reproduce/metrics/`。
- stage 级别 reduce/parse/generate/select 诊断指标：归 `task_meta[].eval_type`。
- 运行后的汇总报告：归 `evaluator-report`。

---

## 交互门控

写 `metric/spec-draft.md` → `METRIC_OPTION_REVIEW` → 用户明确选择启用或禁用 → 落盘
`metric/spec.json` → `DELIVERY`。

`METRIC_OPTION_REVIEW` 必须向用户说明：

- 候选 metric id 与适用 benchmark/dataset。
- 该指标需要的输入文件、依赖、后处理或官方脚本。
- 默认选择是 disabled。
- 若启用，config 会写入 `external_eval.enabled: true`，且只在后续 runtime seam 实现后运行。
- 若禁用，仍可写入 `metric/spec.json` 记录选择，但 config 不得启用外部指标。

若无法交互或用户未明确确认，写入 disabled spec：

```json
{
  "enabled": false,
  "confirmed_by_user": false
}
```

---

## Steps

1. 读取 reader 产物与 manifest 中的候选指标线索。
2. 判断候选指标是否属于外部指标，而不是内置 metric 或 stage eval。
3. 为每个候选指标整理 `metric/spec-draft.md`，列出启用/禁用选项。
4. 执行 `METRIC_OPTION_REVIEW`，通过持续用户交互确认 option 指标选择。
5. 从 `templates/adapter/metric-spec.json` 实例化 `artifacts/<slug>/metric/spec.json`。
6. 若启用：设置 `enabled: true`、`confirmed_by_user: true`、`metric_id`、`config_snippet.external_eval`。
7. 若禁用：设置 `enabled: false`，`config_snippet.external_eval.enabled: false`。
8. `verify.py json-load --path artifacts/<slug>/metric/spec.json`。
9. 交给 `config-adapter`。`config-adapter` 只消费 spec，不重新决定 metric 语义。

---

## Spec 字段

| 字段 | 要求 |
|------|------|
| `slug` | 当前接入 slug |
| `target_dataset` | 目标 dataset 或 benchmark |
| `metric_id` | 稳定 id，例如 `ehrsql_reliability` |
| `enabled` | 用户是否选择启用 |
| `confirmed_by_user` | 是否经过明确确认；启用时必须为 `true` |
| `applicability` | 适用范围、限制与不适用情况 |
| `inputs` | 所需 gold/pred/db/schema 等输入 |
| `dependencies` | 外部脚本、包、服务或环境要求 |
| `output_schema` | 预期输出字段；未来写入 `scores.json.external_metrics` |
| `config_snippet` | `config-adapter` 可合并的 `external_eval` 片段 |
| `notes` | 证据、来源、风险 |

---

## 安全规则

- 不得从 manifest metadata 自动启用外部指标。
- 不得因为 benchmark 名称匹配就启用外部指标。
- 不得把外部指标放入 `task_meta[].eval_type`。
- 不得把外部指标结果混入 `scores.json.aggregate`。
- 不得声称外部指标已出分，除非存在对应 run artifact。
- 不改 `Engine`、`Router`、`core/task` 或 Evaluator internals。

---

## 完成证据

```bash
verify.py json-load --path artifacts/<slug>/metric/spec.json
verify.py reproduce-contract --path reproduce/configs/<dataset>/<method>.json
```

完成后在 handoff 中说明：

- metric 是 enabled 还是 disabled。
- 用户确认证据在哪里。
- `config-adapter` 应合并或忽略的 `external_eval` 行为。

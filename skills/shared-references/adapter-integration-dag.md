# Adapter Integration DAG

manifest 中 `integration.dag` 声明 adapter 依赖顺序；与运行时 `exec_process` 独立。

可复制 schema 见 `templates/manifest/integration-dag.schema.json`。

`metric` 不是默认 DAG 阶段。可选外部指标由 `metric-adapter` 通过用户确认生成
`artifacts/<slug>/metric/spec.json`，再由 `config-adapter` 投影到 reproduce config 的
`external_eval`。manifest 可以记录候选指标线索，但不能单独启用外部指标。

## 两字段对比

| 字段 | 阶段 | 示例 |
|------|------|------|
| `pipeline.exec_process` | Squrve 运行时 | `["reduce","parse","generate"]` |
| `integration.dag` | Harness 接入 | `{ "actor": [], "llm_provider": [] }` |

## Schema

```json
{
  "integration": {
    "dag": {
      "llm_provider": [],
      "actor": [],
      "prompt": ["llm_provider"],
      "workflow": ["actor"],
      "adapter": ["llm_provider", "prompt", "workflow"]
    },
    "notes": "顺序理由"
  }
}
```

- `[]` = 无前置，可并行
- `adapter` 通常依赖所有非 null 上游
- `null` stage 不出现在 DAG

## 常见模式

**LLM 优先**：`llm_provider[] → prompt[llm] → actor[llm,prompt] → workflow[actor]`

**Actor 优先**：`actor[] → llm_provider[] → prompt[actor] → workflow[actor,llm]`

**并行起步**：`llm[], embedding[], actor[] → prompt[llm], rag[embed] → workflow[actor,rag]`

**可选指标分支**：`metric-adapter → artifacts/<slug>/metric/spec.json → config-adapter`

- 只有 `metric/spec.json` 中 `enabled: true` 且 `confirmed_by_user: true` 时，config 才能写入
  `external_eval.enabled: true`。
- `integration.dag` 中的候选 metric 元数据只用于提示交互，不是启用源。
- 若未来把 `metric` 提升为一等调度阶段，必须从已确认的 `metric/spec.json` 派生，不能由
  manifest metadata 直接触发。

## 调度

```bash
artifact_state.py adapter-plan --slug <slug>
```

输出 `READY_STAGE`/`READY_SKILL` → 执行 → 重新 plan → 直到 `ADAPTER_READY=true` → config-adapter。

同轮多个无边 `READY_STAGE` 可并行。

## 工具

```bash
artifact_state.py validate-integration-dag --slug <slug>
artifact_state.py adapter-plan --slug <slug>
```

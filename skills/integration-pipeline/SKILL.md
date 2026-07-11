---
name: integration-pipeline
description: 根据 manifest integration.dag 编排细粒度 adapter，完成 method/database 接入，并生成可被 /run 递归评估的 config。candidate-reader 完成后触发。
disable-model-invocation: true
---

# Integration Pipeline

**前置阅读**：`shared-references/README.md` → `integration-contract.md` → `adapter-integration-dag.md` → `user-interaction-contract.md`

**接收**：`artifacts/<slug>/reader/manifest.json` + `state.json`（reader done）  
**产出**：`reproduce/configs/<dataset>/<method>.json` → 交给 `/run`（目标：debug 跑通，并生成 scores.json、workflow trace、SQL feature/QVT 切片、eval-store）
模板：`templates/manifest/integration-dag.schema.json`、`templates/artifacts/state.schema.json`

---

## 交互门控

| 阶段 | 时机 | 内容 |
|------|------|------|
| INTAKE | §0 | 确认从 reader 继续还是重跑 |
| SPEC_REVIEW | §3 每个 READY_SKILL 前 | 该 stage 计划 |
| DELIVERY | §3 config-adapter 前 | 全链路汇总 |

---

## Steps

### 0. INTAKE

slug 已有 manifest → 确认「继续 integration」还是「重跑」。  
从 candidate 路径启动 → 先走 `candidate-reader`。

**Branch / Worktree / Main**（method 时，见 `git-experiment-isolation.md`）：先问用户模式；若选 **Main 模式** 须说明风险并 `set-dev-mode --mode main`。

**分支门控**（读 `manifest.type` 或 `state.type`）：

- **method** 且当前在 `main` → 默认 `check-branch` 失败；用户选 Main 模式并登记后放行。
- **database** → 可在 `main` 继续；`check-branch --type database` 始终通过。

### 1. Reader 校验

```bash
artifact_state.py validate-reader-artifacts --slug <slug>
artifact_state.py validate-integration-dag --slug <slug>
```

### 2. DAG 调度

禁止固定顺序。接入顺序由 `integration.dag` 决定：
- `[]` = 无前置，可并行
- 有边 = 等前置全部 done/inline/null

### 3. 执行循环

```bash
artifact_state.py adapter-plan --slug <slug>
```

循环：

1. `adapter-plan` → 解析 `READY_STAGE`/`READY_SKILL`
2. `INTEGRATION_COMPLETE=true` → §5
3. 每个 `READY_SKILL`：
   - SPEC_REVIEW → 用户 approve → 执行对应 adapter skill
4. `ADAPTER_READY=true` → config-adapter（须先 DELIVERY 汇总）
5. 回到 1

### 4. Stage → Skill

| stage | skill |
|-------|-------|
| `llm_provider` | llm-provider-adapter |
| `embedding` | embedding-adapter |
| `prompt` | prompt-adapter |
| `rag` / `few_shot` | retrieval-adapter |
| `external` | external-knowledge-adapter |
| `actor` | actor-adapter |
| `workflow` | workflow-adapter |
| `adapter` | config-adapter |
| `benchmark_data` | benchmark-data-adapter |
| `sysconfig` | sysconfig-adapter |
| `schema` | schema-adapter |
| `db_backend` | db-backend-adapter |
| `credential` | credential-adapter |

### 可选 metric 分支

`metric-adapter` 是用户确认驱动的可选 artifact 分支，不是默认 `integration.dag`
调度阶段。manifest 可以记录候选外部指标线索；真正启用必须来自
`artifacts/<slug>/metric/spec.json`。

- 默认：不调用 `metric-adapter`，不生成启用的 `external_eval`。
- 用户需要 benchmark-specific/外部指标时：执行 `metric-adapter` 的
  `METRIC_OPTION_REVIEW`，确认 enabled/disabled，再交给 `config-adapter`。
- `config-adapter` 只能从已确认 spec 投影 `external_eval`，不得从 manifest metadata
  自动启用。
- 本阶段不修改 `artifact_state.py` 的 stage set，也不把 `metric` 提升为一等 DAG 调度。

### 5. 收尾

失败 → 立即停止，保留 state。  
成功 → 报告 `state.adapter.reproduce_config`，询问是否 `/run`（进入 debug 跑通 config 阶段）。

**注意**：integration-pipeline 完成 **≠** 合入 main。`/run` 成功后须 **MERGE_REVIEW**（见 `run` skill §6、`git-experiment-isolation.md` §MERGE_REVIEW）。

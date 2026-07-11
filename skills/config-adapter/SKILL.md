---
name: config-adapter
description: 聚合上游 adapter 产物，生成可复现且可评估的 reproduce config；必须配置 stage eval、dataset_save_path 与 workflow trace 所需字段。所有 adapter 完成后触发。
disable-model-invocation: true
---

# Config Adapter

**前置阅读**：`shared-references/reproduce-config-schema.md`

**接收**：各 adapter 产物（model/config.json、spec.json、changes.json 等）  
**产出**：`reproduce/configs/<dataset>/<method>.json` + `adapter/file-changes.json` → 交给 `/run`（debug 跑通该 config，并产出 scores/workflow trace/eval-store）
模板：`templates/reproduce/`、`templates/adapter/file-changes.json`

---

## 交互门控

写 `adapter/reproduce-spec-draft.md`（每个 target dataset 的 config 要点）→ SPEC_REVIEW + DELIVERY → reproduce config。

---

## Steps

```bash
artifact_state.py gate-adapter --slug <slug> --expected-type <method|database>
```

### Method 输入

| 文件 | 用途 |
|------|------|
| `model/config.json` | LLM 配置 |
| `model/embedding-config.json` | embedding |
| `prompt/spec.json` | prompt |
| `rag/*.json` | index/few-shot |
| `external/external-config.json` | external |
| `workflow/changes.json` | Task/Actor 注册 |
| `<layer>/spec.json` → task_meta | 各 layer Task 声明 |
| `metric/spec.json` | 可选外部指标；仅当 `enabled: true` 且 `confirmed_by_user: true` 时合成 `external_eval` |

### Database 输入

| 文件 | 用途 |
|------|------|
| `benchmark/registration.json` | data/schema source |
| `sysconfig/registration.json` | benchmark 注册 |
| `schema/conversion.md` | schema 转换 |
| `metric/spec.json` | 可选外部指标；默认不生成启用配置 |

### 遍历要求

`target_datasets` 为数组——**每个 dataset 独立生成 reproduce config**。

### 可选外部指标

`metric-adapter` 拥有外部指标语义和用户确认；`config-adapter` 只消费已经确认的
`artifacts/<slug>/metric/spec.json`。

- 无 `metric/spec.json`：不写入 `external_eval`，或写入 `{"enabled": false, "adapters": []}`。
- `enabled: false`：保持 default-off，不运行外部指标。
- `enabled: true`：必须同时满足 `confirmed_by_user: true`，并把 spec 中的 `config_snippet`
  合并到 config 的 `external_eval`。
- config 中每个启用 adapter 必须带 `id` 与 `source_artifact`，且 `id` 与
  `metric/spec.json.metric_id` 一致。
- 不得从 manifest metadata、benchmark 名称或 adapter 猜测自动启用外部指标。

### 单阶段

为每个 dataset 生成 `reproduce/configs/<dataset>/<method>.json`。
从 `templates/reproduce/single-stage-config.json` 实例化。

最低评估要求：
- `task_meta[].eval_type` 至少包含 `execute_accuracy`
- `is_save_dataset: true`
- `dataset_save_path` 非空，便于 `scores.json` 与 eval-store 追踪最终输出

### 多阶段

1. 收集各 layer task_meta → `task.task_meta[]`
2. 合成 `cpx_task_meta`（`task_lis` 按数据流顺序）
3. `exec_process` → `"<slug>_full"`
4. 每个 stage 都必须配置 `eval_type`、`is_save_dataset: true`、`dataset_save_path`
5. **不显式配 `pipeline_run_mode`** — 默认逐个 sample 模式。stage eval 不要求 stage-mode；只有用户明确要求按 stage 整批诊断时才配 `"stage"`

从 `templates/reproduce/multi-stage-config.json` 实例化。

> ComplexTask 执行模式详见 `workflow-adapter` 或 `run` §2.2；常规 config 一律保持默认逐个 sample。

推荐 stage eval：

| Task | eval_type |
|------|-----------|
| ReduceTask | `reduce_recall`, `reduce_precision`, `reduce_rate` |
| ParseTask | `parse_recall`, `parse_precision`, `parse_exact_matching` |
| GenerateTask | `execute_accuracy` |
| SelectTask | `execute_accuracy` |

如 dataset 缺 `gold_schemas`，reduce/parse 指标会显示 unavailable；仍应保留 `dataset_save_path` 供 `_actor_trace`、workflow attribution 和错误排查使用。

### 验证

```bash
verify.py json-load --path reproduce/configs/<dataset>/<method>.json
verify.py config-task --path reproduce/configs/<dataset>/<method>.json --expected-task <Class>
```

### `api_key` 与 `.env`

生成的 reproduce config **禁止写入真实 secret**。默认写法：

```json
"api_key": {
  "qwen": "your_api_key_here"
},
"llm": { "use": "qwen" }
```

用户在本机仓库根目录维护 `.env`（见 `.env.example`）；`/run` 与 `reproduce/run.py` 启动时会加载 `.env` 并自动补齐 placeholder。

也可生成显式 env 引用（仍不含 secret 值）：

```json
"api_key": { "qwen": "${ENV:QWEN_API_KEY}" }
```

Provider 映射：`qwen→QWEN_API_KEY`，`deepseek→DEEPSEEK_API_KEY`，`zhipu→ZHIPU_API_KEY`。详见 [reproduce-config-schema.md](../shared-references/reproduce-config-schema.md#api_key-与-env)。

---

### 完成

```bash
artifact_state.py complete-adapter --slug <slug> --adapter-type <type> --target-dataset <ds> --reproduce-config <path>
```

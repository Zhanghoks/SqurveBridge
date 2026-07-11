# Reproduce Config Schema

实验入口：`reproduce/configs/<dataset>/<method>.json`，由 `reproduce/run.py` 加载。

`reproduce/` 是 Squrve 的运行工作区：config 在这里变成可检查、可运行、
可 debug、可评估并可沉淀 artifact 的实验合同。工作区生命周期、README 约定
和验证边界见 [reproduce-workspace-contract.md](reproduce-workspace-contract.md)。

模板：从仓库根目录 `templates/reproduce/` 复制骨架，替换占位符。

- 单阶段：`templates/reproduce/single-stage-config.json`
- 多阶段：`templates/reproduce/multi-stage-config.json`
- Config README：`templates/reproduce/config-readme.md`

## 主要段落

| 段 | 关键字段 |
|----|---------|
| `api_key` | 与 `llm.use` 对应；见下方 **`.env` 补齐** |
| `llm` | `use`, `model_name`, `context_window`, `temperature`, `time_out` |
| `dataset` | `data_source`（`<benchmark>:<sub>:` 或 `<benchmark>:<sub>:<filter>`）, `need_few_shot`, `need_external` |
| `database` | `schema_source`, `need_build_index` |
| `task.task_meta[]` | `task_id`, `task_type`, `dataset_save_path`, `is_save_dataset`, `eval_type`, `meta.task.*_type` |
| 顶层 | `generate_num`, `engine.exec_process` |

## `api_key` 与 `.env`

实验 config 中的 `api_key` 可与仓库根 `.env` 配合，避免把 secret 提交进 git。

**加载时机**：`python reproduce/run.py ...` 与 `prepare-run` 启动时，读取 `<repo>/.env`（不覆盖 shell 已有 env）。

**config 写法（二选一）**：

```json
"api_key": { "qwen": "your_api_key_here" }
```

```json
"api_key": { "qwen": "${ENV:QWEN_API_KEY}" }
```

当值为 placeholder / 空 / `${ENV:...}` 且 env 有值时，自动解析为可用 key。

| `llm.use` | `.env` 变量 |
|-----------|-------------|
| `qwen` | `QWEN_API_KEY` |
| `deepseek` | `DEEPSEEK_API_KEY` |
| `zhipu` | `ZHIPU_API_KEY` |
| `openai` | `OPENAI_API_KEY` |
| `claude` | `ANTHROPIC_API_KEY` |

环境变量模板文件：`.env.example` → 复制为 `.env`（已在 `.gitignore`）。

`reproduce/configs/` 目录本身 gitignore；本地 config + `.env` 即可跑通。

---

```json
{
  "task_meta": [{ "task_id": "generate", "task_type": "GenerateTask",
    "meta": { "task": { "generate_type": "<Class>" } } }],
  "exec_process": ["generate"]
}
```

单阶段最低要求：`eval_type: ["execute_accuracy"]`、`is_save_dataset: true`、`dataset_save_path` 非空。

## 多阶段

每 stage 一条 `task_meta`（`task_id`: `<slug>_<layer>`），加一条 `cpx_task_meta`：

```json
{
  "cpx_task_meta": [{
    "task_id": "<slug>_full",
    "task_lis": ["<slug>_reduce", "<slug>_parse", "generate"],
    "eval_type": ["execute_accuracy"]
  }],
  "exec_process": ["<slug>_full"]
}
```

多阶段最低要求：每个 stage 都要保存 dataset snapshot，供 stage eval、workflow trace 与 eval-store 使用。

| Task | 推荐 eval_type |
|------|----------------|
| ReduceTask | `reduce_recall`, `reduce_precision`, `reduce_rate` |
| ParseTask | `parse_recall`, `parse_precision`, `parse_exact_matching` |
| GenerateTask | `execute_accuracy` |
| SelectTask | `execute_accuracy` |

`reproduce/run.py` 会将最终评估写入：
- `artifacts/<run_id>/scores.json`
- `artifacts/<run_id>/detailed-report.txt`
- `artifacts/<run_id>/weakness_profile.md`
- `artifacts/eval-store.sqlite`

`scores.json` 包含 final metrics、stage metrics、`workflow_trace`、`per_sample[].workflow`、`sql_features`、`by_sql_feature`、`by_scenario`、`qvt`、token/latency 与错误归因。
输出骨架见 `templates/evaluation/scores.schema.json`、
`templates/evaluation/workflow-trace.schema.json`、
`templates/evaluation/stage-metrics.schema.json`。

## Checklist

1. 复制 template → `reproduce/configs/<dataset>/<method>.json`
2. 替换 benchmark/Actor 占位符
3. 多 stage：各 layer task_meta + cpx_task_meta + 每 stage `dataset_save_path`
4. 生成/刷新 config README：
   `python tools/reproduce_contract.py generate-readmes --path reproduce/configs/<dataset>/<method>.json`
5. 静态合同校验：
   `python tools/verify.py reproduce-contract --path reproduce/configs/<dataset>/<method>.json`

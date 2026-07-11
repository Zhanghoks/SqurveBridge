# Artifact Pipeline

Harness 产物与状态合同。运行时架构见 [squrve-framework.md](squrve-framework.md)。

可复制/可校验的文件骨架放在仓库根目录 `templates/`：
`templates/reader/`、`templates/manifest/`、`templates/artifacts/`、
`templates/adapter/`。

## 目录 `artifacts/<slug>/`

| 路径 | 说明 |
|------|------|
| `state.json` | 各 stage 状态（pending/done/inline/null） |
| `history.jsonl` | 追加式事件日志 |
| `reader/` | profile、manifest、handoff、exploration |
| `model/`…`external/` | 各 adapter 产物 |
| `generator/`…`agent/` | Actor layer spec.json |
| `workflow/`…`credential/` | 编排/数据库 adapter |
| `adapter/` | 聚合 file-changes.json、reproduce config 引用 |
| `runs/` | **不可删**的编号 run 记录 |

## Reader Exploration（双 subagent 硬门控）

写 manifest **前**必须并行完成：

| 文件 | 产出方 | 扫描范围 |
|------|--------|----------|
| `squrve-inventory.md` + `squrve-coverage.json` | Squrve 探索 subagent | **整个 Squrve 仓库根** |
| `candidate-inventory.md` + `candidate-coverage.json` | Candidate 探索 subagent | `<candidate_path>` |
| `mapping-matrix.md` | 主 agent 合成 | — |

Squrve subagent 须覆盖 `core/`、`skills/`、`tools/`、`templates/`、`harness/`、`benchmarks/` 结构等，不得仅扫 `core/`。
递归规则：[reader-recursion-contract.md](reader-recursion-contract.md)

## Manifest 合同

`components` **必须是分组对象**。实例骨架见：

- Method: `templates/reader/method-manifest.json`
- Database: `templates/reader/database-manifest.json`
- Component schemas: `templates/manifest/method-components.schema.json` and `templates/manifest/database-components.schema.json`

### Method

```json
{
  "llm": [], "embedding": [], "prompt": [], "rag": [], "few_shot": [],
  "external": [],
  "actor": {
    "generator": [], "parser": [], "reducer": [], "scaler": [],
    "decomposer": [], "optimizer": [], "selector": [], "agent": []
  },
  "config": []
}
```

附加：`pipeline.exec_process`（运行时 Task 链）、`integration.dag`（接入 adapter 依赖）。

### Database

```json
{
  "dataset": [], "schema": [], "database_files": [], "benchmark_meta": [],
  "embedding": [], "rag": [], "few_shot": [], "external": [],
  "db_backend": [], "credential": []
}
```

每条含 `source_files`、`needs_*`。空数组 = 不存在。

## State / Gate API

```bash
artifact_state.py gate <stage> <slug>
artifact_state.py done <stage> <slug> [--status done|inline] [--layer <layer>] [--class-name <Class>]
artifact_state.py gate-adapter --slug <slug> --expected-type method|database
artifact_state.py complete-adapter --slug <slug> --adapter-type <type> --target-dataset <ds> --reproduce-config <path>
```

`state.<stage> === null` → 跳过。`/run` 要求 `state.adapter.status == done`。

## file-changes.json

`config-adapter` 写入：`adapter_type`, `slug`, `target_dataset`, `reproduce_config`, `changes[]`, `verification`。
实例骨架见 `templates/adapter/file-changes.json`，schema 见
`templates/artifacts/file-changes.schema.json`。

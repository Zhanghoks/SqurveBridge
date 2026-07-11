# Shared References — Squrve 接入 Harness

Skills 之间的**稳定合同**。不维护当前仓库已有 benchmark/方法的静态清单——运行时从
`config/sys_config.json`、`reproduce/*.json` 与 exploration 归纳。

中间产物的可复制骨架不放在这里，统一放在仓库根目录
[`templates/`](../../templates/README.md)。本目录只保留“何时做、谁负责、哪些
边界不可越过”的协议。

## 核心原则

1. **原生重构**：接入 = 用 Squrve API 重新实现候选算法，不是复制源码
2. **Spec → 确认 → 交付 → Merge 确认**：写最终产物前须用户 approve；feature branch 上 `/run` 后须 **MERGE_REVIEW** 再合入 `main`
3. **最小侵入**：默认不改 Engine/Router/Evaluator
4. **分支隔离**：method 禁止在 `main` 改 Actor；**Branch + Worktree 混合**（见 [git-experiment-isolation.md](git-experiment-isolation.md)）；database 可在 `main` 接入

详见 [squrve-framework.md](squrve-framework.md) §原生重构、§分支隔离 与 [user-interaction-contract.md](user-interaction-contract.md)。

## 阅读顺序

```
任何 skill 启动 → squrve-framework.md → user-interaction-contract.md → git-experiment-isolation.md（method / Git 时）
    │
    ├─ Reader 阶段 → artifact-pipeline.md → reader-recursion-contract.md（模板见 templates/reader）
    ├─ Integration → integration-contract.md → adapter-integration-dag.md（模板见 templates/manifest）
    ├─ Method      → actor-registration-chain.md
    ├─ Database    → benchmark-registration.md（模板见 templates/benchmark）
    └─ Run/Eval    → reproduce-workspace-contract.md → reproduce-config-schema.md（模板见 templates/reproduce + templates/evaluation）
       Optional metrics → metric-adapter → artifacts/<slug>/metric/spec.json（模板见 templates/adapter/metric-spec.json）
```

Public overviews:

- [`docs/harness-state-machine.md`](../../docs/harness-state-machine.md) explains the integration state machine without requiring readers to inspect `tools/artifact_state.py`.
- [`docs/meta-evo-loop.md`](../../docs/meta-evo-loop.md) explains the lightweight Meta-Evo loop and artifact ownership.

## 文档索引

| 文件 | 职责 |
|------|------|
| [squrve-framework.md](squrve-framework.md) | Squrve 架构、Actor 层、扩展点、**原生重构原则**、禁止修改区 |
| [user-interaction-contract.md](user-interaction-contract.md) | 四阶段门控（INTAKE → SPEC_REVIEW → DELIVERY → **MERGE_REVIEW**） |
| [artifact-pipeline.md](artifact-pipeline.md) | `artifacts/<slug>/` 产物流转、manifest/state 职责、state API；文件骨架见 `templates/` |
| [integration-contract.md](integration-contract.md) | adapter 职责、skip 规则、所有权 |
| [adapter-integration-dag.md](adapter-integration-dag.md) | `integration.dag` 设计与调度；schema 见 `templates/manifest/integration-dag.schema.json` |
| [reader-recursion-contract.md](reader-recursion-contract.md) | 递归覆盖、I/O→layer、anti-monolith |
| [actor-registration-chain.md](actor-registration-chain.md) | Actor 5 步注册链 |
| [benchmark-registration.md](benchmark-registration.md) | benchmark 注册流程；条目和目录骨架见 `templates/benchmark/` |
| [reproduce-workspace-contract.md](reproduce-workspace-contract.md) | `reproduce/` 作为平台工作区的生命周期、README 约定与验证边界 |
| [reproduce-config-schema.md](reproduce-config-schema.md) | reproduce config 字段与多阶段 Task；实例骨架见 `templates/reproduce/` |
| [git-experiment-isolation.md](git-experiment-isolation.md) | Branch + Worktree 混合模式、Agent Git 合同 |
| [evolution-controller-contract.md](evolution-controller-contract.md) | Meta-Evo / MCTS / human review 的分层边界 |
| [evolution-node-schema.md](evolution-node-schema.md) | node 语义合同；文件骨架见 `templates/evolution/node.json` |
| [evolution-journal-schema.md](evolution-journal-schema.md) | journal 事实源、best node、stagnation 语义；文件骨架见 `templates/evolution/journal.json` |
| [bounded-search-policy.md](bounded-search-policy.md) | smoke(50) → bounded(200) → full(best only) 晋级规则 |
| [fitness-contract.md](fitness-contract.md) | 多维 fitness 输入、惩罚项和确定性边界 |
| [evolution-artifact-contract.md](evolution-artifact-contract.md) | `artifacts/evolve/` 必备产物流；目录骨架见 `templates/evolution/artifact-layout.md` |
| [orchestrator-boundary.md](orchestrator-boundary.md) | `.agents/` wrapper 与真实 MCTS orchestrator 边界 |

## 两条流水线

| | 接入流水线（harness） | 运行时流水线（Squrve） |
|--|---------------------|---------------------|
| **入口** | `/candidate-reader` | `reproduce/run.py` |
| **编排** | `integration.dag` → adapter stages | `engine.exec_process` → Task 链 |
| **产物** | `artifacts/<slug>/` + reproduce config | `files/pred_sql/` + `scores.json` + `eval-store.sqlite` |

## Skill ↔ 产物流转

```
candidate-reader ──manifest.json──→ integration-pipeline
                   handoff.md          │
                                       ├→ actor-adapter ──spec.json──→ workflow-adapter
                                       ├→ llm/embedding/prompt/rag/external adapters
                                       ├→ metric-adapter ──metric/spec.json──→ config-adapter（可选外部指标，默认不启用）
                                       └→ config-adapter ──reproduce/*.json──→ /run（debug 跑通 config，产出 scores/workflow trace/eval-store）──→ evaluator-report
```

## 工具

| 工具 | 职责 |
|------|------|
| `artifact_state.py` | gate/done、manifest 校验、DAG 调度、run 记录、**method 分支门控** |
| `verify.py` | Actor import、config 加载、benchmark 注册、reproduce workspace contract 等 smoke check |

`artifact_state.py check-branch --slug <slug> --type method|database`：method 在 `main` 上硬失败；database 允许 main。

---
name: meta-evo
description: SqurveBridge evolution-controller 正式入口；从 reproduce scores 诊断弱点，调用 reproduce/metrics 下的 MCTS/evolution engine 搜索 Actor/config 改进，并把全过程写入 artifacts/evolve。
disable-model-invocation: true
---

# Meta-Evo

Meta-Evo 是 SqurveBridge 自进化 harness 的正式入口。它不是新根目录系统，也不是第二套 runner；它顺着现有结构组织：

- `skills/`、`tools/`、`templates/`（SSOT）：`SKILL.md` frontmatter 注册命令入口，正文描述流程；`tools/` 放确定性工具；`templates/` 放可复制产物骨架。
- `.claude/` 与 `.agents/`：symlink 镜像，共享同一套 SSOT 源文件。
- `reproduce/metrics/`：真实 evolution engine。MCTS、fitness、journal、rollout、delta 等确定性逻辑都放在这里。
- `artifacts/evolve/`：事实源。每次 evolution run 的 baseline、weakness、candidate nodes、journal、memory、best node 和 comparison report 都落盘。

一句话：**Meta-Evo 是入口，MCTS orchestrator 是引擎，evolution_pkg 是工具层，artifacts/evolve 是事实源，.agents 是镜像。**

---

## 接收

- 已完成的 reproduce run slug 或 artifact 路径。
- baseline `scores.json`。不得用 stdout、聊天记录或旧 `runs/eval-result` 替代。
- 用户确认本次针对 method 自进化；不用于 database 接入。

---

## 产出

每次运行写入：

```text
artifacts/evolve/<evolve_slug>/
  evolve-state.json
  baseline-summary.md
  meta-evo-input.json
  weakness_profile.md
  weakness-profile.json
  weakness-analysis.md
  journal.json
  experience.md
  best-node.md
  comparison-report.md
  nodes/
    <node_id>/
      node.json
      change-plan.md
      patch.diff
      run-command.sh
      scores.smoke50.json
      scores.bounded200.json
      evaluator-report.md
      delta.json
      status.json
```

`evolve-state.json` 是当前 phase / resume / human gate 控制状态；`journal.json` 是 node/search 证据账本，记录 node、父子关系、分数、fitness、晋级状态和推荐结论。`process-events.jsonl` 与 `artifact-manifest.json` 记录过程事件、产物指纹和上下游 lineage。

---

## 运行逻辑

1. **BASELINE**：定位 baseline artifact，读取 `scores.json`、`detailed-report.txt`、token/latency、workflow/stage attribution。
2. **WEAKNESS**：调用 `tools/profile_weakness.py` 生成 weakness profile，识别 schema linking、join-heavy、SQL repair、cost 等短板。
3. **INITIALIZE**：创建 `artifacts/evolve/<evolve_slug>/`，写 baseline summary 和初始 journal。
4. **CANDIDATE GENERATION**：由 Meta-Evo 生成候选改进节点；每个 node 必须说明目标弱点、允许修改范围、change plan、patch、运行命令。
5. **SMOKE GATE**：每个候选先跑 bounded smoke（默认 50 samples）。目的不是最终排名，而是筛掉跑不通、严重退化、成本爆炸的候选。
6. **BOUNDED EVAL**：通过 smoke gate 的 top candidate 再跑更大切片（默认 200 samples），比较 EX、EM、VES/CF1/FD、HardSliceScore、cost、latency。
7. **MCTS LOOP**：真实搜索循环由 `reproduce/metrics/mcts/orchestrator.py` 执行；run-level phase 和 resume 由 `reproduce/metrics/evolution_pkg/state_machine.py` 控制。`skills/Meta-Evo/SKILL.md` 只负责入口编排和人工 review，不维护第二套搜索逻辑。
8. **FULL CONFIRMATION**：只对 best node 做 full reproduce confirmation。
9. **USER REVIEW**：展示 best node、patch、delta、改善/退化样本；用户选择 accept / continue / rollback。

---

## 后端边界

Meta-Evo 可以编排和审查，但确定性逻辑不得写在 skill 中：

- MCTS 主循环：`reproduce/metrics/mcts/orchestrator.py`（`run_search()` 单阶段搜索，`run_bounded_funnel()` 串联 smoke → bounded → optional full）
- fitness：`reproduce/metrics/evolution_pkg/fitness.py`
- node / journal：`reproduce/metrics/evolution_pkg/node.py`、`journal.py`
- artifact IO：`reproduce/metrics/evolution_pkg/artifacts.py`
- budget / sampling / experience：`budget.py`、`sampling.py`、`experience.py`

如果这些模块尚不存在，本 skill 只能生成设计和待办，不能在聊天中假装已经完成 rollout。

不得在 `tools/` 或 skill 文档中复制 MCTS selection / rollout / scoring / journal mutation 逻辑，避免双 orchestrator 维护失控。

稳定契约放在 `shared-references/`：

- `evolution-controller-contract.md`
- `evolution-node-schema.md`
- `evolution-journal-schema.md`
- `bounded-search-policy.md`
- `fitness-contract.md`
- `evolution-artifact-contract.md`
- `orchestrator-boundary.md`

可复制产物骨架放在 `templates/evolution/`：

- `node.json`
- `journal.json`
- `evolve-state.json`
- `status.json`
- `artifact-layout.md`

---

## 候选节点要求

每个 candidate node 必须是完整对象：

- baseline 来源
- target weakness
- allowed scope
- change plan
- patch 路径
- run command
- smoke result
- bounded evaluation result
- delta / fitness
- status：`planned` / `running` / `pass` / `buggy` / `reverted` / `recommended`

默认 Scope B：Actor、prompt、config、Task method 分支。Scope C（Engine / Router / Evaluator / DataLoader / Actor 基类）必须单独确认。

---

## 禁止事项

- 不新建根目录级 harness 系统。
- 不在 `tools/` 里实现真实 evolution engine。
- 不复制 MLEvolve 的 Kaggle codegen 逻辑；只吸收 search / journal / fitness / memory / fusion 结构。
- 不让所有候选都跑 full；full confirmation 只给 best node。
- 不把未落盘的聊天内容当作 evolution 事实源。

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

自进化的节奏是 **review → 提意见 → 修改 → 再 review，直到足够优秀**：所有关键产物（weakness profile、候选 change plan/patch、对比报告）在消耗评估预算或人工注意力之前，都必须通过 `skills/evolve-review/SKILL.md` 的 AI 迭代审核循环（契约见 `shared-references/evolution-review-loop.md`）。

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
  reviews/
    <target>/
      review-state.json
      round-<n>-findings.json
  nodes/
    <node_id>/
      node.json
      change-plan.md
      patch.diff
      run-command.sh
      review/
        review-state.json
        round-<n>-findings.json
      scores.smoke50.json
      scores.bounded200.json
      evaluator-report.md
      delta.json
      status.json
```

`evolve-state.json` 是当前 phase / resume / human gate 控制状态；`journal.json` 是 node/search 证据账本，记录 node、父子关系、分数、fitness、晋级状态和推荐结论。`process-events.jsonl` 与 `artifact-manifest.json` 记录过程事件、产物指纹和上下游 lineage。

---

## 运行逻辑

每步给出：命令 → 产出 → 通过判据。任何一步中断后，用 `python3 tools/evolve_status.py --evolve-dir <dir>` 取回唯一下一步。

1. **BASELINE**：定位 baseline artifact，读取 `scores.json`、`detailed-report.txt`、token/latency、workflow/stage attribution。
   产出 `baseline-summary.md`；判据：所有引用数字可回溯到 scores 字段。
2. **WEAKNESS**：`python3 tools/profile_weakness.py --scores <baseline>/scores.json --out <dir>/weakness_profile.md`。
   产出 weakness profile（schema linking、join-heavy、SQL repair、cost 等短板）。
3. **PROFILE REVIEW（循环）**：`/evolve-review`（target_kind=`weakness-profile`，账本在 `<dir>/reviews/weakness-profile/`）。
   判据：verdict=approve；否则按 findings 修 profile 再审。
4. **INITIALIZE**：创建 `artifacts/evolve/<evolve_slug>/`，写 baseline summary、初始 journal 与 `evolve-state.json`（模板见 `templates/evolution/`）。
5. **CANDIDATE GENERATION**：生成候选节点，每个 node 落盘 `node.json`、`change-plan.md`、`patch.diff`、`run-command.sh`，并汇入 `action-pool.json`；必须声明目标弱点、target_metric、允许 scope。
6. **CANDIDATE REVIEW（循环，硬门控）**：每个 node 跑 `/evolve-review`（target_kind=`change-plan`/`patch`，账本在 `nodes/<id>/review/`）。
   判据：`tools/evolve_status.py` 的 `candidate_gate_blockers` 为空 → 记录 phase `candidates_reviewed`；否则继续修改或将 escalate 的 node 交用户。评估预算不得花在没审过的候选上。
7. **SMOKE GATE**：跑 `evolve_status` 给出的 orchestrator 命令（`--stage smoke`，默认 50 samples）。目的不是最终排名，而是筛掉跑不通、严重退化、成本爆炸的候选。
8. **BOUNDED EVAL**：`--stage bounded`（默认 200 samples），比较 EX、EM、VES/CF1/FD、HardSliceScore、cost、latency。
9. **MCTS LOOP**：搜索循环由 `reproduce/evolve/mcts/orchestrator.py` 执行；run-level phase 和 resume 由 `reproduce/evolve/state_machine.py` 控制。本 skill 只编排，不维护第二套搜索逻辑。
10. **FULL CONFIRMATION**：`--stage full`，只对 best node 做 full reproduce confirmation。
11. **REPORT REVIEW（循环）**：comparison report 过 `/evolve-review`（target_kind=`comparison-report`，账本在 `reviews/comparison-report/`）。
    判据：verdict=approve → 记录 phase `report_reviewed`；核对每个分数可回溯、改善/退化成对呈现。
12. **USER REVIEW**：展示 best node、patch、delta、改善/退化样本；用户选择 accept / continue / rollback；escalate 的 findings 一并呈上。结果经 `artifacts.record_user_review` 写入经验记忆。

---

## AI 执行协议

本 skill 面向 Agent 执行，遵守以下协议以保证任意时刻可中断、可恢复、可审计：

1. **状态驱动，不靠记忆**：每次进入（含恢复会话）先执行
   `python3 tools/evolve_status.py --evolve-dir artifacts/evolve/<slug>`，
   按返回的 `next_command` 执行唯一下一步；不得凭聊天上下文猜进度。
   review 门未清（`candidate_gate_blockers` 非空或有 escalate）时，status 会扣住搜索阶段。
2. **一步一落盘**：每个阶段结束时必须存在对应机器可读产物（journal、review-state、scores、delta），
   并通过 process-events / manifest 记账。没有落盘的步骤等于没发生。
3. **单一下一步输出**：向用户汇报时，结尾给出"当前 phase + 下一条可直接执行的命令"，
   不给多选项菜单（人工 gate 除外）。
4. **失败闭合**：`evolve-state.json`、`journal.json`、manifest 三方不一致时 fail closed，
   报告不一致点，不得推断修补。
5. **循环有界**：evolve-review 循环受 `max_rounds` 约束，MCTS 受 `dry_round_limit` 约束；
   任何"再试一次"都必须消耗账本里的预算，预算尽则 escalate。

---

## 后端边界

Meta-Evo 可以编排和审查，但确定性逻辑不得写在 skill 中：

- MCTS 主循环：`reproduce/evolve/mcts/orchestrator.py`（`run_search()` 单阶段搜索，`run_bounded_funnel()` 串联 smoke → bounded → optional full）
- fitness：`reproduce/evolve/fitness.py`
- node / journal：`reproduce/evolve/node.py`、`journal.py`
- artifact IO：`reproduce/evolve/artifacts.py`
- budget / sampling / experience：`budget.py`、`sampling.py`、`experience.py`

如果这些模块尚不存在，本 skill 只能生成设计和待办，不能在聊天中假装已经完成 rollout。

不得在 `tools/` 或 skill 文档中复制 MCTS selection / rollout / scoring / journal mutation 逻辑，避免双 orchestrator 维护失控。

稳定契约放在 `shared-references/`：

- `evolution-controller-contract.md`
- `evolution-review-loop.md`
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
- `review-state.json`
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
- review verdict（`review/review-state.json`，approve 才可消耗评估预算）
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
- 不跳过 evolve-review 门控直接花评估预算；不把"聊天里说审过了"当作审核记录。

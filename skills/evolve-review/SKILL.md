---
name: evolve-review
description: Meta-Evo 内嵌的 AI 迭代审核循环：对候选 change plan / patch / 报告做批判性 review，落盘结构化 findings，作者修改后再 review，直到 verdict=approve 或升级人工。评估预算只花在通过审核的候选上。
internal_only: true
parent_skill: meta-evo
disable-model-invocation: true
---

# Evolve Review — AI 迭代审核循环

自进化的核心不是"生成一次候选就去跑分"，而是 **review → 提意见 → 修改 → 再 review，直到足够优秀**。本 skill 定义这个循环的执行协议。确定性账本在 `reproduce/evolve/review.py`，CLI 是 `tools/evolve_review.py`；本文件只描述角色、rubric 和循环节奏，不复制 verdict 逻辑。

一句话：**作者写，审稿人挑刺，账本记账，verdict 决定循环是否结束；人只在 escalate 和最终 accept 时介入。**

---

## 接收

- 一个 review 目标（`target_kind` + 文件路径）：
  - `change-plan` / `patch`：候选节点的改动方案与补丁（花评估预算前必审）
  - `weakness-profile`：弱点画像（进入候选生成前审）
  - `comparison-report` / `evaluator-report`：交人工前审
  - `skill-doc`：harness 自身的 skill / 契约文档改进
- 所在 evolution run 目录（用于 process-events 记账），或独立目录。

## 产出

```text
<target 同级>/review/
  review-state.json      # 账本：rounds、findings、verdict（唯一事实源）
  round-<n>-findings.json # 每轮审稿人原始输出（record-round 的输入）
  round-<n>-notes.md      # 可选：审稿叙述，人类可读
```

---

## 角色分离（必须遵守）

1. **作者 pass**：生成或修改目标产物的一方。
2. **审稿 pass**：以全新批判视角审目标。审稿 pass 必须满足其一：
   - 由独立子代理执行（推荐；prompt 中只给目标产物 + rubric + baseline 证据，不给作者的自辩）；
   - 或由同一 agent 在**读完 rubric 后重新从磁盘读取目标文件**执行，且禁止在同一条消息里"边写边评"。
3. 审稿 pass 不得因为"是自己写的"而跳过任何 rubric 条目；零 findings 的轮次必须逐条说明 rubric 检查了什么、证据是什么（写入 `round-<n>-notes.md`）。

## Rubric（按 target_kind）

**change-plan / patch**
- 是否明确指向 weakness profile 里的一个短板（target_metric 可度量）？
- 改动范围是否在申报 scope 内？是否偷偷触碰 Scope C 路径（`state_machine.is_scope_c_path`）？
- patch 是否能干净 apply？run command 是否可直接执行？
- 是否可能引入回归（hard slice、cost、latency）？有没有便宜的反证方法？
- 是否与已有 journal 里失败过的 action 实质相同（查 experience/journal）？

**weakness-profile**
- 结论是否全部可回溯到 `scores.json` 字段？有没有从聊天记忆里编造的数字？
- top 短板是否有样本量支撑（n 太小的 slice 不得列为主短板）？

**comparison-report / evaluator-report**
- 每个分数是否来自落盘 artifact（scores.json / delta.json）？
- 改善/退化样本是否成对列出？有没有只报喜不报忧？
- 结论是否与 journal best node 一致？

**skill-doc**
- 是否违反层边界（skill 里写确定性逻辑、tools 里写搜索逻辑）？
- 步骤对 AI 是否可执行：每步有输入、命令、产出文件、下一步判据？
- 与 shared-references 契约是否冲突？

## 循环协议

```text
1. open      python3 tools/evolve_review.py open --state <dir>/review/review-state.json \
                 --target-kind <kind> --target-ref <path> [--evolve-dir <run_dir>]
2. review    审稿 pass 按 rubric 产出 round-<n>-findings.json（见下方 schema）
3. record    python3 tools/evolve_review.py record-round --state ... \
                 --reviewer <agent:critic|subagent:...> --findings round-<n>-findings.json
4. branch    读 stdout JSON 的 verdict：
             - revise   → 作者逐条修复 findings → 每条 resolve --resolution "<具体修复>"
                          → 回到步骤 2 重新 review（必须有一轮零新增 blocker/major 才能 approve）
             - approve  → 循环结束；目标产物获得进入下一阶段的资格
             - escalate → 停止循环，把 open findings + escalation_reason 呈给用户裁决
5. gate      回到 Meta-Evo：候选门全部 approve 后
             `python3 tools/evolve_status.py --evolve-dir <run_dir> --record-phase candidates_reviewed`
             （门未清会拒绝）；报告门 approve 后同法记录 `report_reviewed`
```

findings 文件 schema（每条）：

```json
{"severity": "blocker|major|minor|nit", "category": "correctness|scope|evidence|regression-risk|cost|clarity",
 "location": "<文件:行 或 章节>", "summary": "<问题>", "recommendation": "<具体修改建议>"}
```

## 严重度约定

- **blocker**：不修复不得进入下一阶段（apply 不上的 patch、伪造的分数、越界 Scope C）。
- **major**：大概率导致评估浪费或错误结论（target metric 不可度量、与已知失败 action 重复）。
- **minor / nit**：不阻塞 approve，但必须留在账本里；作者可修可不修。
- blocker/major 的 waive 必须 `--human-approved`（用户明确说了才允许）；minor/nit 可由作者 waive 但必须给理由。

## 禁止事项

- 不得在未 record-round 的情况下宣称"已审核通过"；聊天内容不是审核事实源。
- 不得为凑 approve 把 blocker 降级为 minor；严重度以 rubric 为准。
- 不得无限循环：verdict=escalate 后必须停下来找用户。
- 不得在本 skill 或 tools 里复制 verdict 判定逻辑；唯一实现在 `reproduce/evolve/review.py`。

# User Interaction Contract

写最终产物前**必须**用户确认。

## 三阶段门控 + Merge 门控

| 阶段 | 时机 | 用户问题 |
|------|------|----------|
| **INTAKE** | skill 启动后 | 目标与边界理解正确？ |
| **SPEC_REVIEW** | 分析完、写产物前 | 方案可行？要改什么？ |
| **DELIVERY** | validate 通过后 | 锁定交付并推进 state？ |
| **MERGE_REVIEW** | `/run` 成功且用户在 feature branch（非 Main 模式） | **是否将本分支合入 `main`？** |

接入 pipeline 的 INTAKE → SPEC_REVIEW → DELIVERY **不包含** merge；merge 是实验结束后的**独立第四门控**，见 [git-experiment-isolation.md](git-experiment-isolation.md) §MERGE_REVIEW。

## 迭代流程

```
分析 → spec-draft → 呈现 → 用户 approve?
  ├─ approve → 写最终产物 → validate → DELIVERY → done
  ├─ revise  → 改 draft → 再呈现
  └─ reject  → 停止，记录原因
```

## 呈现格式

```markdown
## 方案摘要 — <skill> / <slug>

**类型**：method | database
**目标**：一句话
**关键决策**（3–7 条）
**风险与 open questions**
**下一步**：approve 后执行什么

请确认：**[A] 批准** | **[R] 修订** | **[X] 暂停**
```

## 跳过条件

用户已在本轮明确等价指令（如「按方案直接做」），可跳过，在 `interview-log.md` 记录 `skipped: true`。

## 访谈记录

`artifacts/<slug>/interview-log.md`（append-only），每轮：

```markdown
## Round N — INTAKE|SPEC_REVIEW|DELIVERY
**呈现**：摘要
**用户**：approve|revise|reject
**动作**：执行/跳过的步骤
```

## Draft 路径

| Skill | Draft | 锁定后写入 |
|-------|-------|-----------|
| candidate-reader | `reader/spec-draft.md` | manifest.json + handoff.md |
| actor-adapter | `<layer>/spec-draft.md` | spec.json + Actor .py |
| config-adapter | `adapter/reproduce-spec-draft.md` | reproduce/*.json |
| run | `artifacts/<run_id>/run-plan-draft.md` | record-run（只记录 reproduce artifact 指针） |

## 高风险项（须单独确认）

- 修改 Engine / Router / Evaluator
- `standalone_fallback`
- 新增非 sqlite/big_query/snowflake 的 db_type
- 使用用户未提供的 API key
- 跳过 documented verification

## 与工具的关系

- 用户 approve **不替代** `validate-manifest`、`verify.py` 等校验
- `complete-reader`、`done`、`complete-adapter` 仅在 DELIVERY 后执行
- **`git merge` / `git push` 到 `main` 仅在 MERGE_REVIEW 用户明确选择合入后执行**；`record-run` 不等于 merge

---

## MERGE_REVIEW（合入 main 前必做）

**触发**：method 在 feature branch / worktree 上完成 `/run`（config 跑通 + 有评估结果）之后。

**Agent 必须向用户呈现**（不得跳过）：

```markdown
## 合入 main？ — <branch> / <method>

**当前分支**：`feature/...`（不在 main）
**相对 main 的 commit 数**：N
**本次 EX / smoke 结果**：…
**主要改动**：Actor / config / tests（3–5 条）
**风险**：是否改 runtime core、是否影响其他 method

请选择：
**[M] 合入 main** — 我将执行 merge（冲突须逐文件与你确认）
**[K] 保留分支** — 实验留在本 branch，不合入（默认）
**[R] 放弃** — 标记 deprecated，不再在此 branch 继续
```

**禁止**（曾导致主干与 feature 分叉、同一改动双份 commit）：

| ❌ | ✅ |
|----|-----|
| `/run` 成功后直接在 `main` 上重做相同 commit | 用户选 **[M]** 后从 feature branch **merge** |
| 未询问就 `git merge` / `git push origin main` | MERGE_REVIEW approve 后再操作 |
| 假设 feature branch「已经并进 main」 | `git branch --contains <commit> main` 或 `git log main..HEAD` 核实 |
| `record-run` 后直接结束 | REPORT 后进入 **MERGE_REVIEW** |

**Main 模式**：已在 `main` 开发时跳过 merge，但须在 DELIVERY 说明「改动已在 main，须 review 后再 push」。

访谈记录：`artifacts/<slug>/interview-log.md` 追加 `## Round N — MERGE_REVIEW`。

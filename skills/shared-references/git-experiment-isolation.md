# Git 与实验隔离 — Agent 执行合同

> 人类可读完整版见仓库 `CLAUDE.md` §Branch + Worktree 混合开发模式。

**一句话**：一个方向持续调试用 **feature branch**；多个方向并行推进用 **worktree**；新路线、新实验、新 benchmark 须从最新 `main` 新开。

---

## 任务开始前（必做）

```bash
git fetch origin
git branch --show-current
git status -sb
```

| # | 检查 | 不满足则 |
|---|------|----------|
| 1 | method 任务不在 `main`（**除非**用户已选 Main 模式） | 创建 feature branch / worktree，或 `set-dev-mode --mode main` |
| 2 | 已确认 Branch / Worktree / **Main** 模式 | **先问用户** |
| 3 | 若是新方向/新实验 | 从最新 `main` 新建 branch/worktree（Main 模式不替代「新方向须新开」） |

---

## 开发前：询问用户（必须）

```text
本次开发你希望使用哪种模式？

1. Branch 模式 — 单一方向持续调试，不额外建目录
2. Worktree 模式 — 多个方向并行，每方向独立目录
3. Main 模式 — 直接在 main 上开发（须你明确确认；method 默认不推荐）

只集中调试一个方向 → 推荐 Branch。
同时推进多个方向 → 推荐 Worktree。
明确要在 main 上改 → 可选 Main（须先说明风险，见下）。
```

用户确认后：

```bash
# Branch / Worktree：建分支或 worktree（见下节）

# Main 模式（用户明确选择后）
python3 tools/artifact_state.py set-dev-mode --slug <slug> --mode main
python3 tools/artifact_state.py check-branch --slug <slug> --type method --allow-main
```

**Main 模式须告知的风险**：method Actor 直接进入 main，影响共享主干与其他实验；仍须 Spec 确认与 `/run`；**禁止** Agent 未获用户选择 Main 时在 main 上改 method。

---

## 1. 多方向并行 → Worktree

```bash
git checkout main && git pull
git worktree add ../squrve-finsql -b feature/finsql-20260629 main
git worktree add ../squrve-ehrsql -b feature/ehrsql-20260629 main
```

原则：**一个并行方向 = 一个 worktree = 一个 feature branch**。

---

## 2. 单一方向持续调试 → Feature Branch

```bash
git checkout main && git pull
git checkout -b feature/finsql-debug-20260629
```

可在同一 branch 内连续：

```bash
git commit -m "fix: improve FinSQL parser"
git commit -m "fix: align FinSQL generator"
```

**同一方向、可留同一 branch 的工作**：

- 修 bug、调 prompt、补 adapter、改 config、修 evaluator
- 跑同一 benchmark、优化同一方法实现细节

原则：**一个单一调试方向 = 一个 feature branch**（不必每次新建 worktree）。

---

## 3. 必须新建 branch / worktree

- 接入**另一个** method / benchmark / pipeline
- 同一方法**大版本重写**或不同实现路线
- 用户要求重新开始；branch 已混乱
- 新一轮**独立实验**；需**并行比较**
- 旧分支 merge / reject / deprecated

| ❌ | ✅ |
|----|-----|
| 在旧 branch 上堆 unrelated 实验 | `feature/finsql-debug-20260629` 内连续调试 |
| 新路线复用旧 branch | `feature/finsql-rewrite-20260630` 从 main 新建 |
| 多方向共用一个 checkout | `squrve-finsql/` + `squrve-ehrsql/` 各一 worktree |

---

## 4. Main 模式（用户显式选择）

**默认**：method 不在 `main` 开发。

**例外**：用户明确选择 **Main 模式** 后，可在 `main` 上接入/调试 method（如与 harness 联调、快速验证）。须：

1. INTAKE 中用户明确选「Main 模式」
2. Agent 说明风险（共享主干、Actor 污染）
3. 登记：`set-dev-mode --slug <slug> --mode main`
4. 后续 gate 使用已登记的 `allow_main`，或单次 `--allow-main`

Main 模式**不替代**「新方向须新开 branch/worktree」——只是允许**当前**方向在 main 上继续。

---

## 代码改动权限（method）

| 层级 | 路径 | Agent 权限 |
|------|------|------------|
| **Actor** | `core/actor/**`、该 method Task 注册 | Spec 确认后，在 feature branch **可自主**改 |
| **Runtime core** | Engine / Router / Evaluator / DataLoader / `core/task/` 基类 | **须先告知用户并获 approve** |

---

## Merge 冲突

禁止静默 `--strategy=ours/theirs`。暂停 → 列文件 → 展示 diff → 用户选 A/B/融合 → 再继续。

---

## MERGE_REVIEW — 合入 main（实验结束后必做）

> **漏洞修复**：此前 pipeline 在 `/run` + `record-run` 后缺少 merge 门控，易出现 feature branch 未合入、却在 `main` 上重做 commit 的分叉问题。**Agent 不得默认合入或默认不合入。**

### 何时触发

| 场景 | 是否 MERGE_REVIEW |
|------|-------------------|
| method 在 **feature branch / worktree** 完成 `/run` | **必须** |
| method 在 **Main 模式**（已在 main） | 跳过 merge；DELIVERY 提醒 push 前 review |
| 仅 harness / 平台层在 main 开发 | 按普通 PR 流程；无 method branch merge |
| database 在 main 接入 | 可选 PR；若改 `core/` 仍建议 branch + MERGE_REVIEW |

### Agent 必须执行的步骤

1. **汇报实验结果**：EX、run_id、相对 `main` 的 commit 列表（`git log --oneline main..HEAD`）
2. **展示合入选项**（见 [user-interaction-contract.md](user-interaction-contract.md) §MERGE_REVIEW 模板）
3. **等待用户明确选择** `[M]` / `[K]` / `[R]`
4. 仅当用户选 **`[M]`**：
   ```bash
   git fetch origin
   git checkout main && git pull
   git merge <feature-branch>   # 或用户指定的 merge 方式
   # 冲突 → 暂停，逐文件与用户确认，禁止静默 ours/theirs
   ```
5. 选 **`[K]`**：记录「保留在 `<branch>`」，**禁止**在 `main` 上复制粘贴相同改动
6. 选 **`[R]`**：记录 deprecated，不再在该 branch 继续

### 典型反模式（禁止）

```
❌ feature/c3sql 上 commit 4885bdb，main 上又单独 commit fd976f0（同标题不同 hash）
❌ /run 成功后 Agent 自动 merge，用户不知情
❌ 从未 merge，却告诉用户「已合入 main」
✅ MERGE_REVIEW → 用户 [M] → git merge feature/c3sql → 解决冲突 → 测试 → commit
```

### 与 `/run` 的关系

```
/run PHASE C（评估）→ DELIVERY（record-run）→ REPORT → MERGE_REVIEW → （可选）merge
```

`record-run` **只归档实验**；**不表示**已合入 `main`。

---

## 工具

```bash
python3 tools/artifact_state.py set-dev-mode --slug <slug> --mode main|branch|worktree
python3 tools/artifact_state.py check-branch --slug <slug> --type method [--allow-main]
python3 tools/artifact_state.py prepare-run --dataset <ds> --method <method>
```

method 在 `main` 上 **默认** gate 失败；`set-dev-mode --mode main` 后放行。

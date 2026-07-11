# Squrve 2.0

Text2SQL 研究框架。通过 ARIS 风格 SKILL.md 合约接入社区方法和数据集，自动复现评估。

Pipeline: `/candidate-reader` → `/integration-pipeline`（细粒度 adapters）→ `/run`（**debug 运行问题、跑通整条 reproduce config**，再评估出分）→ 可选 `/meta-evo`（基于 reproduce artifacts 的自进化 loop engineering）。
`/method-adapter` 与 `/database-adapter` 仅为对应分支的兼容薄封装。

**双 Agent（共享 SSOT）**：`skills/`、`tools/`、`templates/` 为单源真相；`.claude/skills/` 与 `.agents/skills/` 通过扁平 symlink 暴露同一套 SKILL.md。Claude Code 读本文件 + `.claude/`；Codex 读 [AGENTS.md](./AGENTS.md) + `.agents/`。详见 [harness/README.md](./harness/README.md)。

## 核心原则

1. **原生重构**：接入 = 用 Squrve Actor API 重新实现算法，不复制候选源码运行。候选源码仅作为算法文档参考。
2. **Spec → 确认 → 交付**：接入前须与用户确认方案（见 `shared-references/user-interaction-contract.md`）。**实验结束后须 MERGE_REVIEW**：用户明确选择是否将 feature branch 合入 `main`（见 `git-experiment-isolation.md` §MERGE_REVIEW）。
3. **最小侵入**：默认不改 Engine / Router / Evaluator。
4. **分支隔离（method 默认 / database 豁免）**：
   - **method**：**默认**不在 `main` 上改 Actor / Task 注册；须在 feature 分支或 worktree 上开发。**用户可显式选择 Main 模式**（见下）。
   - **database**：可在 **`main` 直接接入**（以新增 `benchmarks/`、`sys_config` 注册为主）；若需改 runtime core，仍建议独立分支。

`skills/` 描述流程和人工判断；`tools/` 的确定性脚本做状态推进与校验。

## Branch + Worktree 混合开发模式

> **一句话**：一个方向持续调试用 **feature branch**；多个方向并行推进用 **worktree**；新路线、新实验、新 benchmark 须从最新 `main` 新开。

完整 Agent 执行合同见 `skills/shared-references/git-experiment-isolation.md`。

### 开发前：询问用户模式

开始 method 开发前须确认：

```text
本次开发你希望使用哪种模式？

1. Branch 模式 — 单一方向持续调试（修 bug、调 prompt、改 config、同一 benchmark 迭代）
2. Worktree 模式 — 多个方向并行（FinSQL + EHRSQL + C3SQL 等同时进行）
3. Main 模式 — 直接在 main 上开发（须你明确确认；默认不推荐 method）

若只集中调试一个方向 → 推荐 Branch。
若需同时推进多个方向 → 推荐 Worktree。
若你明确要在 main 上改（如平台+harness 联调、临时验证）→ 可选 Main，Agent 须说明风险后再执行。
```

用户确认后再创建分支/worktree，或登记 Main 模式：

```bash
# 用户选择 Main 模式后（method 也适用）
python3 tools/artifact_state.py set-dev-mode --slug <slug> --mode main
python3 tools/artifact_state.py check-branch --slug <slug> --type method --allow-main
```

**Main 模式风险（须告知用户）**：method 的 Actor/Task 改动直接进入共享主干，可能影响他人与其他实验；合入前仍须 `/run` 与 review。Agent **不得**在未获用户明确选择 Main 模式时静默在 main 上改 method Actor。

### 1. 多方向并行 → Worktree

每个并行方向 = 一个 worktree = 一个 feature branch：

```bash
git checkout main && git pull
git worktree add ../squrve-finsql -b feature/finsql-20260629 main
git worktree add ../squrve-ehrsql -b feature/ehrsql-20260629 main
```

```text
squrve/                 # main
squrve-finsql/          # FinSQL
squrve-ehrsql/          # EHRSQL
squrve-c3sql-align/     # C3SQL 对齐
```

### 2. 单一方向持续调试 → Feature Branch

同一方向内反复调试时，**不必**每次新建 worktree；在同一 feature branch 上连续 commit 即可：

```bash
git checkout main && git pull
git checkout -b feature/finsql-debug-20260629
# 修改 → 跑实验 → 修 bug → commit → 继续
```

**可留在同一 branch 的工作**（同一方向连续调试）：

- 修 bug、调 prompt、补 adapter、改 config、修 evaluator
- 跑同一 benchmark、优化同一方法实现细节

### 3. 必须新建 branch / worktree 的情况

- 接入**另一个** method / benchmark / pipeline
- 同一方法的**大版本重写**或完全不同实现路线
- 用户明确要求重新开始；当前 branch 已混乱
- 新一轮**独立实验**；需与当前实现**并行比较**
- 旧分支已 merge / reject / deprecated

| ❌ 错误 | ✅ 正确 |
|--------|--------|
| 在 `feature/finsql` 上堆叠互不相关的实验 | `feature/finsql-debug-20260629` 内连续调试 |
| 新方向仍复用旧 branch | 从 `main` 新建 `feature/finsql-rewrite-20260630` |
| 多方向共用一个 checkout | 每方向一个 worktree |

分支命名：`feature/<method>/<timestamp>`、`feature/<method>-debug-<date>`；兼容 `integrate/<slug>`。

### Method vs Database

| | method | database |
|---|--------|----------|
| 典型改动 | `core/actor/`、Task 注册、reproduce config | `benchmarks/`、schema、`sys_config.json` |
| 对已有实验的风险 | 高 | 低 |
| `main` 上开发 | **默认禁止** method Actor；**用户可选 Main 模式** | **允许** |

`artifact_state.py` 在 method 的 `complete-reader` / `gate` / `gate-adapter` 时校验分支；**在 `main` 上默认硬失败**，`set-dev-mode --mode main` 或 `--allow-main`（且用户已确认）后放行。

### Database：可直接在 main

```bash
# 在 main 上即可开始
/candidate-reader <candidate_path>   # type=database
/integration-pipeline <slug>
```

仍须遵守最小侵入：默认只新增 benchmark 数据与注册，不改 Engine/Router/Evaluator。需要 `db_backend` 等 core 扩展时，改用 `integrate/<slug>` 分支。

### 当前仓库分支

| 分支 | 内容 |
|------|------|
| **`main`** | Harness + 平台评估（metrics / token 统计 / Meta-Evo 工具）；**不含** C3SQL 等 method Actor |
| **`integrate/c3sql`** | main + C3SQL 接入（Actor、Task 注册、`configs/spider/c3sql.json`） |
| **`integrate/finsql`** | FinSQL 接入（独立维护，需定期 `rebase main`） |

```bash
# 平台 / harness / 评估开发
git checkout main

# C3SQL 开发与 /run
git checkout integrate/c3sql
python reproduce/run.py spider c3sql
```

## 最小化修改原则

接入社区 method/database 时，默认只新增候选相关内容并完成注册：

- method：新增 Actor（原生重写）、导出、Task 注册分支、reproduce config。
- database：新增 benchmark 数据目录、注册 `config/sys_config.json`、reproduce config。

尽可能不修改 Squrve 核心源码。避免改 `Engine` / `Router` / `DataLoader` / `Evaluator`。如果确实必须改 Squrve 核心，必须先说明：

1. 为什么不能通过新增文件或注册完成。
2. 修改的最小范围。
3. 对已有方法/数据集的回归验证命令。

详见 `skills/shared-references/README.md` 与 `squrve-framework.md`

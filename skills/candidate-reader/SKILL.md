---
name: candidate-reader
description: 深度阅读候选项目源码，分析 Text2SQL 方法或数据集结构，产出 manifest 供下游 adapter 使用。接入候选时首先触发此 skill。
disable-model-invocation: true
---

# Candidate Reader

**前置阅读**：`shared-references/squrve-framework.md`、`shared-references/README.md`、`shared-references/user-interaction-contract.md`

**接收**：候选路径或 URL  
**产出**：`artifacts/<slug>/reader/` 全套（manifest.json、handoff.md、exploration/）→ 交给 `integration-pipeline`
模板：`templates/reader/`、`templates/manifest/`

---

## 交互门控

| 阶段 | 时机 | 内容 |
|------|------|------|
| INTAKE | §1b | slug/路径/类型/约束确认 |
| BRANCH | §1c | method 强制切分支；database 可在 main |
| SPEC_REVIEW | §3e | mapping + Actor 分层 + DAG 草案 |
| DELIVERY | §5b | validate 结果 + 下游建议 |

---

## Steps

### 1. GATE

推导 `<slug>`（目录名小写，除非用户指定）。

```bash
mkdir -p artifacts/<slug>/reader/exploration artifacts/<slug>/adapter artifacts/<slug>/reproduce-runs
touch artifacts/<slug>/interview-log.md
```

### 1b. INTAKE

向用户确认：

1. slug 与路径
2. method / database
3. target_datasets 预期
4. 约束（standalone_fallback、零 core 改动、API/GPU 限制）

记入 `interview-log.md` Round 1。拒绝 → 停止。

### 1c. 分支门控（INTAKE 确认 type 后立即执行）

**先问 Branch / Worktree / Main 模式**（见 `git-experiment-isolation.md`），用户确认后再建分支/worktree 或 `set-dev-mode --mode main`。

| type | 规则 |
|------|------|
| **method** | **默认**不在 `main`；须 feature branch 或 worktree。**用户可选 Main 模式**（须登记 `set-dev-mode`） |
| **database** | **可在 `main` 继续**。仅当 manifest 预计需要 db_backend 等 core 改动时，建议独立分支 |

工具强制校验（method）：

```bash
artifact_state.py check-branch --slug <slug> --type method
# complete-reader / gate / gate-adapter(method) 也会自动校验
```

详见 `squrve-framework.md` §分支隔离。

### 2. ASSEMBLE CONTEXT

读取 shared-references（先 squrve-framework → README → artifact-pipeline → reader-recursion-contract → adapter-integration-dag → user-interaction-contract）。

### 3. DUAL SUBAGENT EXPLORATION

**必须并行**启动两个 subagent（`run_in_background: false`）。

#### 3a. Squrve 框架探索

explore subagent，**从 Squrve 仓库根目录递归扫描整个仓库**（不是只读 `core/`/`reproduce/`/`config/`）：

- **探索根**：Squrve 仓库根（`<repo-root>/`）
- **必须覆盖**：`core/`、`config/`、`reproduce/`、`benchmarks/`、`skills/`、
  `tools/`、`templates/`、`harness/`、`files/` 布局、根目录文档（`CLAUDE.md` 等）
- **允许跳过**（写入 `skipped_paths` 并注明 reason）：`.git`、`__pycache__`、`.venv`、
  大二进制/数据目录（如 `benchmarks/**/database/*.sqlite`、`files/pred_sql/`、
  `artifacts/<other-slug>/`）、可再生输出
- 每个应扫描的 `.py`/`.sh`/关键配置 ∈ `scanned_files` ∪ `skipped_paths`
- 每个 `.py` 标注职责；列出所有**接入扩展点**（file:line）
- 标注禁止修改模块（Engine/Router/Evaluator）
- 写入 `exploration/squrve-inventory.md` + `squrve-coverage.json`

Subagent prompt 要点：

```text
Repository root: <repo-root>/
Write: artifacts/<slug>/reader/exploration/squrve-inventory.md
       artifacts/<slug>/reader/exploration/squrve-coverage.json
Thoroughness: very thorough — recurse the ENTIRE Squrve repo from root, not only core/.
Must include skills/, tools/, templates/, harness/, benchmarks/ structure, reproduce/, config/.
Each .py must appear in scanned_files or skipped_paths with reason.
Return: path list written + count of modules mapped to each Squrve component group.
```

#### 3b. Candidate 探索

explore subagent，递归 `<candidate_path>`：
- 完整目录树（跳过 `__pycache__`/`.git`/大数据）
- 识别所有可执行入口与功能模块
- 按 I/O 语义映射 Squrve Actor layer（**非物理打包**）
- 写入 `exploration/candidate-inventory.md` + `candidate-coverage.json`

**Actor 层映射**：产出 `schema_links` → parser；产出 `instance_schemas` → reducer；产出 `pred_sql` → generator。同一 `.py` 多阶段须按函数拆。详见 `reader-recursion-contract.md`。

#### 3c. Coverage 合同

两份 coverage JSON 必须满足：
- 每个文件 ∈ scanned ∪ skipped
- 每个 scanned ∈ 某 module.files
- 每个 module 含 inputs/outputs/io_artifact

#### 3d. SYNTHESIZE

合并两份 inventory，写 `exploration/mapping-matrix.md`：

| Candidate 模块 | 源文件 | Squrve 组件 | 输入→输出 | needs_* | 接入策略 |

**Actor 边界审计**：追溯每个模块的 I/O 链；I/O 匹配优先于物理打包。

### 3e. SPEC_REVIEW

写 `reader/spec-draft.md`（status: draft），含：
- type、target_datasets、exec_process 草案
- integration.dag + notes
- Actor 分层简表
- 风险 / open_questions

呈现给用户 → approve/revise/reject。**禁止**在 approve 前写 manifest。

### 4. WRITE ARTIFACTS

- **profile.md** — 项目概述、架构、依赖
- **manifest.json** — 须与 approved spec-draft 一致；method/database 骨架见 `templates/reader/*-manifest.json`
- **handoff.md** — 给下游 adapter 的上下文：关键文件、难点、Actor 映射、open_questions 裁决；骨架见 `templates/reader/handoff.md`

### 5. VALIDATE

```bash
artifact_state.py validate-manifest --slug <slug>
artifact_state.py validate-reader-artifacts --slug <slug>
```

### 5b. DELIVERY

向用户呈现 validate 结果 + manifest 与 spec-draft 差异（应为空）+ 下游建议。approve 后 → §6。

### 6. COMPLETE

```bash
artifact_state.py complete-reader --slug <slug> --source-path <path>
```

---

## Checklist

- [ ] INTAKE 已记录 type（method / database）
- [ ] method：已在 feature branch / worktree，**或**用户已选 Main 模式且 `set-dev-mode --mode main`；database：在 `main` 或已按需切分支
- [ ] 两个 subagent 并行完成，exploration/ 五文件齐全
- [ ] Squrve subagent 已从**仓库根**递归覆盖（含 `skills/`、`tools/`、`templates/`、`harness/`、`benchmarks/` 结构，非仅 `core/`）
- [ ] spec-draft approved
- [ ] Actor 边界审计通过（I/O 证据）
- [ ] validate 通过
- [ ] DELIVERY approved
- [ ] complete-reader 成功

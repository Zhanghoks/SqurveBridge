# Candidate Reader — 交互与访谈合同

`candidate-reader` 专用。通用三阶段门控见 [user-interaction-contract.md](user-interaction-contract.md)。

## 核心目标

Reader 阶段**不是**急于写 manifest 或定死接入方案，而是：

1. **先穷尽理解候选源码** — 结构、运行方式、参数、数据流、复现命令、依赖与边界条件
2. **再对照 Squrve 找最小映射** — 在理解源码的前提下，探索 Squrve 中对应扩展点，尽量以**小改动、原生重构**方式接入
3. **与用户逐项确认差异** — 源码行为 vs Squrve 映射之间的每一处差异，须访谈记录并获 approve

下游 adapter 以 reader 产出的复现信息为**唯一算法依据**；不得跳过 reader 访谈直接写 Actor。

---

## 访谈轮次

| 轮次 | 代号 | 时机 | 目的 |
|------|------|------|------|
| R1 | **INTAKE** | §1b，GATE 后 | 确认 slug、路径、type、target_datasets、硬约束 |
| R2 | **DEEP_INTERVIEW** | 读 shared-references 后、**启动探索前** | 弄清用户真实需求与复现目标，再搭脚手架 |
| R3 | **CANDIDATE_REVIEW** | 候选探索完成后、Squrve 探索前 | 呈现源码理解摘要，确认无重大遗漏 |
| R4 | **MAPPING_REVIEW** | 合成 mapping 后、spec-draft 前 | 呈现源码→Squrve 映射与**全部差异清单**，逐项确认 |
| R5 | **SPEC_REVIEW** | spec-draft 完成后 | 方案可行？Actor 分层与 DAG 是否 approve |
| R6 | **DELIVERY** | validate 通过后 | 锁定交付并推进 state |

每轮 append 到 `artifacts/<slug>/interview-log.md`。用户已在本轮给出等价明确指令时可 `skipped: true` 并注明依据。

---

## R2 — DEEP_INTERVIEW（探索前必做）

在用户 approve **前**，禁止启动 subagent 探索或写 exploration 文件。

### 必问清单

**复现与评估**

1. 目标 benchmark / 子集（dev / test / 自定义 slice）？
2. 期望对齐的**官方指标**与 baseline 分数（若有）？
3. 是否必须复现论文/仓库 README 中的**完整 pipeline**，还是允许 smoke / slice？
4. 候选仓库中**哪条命令或脚本**被视为 ground-truth 复现入口？

**资源与约束**

5. 可用 LLM / embedding / API（provider、model、是否必须本地）？
6. GPU / 显存 / 离线限制？
7. 是否允许改候选源码？（Squrve 原则：**不复制运行候选代码**，仅作算法文档）
8. 是否允许改 Squrve `core/`（Engine/Router/Evaluator 默认禁止）？

**接入边界**

9. 用户最在意的**保真项**（prompt 模板、投票逻辑、schema 格式、db_contents、few-shot 等）？
10. 已知可接受简化或 defer 的部分？
11. `standalone_fallback` 或其它合并 Actor 层是否可接受？（须单独确认）

**交付预期**

12. 本次接入 scope：仅 reader+spec，还是 reader→adapter→run 全链路？
13. 有无 deadline 或优先完成的 stage？

### 呈现格式

```markdown
## 需求访谈摘要 — <slug>

**复现目标**：…
**Ground-truth 入口**：`<path or command>`
**保真项**（必须对齐）：…
**可协商项**：…
**资源约束**：…
**Scope**：reader only | through adapter | through /run

请确认：**[A] 开始探索** | **[R] 补充/修订** | **[X] 暂停**
```

---

## R3 — CANDIDATE_REVIEW

候选探索完成后呈现（不等 Squrve 探索）：

- 目录结构与模块职责
- **运行复现清单**：入口命令、环境变量、config 文件、数据路径、stage 顺序
- 各 stage 的 **输入 / 输出 / 中间产物**（含文件名与格式）
- 关键超参与默认值（须标注定义位置 file:line）
- `open_questions`（源码中未读清或需用户补充的部分）

用户 approve 后才进入 Squrve 探索。

---

## R4 — MAPPING_REVIEW

合成 `mapping-matrix.md` 后、写 `spec-draft.md` 前呈现。

### 差异清单（必填）

对每一项标注 **对齐 / 近似 / 待确认 / 不可对齐**：

| 维度 | 源码行为 | Squrve 映射 | 差异说明 | 用户决策 |
|------|----------|-------------|----------|----------|
| 例：schema 格式 | `prompt_generate.py` 紧凑格式 | `parse_schema_from_df`  verbose | 格式不同影响 prompt | 近似，adapter 重写为紧凑格式 |
| 例：db_contents | `get_db_contents()` top-2 | `bridge_content` | 接口一致 | 对齐 |

**原则**：

- 评估目标是衡量**算法本身**，不能少信息（低分）也不能多信息（虚高）
- 每一处「近似」或「待确认」须用户明确 approve 或 revise
- 禁止在 MAPPING_REVIEW approve 前写 manifest

---

## 与 Adapter 的衔接

`handoff.md` 须包含：

- **复现运行手册**（命令、参数、产物路径）
- **已确认差异表**（MAPPING_REVIEW 锁定版）
- **每层 Actor 的源码锚点**（file:line + 函数名）

各 adapter（尤其 `actor-adapter`）在写 spec-draft **前**须重读上述锚点；若发现新差异 → 追加访谈轮次，不得静默偏离。

---
name: run
description: 以 reproduce config 为入口，debug 运行问题直至整条 pipeline 跑通；跑通后产出 scores.json、workflow trace、SQL feature/QVT 切片与 eval-store。config-adapter 完成后触发，或用户直接 /run。
disable-model-invocation: true
---

# Run

## Run 的目标

**`/run` 的首要目标不是「立刻出分」，而是 debug 运行中产生的问题，直到整条 config 定义的 pipeline 能稳定跑通。**

| 优先级 | 目标 | 完成标准 |
|--------|------|----------|
| **1** | **Debug 跑通** | `reproduce/configs/<dataset>/<method>.json` 中声明的 data_source、task/stage、Actor 链能从小切片到全量**无崩溃、无阻塞性错误**地执行完毕 |
| **2** | **评估出分** | 跑通后再进入 PHASE C，产出 EX、stage/workflow 归因、SQL feature/QVT 切片与 `scores.json` |
| **3** | **交付记录** | `record-run` 归档本次 run，可选进入 evaluator-report / self-improve |

**「跑通整个 config」的含义**：

- config 里配置的 **dataset 切片 / 全量** 均能走完（Reducer → Generator → Selector 等 stage 按 config 顺序执行）
- 运行期暴露的 **import 失败、路径缺失、Actor 逻辑错误、执行/SQL 崩溃、checkpoint/resume 异常** 等，在 `/run` 内定位并修复（默认只改 Actor 与 reproduce config）
- 切片渐进（`:3 → :10 → 全量`）是手段；**终点是当前 config 对应规模的一次完整成功 run**

debugger + monitor 合一：PHASE A/B 专注跑通与修复，PHASE C 才评估。每次 `reproduce/run.py` 成功后创建新的 `artifacts/<dataset>-<method>-YYYYMMDD-HHMMSS/`，永不覆盖。

**接收**：`reproduce/configs/<dataset>/<method>.json`  
**产出（跑通后）**：`artifacts/<run_id>/scores.json`、`detailed-report.txt`、`weakness_profile.md`、`artifacts/eval-store.sqlite` + EX 分数 → 可选交给 `evaluator-report`

---

## 交互门控

| 阶段 | 内容 |
|------|------|
| INTAKE | dataset/method、全量 vs smoke、**API key / `.env` 是否就绪** |
| SPEC_REVIEW | 若需改 core → 单独确认 |
| DELIVERY | record-run 前报告 EX 与修复轮数 |
| **MERGE_REVIEW** | record-run 后：是否在 feature branch 上、是否合入 `main`（**须用户选 [M]/[K]/[R]**） |

---

## API Key 与 `.env`（INTAKE 必查）

Squrve **不会**自动读取 shell 里未 export 的变量；`reproduce/run.py` 启动时会加载**仓库根目录**的 `.env`（若存在），并用于补齐 config 中的 `api_key`。

### 推荐做法

1. 复制模板：`cp .env.example .env`
2. 填写与 `llm.use` 对应的 key（例：`llm.use=qwen` → `QWEN_API_KEY=sk-...`）
3. reproduce config 中 **保留 placeholder**，不要把真实 key 写进 `reproduce/configs/`：

```json
"api_key": {
  "qwen": "your_api_key_here"
},
"llm": { "use": "qwen", "model_name": "..." }
```

4. 或显式引用环境变量：

```json
"api_key": {
  "qwen": "${ENV:QWEN_API_KEY}"
}
```

### Provider → 环境变量

| `llm.use` | `.env` 变量 |
|-----------|-------------|
| `qwen` | `QWEN_API_KEY` |
| `deepseek` | `DEEPSEEK_API_KEY` |
| `zhipu` | `ZHIPU_API_KEY` |
| `openai` | `OPENAI_API_KEY` |
| `claude` | `ANTHROPIC_API_KEY` |

### 优先级

1. config 中非 placeholder 的明文 key（本地调试可用，**勿提交**）
2. config 中 `${ENV:VAR}` 引用
3. `.env` 中对应 `*_API_KEY`
4. 已在 shell export 的同名环境变量（`.env` 不覆盖已有 env）

### GATE 校验

`prepare-run` 会调用与 `run.py` 相同的解析逻辑。若 active provider 仍无 key，停止并提示设置 config 或 `.env`：

```bash
python3 tools/artifact_state.py prepare-run --dataset <ds> --method <method>
# 失败示例：qwen api_key is placeholder; set ... or QWEN_API_KEY in repo-root .env
```

### 常见误区

| 误区 | 说明 |
|------|------|
| 只建 `.env` 不跑 `run.py` | 需在**仓库根**执行 `python reproduce/run.py ...`，才会 load `.env` |
| key 写在 config 里又 commit | `reproduce/configs/` 已 gitignore；真实 key 放 `.env` |
| `llm.use=deepseek` 但只填了 `QWEN_API_KEY` | provider 与 env 变量须一致 |
| Cursor/IDE 终端未 reload | 改 `.env` 后重新跑 run，无需重启 IDE |

---

## Steps

### 1. GATE

```bash
artifact_state.py prepare-run --dataset <ds> --method <method>
```

记住 `RUN_ID`、`RUN_DIR`、`CONFIG`。INTAKE 确认后记入 interview-log。

### 2. PHASE A — 跑通（Run 核心阶段）

**本阶段即 `/run` 的主目标**：针对当前 config 暴露的运行问题 debug，直至该 config 规模下 pipeline 完整执行成功。

**核心原则：先静态校验，再极小切片，再诊断切片，再扩大样本，最后全量。不能一步跑全量。**

#### 2.1 启用 checkpoint

先在 config 中加 `checkpoint` 段（如 config 未含）：

```json
"checkpoint": {
  "enabled": true,
  "interval": 1,
  "save_state": true
}
```

- `interval: 1` → 每样本完成后立即 flush（小切片用）
- `interval: 10` → 每 10 样本 flush 一次（全量用，减少 I/O）

#### 2.2 执行模式：默认逐个 sample

`/run` 默认就是逐个 sample 模式：一个样本完整跑完 `[Reducer → Generator → Selector]` 后再算完成。config 中**不要显式配置** `pipeline_run_mode`，除非用户明确要求诊断 stage-mode。

**默认：逐个 sample 模式**

```
ThreadPool(16 workers)
  worker_0: sample_0 → [Reducer → Generator → Selector] → 完成
  worker_1: sample_1 → [Reducer → Generator → Selector] → 完成
  ...
```

每个线程拿一个样本，跑完完整 pipeline 的所有 stage。1000 个样本分给 16 个线程并发执行。

特点：
- checkpoint 粒度为 pipeline 整体（`finsql_full1` 每个样本完成后标记）
- resume 粒度为样本级（已完成样本直接跳过，零 LLM 调用）
- 内存低（每线程只持 1 样本）
- `_actor_trace` 会记录每个 sample 内各 actor 的中间输入、输出、row_delta、耗时、错误
- 适合所有常规 debug、smoke、全量运行

**诊断开关：逐 stage 模式（非默认）**

```
Stage 1: [Reducer  × 1000 samples] → 全部完成
Stage 2: [Generator × 1000 samples] → 全部完成
Stage 3: [Selector  × 1000 samples] → 全部完成
```

所有样本先跑完 Reducer，再一起跑 Generator，最后一起跑 Selector。

只有用户明确要求“按 stage 整批跑”或需要复现 stage-mode bug 时才使用。触发条件（需显式配置，3 个条件全部满足）：
1. config 中设 `pipeline_run_mode: "stage"`
2. 至少一个 actor 有 `stage_dataset_save_path`（即 `is_save_dataset: true` + `dataset_save_path` 非空）
3. executor 是 `PipelineActor`

特点：
- checkpoint 粒度为每个 stage 独立（`finsql_reduce1`、`finsql_generate1`...）
- resume 粒度：stage+样本级（已完成 stage 整体跳过，跨 stage 可部分 resume）
- 内存较高（stage 间需保留中间数据集）
- 日志按阶段分段，但运行语义不同，不能作为默认路径

**选择规则**：始终使用逐个 sample 模式。stage eval 不要求 stage-mode；只要每个 task 配 `dataset_save_path`，sample-mode 也会保存中间 row snapshot 并产出 stage/workflow 指标。

#### 2.3 切片逐步扩展

先确认原 config 的 `<benchmark>:<split>:`，再只改第三段 filter。推荐切片阶梯：

```
quick-1  →  smoke-3  →  smoke-10  →  diag-25  →  stable-50  →  confidence-100  →  full
```

| 阶段 | data_source 第三段 | 目的 | 通过标准 |
|------|--------------------|------|----------|
| quick-1 | `1` | import/config/单样本路径 smoke | 无 import/path/task 初始化错误 |
| smoke-3 | `3` | 暴露 Actor I/O、保存路径、基础 SQL 错误 | pipeline 完整结束，生成 scores |
| smoke-10 | `10` | 看初步错误分布和 workflow attribution | 无系统性崩溃；错误可归因 |
| diag-25 | `25` | 验证修复是否覆盖更多 DB/question 类型 | 同类 bug 不再反复出现 |
| stable-50 | `50` | 验证并发、checkpoint、actor trace/中间 row snapshot | checkpoint/resume 正常 |
| confidence-100 | `100` | 全量前稳定性门槛 | 无阻塞错误，scores/eval-store 可写 |
| full | 空 | 正式评估 | 全量完成 |

每轮固定执行顺序：

1. 静态校验：
   ```bash
   python tools/verify.py json-load --path reproduce/configs/<dataset>/<method>.json
   python tools/verify.py config-task --path reproduce/configs/<dataset>/<method>.json --expected-task <TaskClass>
   ```
2. 修改 config：
   - `dataset.data_source`
   - 每个 `task_meta[].data_source`
   - 需要时同步 `checkpoint.interval`：小切片 `1`，50+ 样本 `10`
3. 清理本 method 的 checkpoint。只清目标目录，不清全局产物：
   ```bash
   python - <<'PY'
   import shutil
   from pathlib import Path
   target = Path("files/checkpoints/<dataset>-<method>")
   if target.exists():
       shutil.rmtree(target)
   PY
   ```
4. 运行：
   ```bash
   SQURVE_EVAL_SCOPE=smoke python reproduce/run.py <dataset> <method>
   ```
   full 前都用 `SQURVE_EVAL_SCOPE=smoke`，避免把小切片误当统计有效结论。
5. 记录本轮最新 artifact：
   ```bash
   ls -td artifacts/<dataset>-<method>-* | head -1
   ```
6. 分析 `scores.json`、`detailed-report.txt`、checkpoint state，再决定扩大、修复或回退。

resume 测试只在 `stable-50` 或之后做：

```bash
python reproduce/run.py <dataset> <method> --resume
```

预期：已完成样本被跳过；若又发起 LLM 调用或重跑大量样本，先修 checkpoint/resume。

#### 2.4 每轮关注什么

| 轮次 | 必看文件/命令 | 关注点 |
|------|---------------|--------|
| quick-1 | stdout traceback | import、Actor 注册、config 字段、API key、路径 |
| smoke-3 | `scores.json.per_sample` | `pred_sql` 是否落盘、EX 是否可算、字段是否缺失 |
| smoke-10 | `workflow_trace.aggregate` | 失败集中在哪个 stage：reducer/generator/selector |
| diag-25 | `per_sample[].workflow.stages` | 每个 actor 的 status、signals、runtime 是否可定位 |
| stable-50 | `files/checkpoints/<dataset>-<method>/state.json` | checkpoint 进度、resume 粒度、actor trace/中间 row snapshot |
| confidence-100 | `by_sql_feature`, `by_scenario`, `qvt` | JOIN/subquery/aggregation 等切片是否有系统弱点 |
| full | `eval-store.sqlite`, `weakness_profile.md` | 跨 run 可查询、最终报告完整 |

快速检查命令：

```bash
python - <<'PY'
import json, glob
from pathlib import Path
p = Path(sorted(glob.glob("artifacts/<dataset>-<method>-*/scores.json"))[-1])
s = json.loads(p.read_text())
print("scores:", p)
print("EX:", s["aggregate"]["ex"])
print("workflow:", s.get("workflow_trace", {}).get("aggregate", {}).get("bottleneck_distribution"))
print("sql slices:", {k:v["count"] for k,v in s.get("by_sql_feature", {}).items() if v.get("count")})
print("qvt:", {k:s.get("qvt", {}).get(k) for k in ("eligible_groups","flip_rate")})
PY
```

#### 2.5 切片内修复循环

每当切片暴露出 bug：

1. **定位**：从终端日志 + `scores.json.per_sample` 提取错误样本
2. **诊断**：优先看 `workflow.attribution`、`workflow.stages`、`_actor_trace`、`exec_error`、`error_root`、`error_sub`
3. **修复**：只改 Actor（Reducer/Generator/Selector），不改 Engine/Router/Evaluator
4. **重跑**：清 checkpoint → 重跑当前切片 → 验证修复效果
5. 修复轮数记录到 `debug-log`

**常见 bug 模式**：

| 症状 | 根因 | 修复方向 |
|------|------|----------|
| `execution_error: column_not_found` | LLM 编造不存在的列名 | Reducer/Generator 加 schema 列名校验 |
| `execution_error: table_not_found` | LLM 选错表 | Reducer 加关键词预过滤缩小候选范围 |
| `model_missing_join` | Schema Linking 漏了关键表 | 放宽 topk_table_num / 预过滤阈值 |
| 全量评估时 `max()` TypeError | scores 中 None 值 | pipeline_delta.py 做 None-safe |

**修改 Engine/Router/Evaluator → 先 SPEC_REVIEW 获用户单独确认。**

#### 2.6 扩大样本/进入全量

扩大样本的判断不只看 EX。满足以下条件再进入下一档：

- exit code = 0
- `scores.json`、`detailed-report.txt`、`weakness_profile.md` 均生成
- `workflow_trace.aggregate.bottleneck_distribution` 非空
- `per_sample[].workflow.attribution` 至少覆盖失败样本
- 小切片阶段没有 `valid=0/total=N` 的评估失效
- checkpoint state 可读

进入 full 前：

1. 改 `data_source` 回 `"<dataset>:<split>:"`（无 filter）
2. 调 `checkpoint.interval` 到 `10`
3. 取消 `SQURVE_EVAL_SCOPE=smoke`
4. 清目标 checkpoint → 后台跑全量
5. 如全量评估阶段崩溃（scores 构建/评估），修完用 `--resume` 跳过已完成样本重评

---

### 3. PHASE B — 全量运行与监控

全量运行时间长（1000 样本约 10-15 分钟），必须支持**后台运行 + 间隔监控 + 对话交互**。

#### 3.1 启动全量（后台模式）

全量跑可用后台 session，避免阻塞对话。命令：

```bash
python reproduce/run.py <dataset> <method>
```

命令启动后记录 session id、开始时间、config path、当前 git diff 摘要。

#### 3.2 监控进度

**用户可随时通过对话询问进度**，无需等待完成。监控从两个数据源读取：

**A. 终端日志（实时）**
```bash
tail -n 80 <task_output_file>
grep "任务进度" <task_output_file> | tail -1
# → 任务进度: 420/1000 (42.0%)
```

**B. checkpoint state（精确）**
```bash
python3 -c "
import json
s = json.load(open('files/checkpoints/<dataset>-<method>/state.json'))
stage = s['current_stage']
done = s['current_stage_sample_index']
total = s['sample_total']
print(f'{stage}: {done}/{total} ({done/total*100:.1f}%)')
"
```

**C. 已落盘中间 row snapshot（阶段数据）**
```bash
find files/checkpoints/<dataset>-<method>/datasets -type f -maxdepth 1 2>/dev/null
```

**D. 最新 artifact（评估完成后）**
```bash
ls -td artifacts/<dataset>-<method>-* 2>/dev/null | head -1
```

**监控输出格式**（向用户呈现）：

```
全量运行中 — bull-en finsql
  进度: ████████░░░░░░░░░░  420/1000 (42%)
  Stage: finsql_full1
  当前处理: dev_427 @ ccks_stock
  耗时: ~6 min  |  预计剩余: ~8 min
  Token: 58,000 (prompt) + 12,300 (completion)
```

#### 3.3 用户交互协议

用户可在运行期间发起以下交互：

| 用户说 | 动作 |
|--------|------|
| "进度" / "到哪了" | 读取 checkpoint state，输出本轮监控报告（§3.2 格式） |
| "暂停" / "停一下" | `Ctrl+C` 杀后台进程（checkpoint 自动保留），下次 `--resume` 恢复 |
| "继续" / "恢复" | `python reproduce/run.py <dataset> <method> --resume` |
| "还有多久" | 根据当前速率估算剩余时间 |
| "token 用了多少" | 统计目前 token 消耗 |
| "有哪些错误" | 从已完成的错误样本中提取 error_root 分布 |

**用户定义监控间隔**（可选）：

```
用户: 每 2 分钟告诉我一次进度
→ 设置 CronCreate, cron="*/2 * * * *", 自动读取 checkpoint 并报告
→ 完成后 CronDelete 取消定时
```

默认**不设自动定时**——只在用户主动询问时响应，避免刷屏。

#### 3.4 运行完成

进程退出后：

1. 检查 exit code
2. 若 `exit 1` → 查看 stderr 尾部的 Traceback → 进入 §2.5 修复循环 → `--resume`
3. 若 `exit 0` → 定位最新 artifact → 进入 PHASE C

---

### 4. PHASE C — 评估

从 stdout 提取 EX，并检查 `artifacts/<run_id>/scores.json`。当前评估系统应输出：

| 层级 | 产物 |
|------|------|
| Final | EX, EM, SF1, SC, VES, RVES, CF1, FD |
| Stage | `stage_metrics`：reduce/parse/generate/select 的 aggregate + per-sample |
| Workflow | `workflow_trace`、`per_sample[].workflow.stages`、`per_sample[].workflow.attribution` |
| SQL feature | `per_sample[].sql_features`、`by_sql_feature`、`by_scenario` |
| Consistency | `qvt`：同 gold SQL 多问法稳定性/flip rate |
| Runtime | `_actor_trace`、token、latency、row_delta |
| Store | `artifacts/eval-store.sqlite`：runs/samples/sql_features/stage_metrics |

评估必须走 reproduce artifact。若 `scores.json` 缺失或字段不完整，先从 reproduce saved datasets、pred_sql、config 重建 scores；不要调用独立 evaluator 作为替代路径：

```bash
python tools/eval_scores.py --help
```

评估完整性检查：

```bash
python - <<'PY'
import json, sqlite3
from pathlib import Path
artifact = Path("<artifact_dir>")
scores = json.loads((artifact / "scores.json").read_text())
required = ["aggregate", "per_sample", "workflow_trace", "by_sql_feature", "by_scenario", "qvt"]
missing = [key for key in required if key not in scores]
print("missing:", missing)
print("sample_count:", scores.get("sample_count"))
print("EX:", scores.get("aggregate", {}).get("ex"))
print("workflow:", scores.get("workflow_trace", {}).get("aggregate", {}).get("bottleneck_distribution"))
store = artifact.parent / "eval-store.sqlite"
print("eval_store_exists:", store.exists())
if store.exists():
    with sqlite3.connect(store) as conn:
        print("store samples:", conn.execute("select count(*) from samples where run_id=?", (scores["run_id"],)).fetchone()[0])
PY
```

检查失败时不要只报 EX；先修 scores 构建、stage eval 或 eval-store 持久化，保证评估闭环完整。

DELIVERY approve 后：

```bash
artifact_state.py record-run --dataset <ds> --method <method> --run-id <id> --ex-score <score> --debug-rounds <N> --config-path <path> --pred-sql-dir <dir> --dataset-save-dir <dir> --artifact-dir <artifact_dir> --scores-path <artifact_dir>/scores.json --eval-store-path artifacts/eval-store.sqlite
```

---

### 5. REPORT

向用户报告：本次 EX、历史最佳、修复轮数概要。EX 偏低 → 提示可进入 evaluator-report / self-improve。

---

### 6. MERGE_REVIEW — 是否合入 main（必做，feature branch 上）

**`/run` 与 `record-run` 不等于 merge。** 若当前不在 `main`（常见 method 开发），**必须**进入 MERGE_REVIEW，不得静默结束。

#### 6.1 检查当前分支

```bash
git branch --show-current
git log --oneline main..HEAD
git merge-base --is-ancestor HEAD main && echo "already on main history" || echo "not merged yet"
```

#### 6.2 向用户呈现（模板见 `user-interaction-contract.md` §MERGE_REVIEW）

必含：分支名、相对 main 的 commits、EX/跑通结论、主要改动、合入选项 **[M] 合入 / [K] 保留分支 / [R] 放弃**。

**默认假设：不合入**（`[K]`），直到用户明确选 `[M]`。

#### 6.3 用户选 [M] 后才执行

```bash
git fetch origin
git checkout main && git pull
git merge <feature-branch>
# 有冲突 → 列出文件、展示 diff、与用户确认后再 resolve
# merge 后：跑相关 tests / smoke
```

#### 6.4 禁止

| 禁止 | 原因 |
|------|------|
| 在 `main` 上重做 feature branch 相同改动 | 产生平行 commit，历史无法 `--contains` |
| 未 MERGE_REVIEW 就 `git merge` / push main | 用户未授权合入 |
| `record-run` 后直接结束 | 缺少 merge 决策 |

Main 模式（已在 main）：跳过 merge，REPORT 中说明「改动在 main，push 前请 review」。

记录：`artifacts/<slug>/interview-log.md` → `## Round N — MERGE_REVIEW`。

---

## Debug 原则

**所有修复必须遵循源码逻辑与框架设计**，不得引入 hack 或破坏现有架构。

### 修改范围

| 允许（无确认） | 需 SPEC_REVIEW |
|----------------|---------------|
| Actor 内部逻辑（Reducer/Generator/Selector/Parser） | Engine / Router / Evaluator |
| reproduce config（`configs/`） | `core/task/` 基类 |
| reproduce metrics（`reproduce/metrics/`） | `core/data_manage.py` |
| reproduce eval（`reproduce/eval/`） | 框架级签名变更 |

### 修复顺序

修改前先理解源码，按此优先级：

1. **Config 级** — 调参数（topk、temperature、候选数）是否能解决？成本最低。
2. **Actor 级** — 在现有 Actor 内部加校验/过滤/重试。不改接口签名。
3. **Pipeline 级** — 调整 stage 顺序或 task_lis 结构。
4. **Core 级** — 最后手段，需 SPEC_REVIEW。

### 修复范例

```
❌ 错误做法：
   FINSQLReducer 返回 None 时，直接跳过整个 stage → 破坏 pipeline 数据流

✅ 正确做法：
   FINSQLReducer 加列名校验 → LLM 返回的列对照 schema 过滤 →
   无效列丢弃并 warn → 全部无效则 fallback 到前 K 表/列 →
   保持输出 schema 结构不变，下游 Generator 正常工作
```

### 回退策略

每轮修复只改一个文件。修复无效时用 `git checkout -- <file>` 回退，重新诊断。

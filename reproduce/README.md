# Reproduce

Squrve 的**实验复现入口**：加载 `configs/` 下的 JSON，驱动 `Engine` 跑 method pipeline，并自动评估、落盘 scores。

工作目录约定：CLI 会在内部 `chdir` 到 `reproduce/`，config 里的相对路径（如 `../files/...`）均相对于该目录解析。

---

## 快速开始

```bash
# 1. 在仓库根目录创建本地环境文件（.env 已被 gitignore）
cp .env.example .env
# 2. 仅在 .env 中填写对应 provider 的 API Key，不要写入 config 或提交到 Git
# 3. 从仓库根目录运行
python reproduce/run.py spider c3sql
python reproduce/run.py BookSQL dinsql
```

提交前请运行 `python tools/security_scan.py --history`；若密钥曾进入 Git
历史，即使当前文件已删除，也必须先轮换密钥并清理历史后再发布。

等价写法（已在 `reproduce/` 下时）：

```bash
python run.py spider c3sql
```

---

## 目录结构

```
reproduce/
├── run.py                 # 单次实验 CLI
├── batch_run.py           # 分批收敛实验 CLI
├── configs/
│   ├── template.json      # 新 config 模板
│   ├── spider/c3sql.json
│   ├── spider/c3sql.json
│   └── BookSQL/           # dinsql, resdsql, unisar, sede
├── runner/
│   ├── run.py             # 执行 + 评估主逻辑
│   └── batch_run.py       # mini-batch 收敛跑法
├── eval/
│   ├── utils.py           # EX / 自定义指标评估
│   ├── stage_eval.py      # 各 stage checkpoint 的阶段指标
│   └── report.py          # 终端报告
├── metrics/               # 内置 Squrve 指标与 scores 组装
├── external_metrics/      # 可选 benchmark/外部指标 adapter（默认不运行）
└── lib/
    └── paths.py           # config 路径、run identifier 工具
```

---

## 实验配置

**路径规则**：`reproduce/configs/<dataset>/<method>.json`

**Run identifier**（产物命名前缀）：`<dataset>-<method>`，例如 `spider-c3sql`。

复制 `configs/template.json` 或仓库根目录 `templates/reproduce/` 下的骨架后替换占位符。
字段说明见 [`skills/shared-references/reproduce-config-schema.md`](../skills/shared-references/reproduce-config-schema.md)，
工作区约定见 [`skills/shared-references/reproduce-workspace-contract.md`](../skills/shared-references/reproduce-workspace-contract.md)。

### Config README 合同

每个可运行 config 应有一个伴随 README：

```text
reproduce/configs/<dataset>/<method>.README.md
```

README 的自动生成区块由 `templates/reproduce/config-readme.md` 渲染，人工说明写在
生成标记之外。刷新与校验：

```bash
python tools/reproduce_contract.py generate-readmes --path reproduce/configs/<dataset>/<method>.json
python tools/verify.py reproduce-contract --path reproduce/configs/<dataset>/<method>.json

# 校验全部可运行 config（跳过 auxiliary/policy JSON）
python tools/verify.py reproduce-contract --all
```

### 当前内置 config

| Config | 说明 |
|--------|------|
| `spider/c3sql` | C3SQL 三阶段（Reduce → Parse → Generate） |
| `spider/c3sql` | C3SQL |
| `BookSQL/dinsql` | DIN-SQL（BookSQL） |
| `BookSQL/resdsql` | RESDSQL |
| `BookSQL/unisar` | UNISAR |
| `BookSQL/sede` | SEDE |

### 单阶段 vs 多阶段

- **单阶段**：一条 `task_meta` + `engine.exec_process: ["generate"]`
- **多阶段**：每个 layer 一条 `task_meta`（`task_id` 如 `{method}_reduce`），再加 `cpx_task_meta` 描述 pipeline 顺序；`exec_process` 指向 complex task id（如 `c3sql_full`）

多阶段 config 应为**每个 stage** 设置 `is_save_dataset: true` 和独立的 `dataset_save_path`，便于阶段评估与排查。

### `data_source` 第三段（filter）

格式：`<benchmark>:<split>:<filter>`

| 第三段 | 行为 |
|--------|------|
| 空（`spider:dev:`） | 全量 |
| 纯数字（`BookSQL:val:20`） | 取前 N 条（head limit，可复现 smoke） |
| 命名 filter（`spider:dev:has_label`） | 按条件筛选（`has_label`、`difficulty`、`db_size`、`limit-N` 等） |

随机抽样用 config 里的 `dataset.random_size`（与 head limit 不同）。

缓存文件：`../files/data_source/<benchmark>_<split>_<filter>.json`。若 filter 改过但文件名未变，需删除旧缓存或设 `overwrite_exist_file: true`。

---

## 运行实验

### `run.py` — 单次全量/子集跑通 + 评估

```bash
python reproduce/run.py <dataset> <method>
```

流程：

1. 加载 `configs/<dataset>/<method>.json`，构建 `Router` + `Engine`
2. `engine.execute()` 执行 pipeline
3. 评估并打印报告
4. （full 模式）写入 `artifacts/<run_id>/scores.json`

### `batch_run.py` — 分批直到指标收敛

按 batch 递增样本量，监控 EX（或其它指标）变化，适合大数据集上的 early stopping：

```bash
python reproduce/batch_run.py spider c3sql
python reproduce/batch_run.py spider c3sql --batch-size 10 --metric ex --delta 0.02 --patience 2
python reproduce/batch_run.py spider c3sql --max-batches 3    # smoke
python reproduce/batch_run.py spider c3sql --resume           # 从 batch state 恢复
python reproduce/batch_run.py spider c3sql --dry-run          # 只看 batch 划分
```

产物目录：`../files/datasets/<dataset>-<method>/batch_run/`（含 `state.json`、累计预测等）。

> `batch_run` 的 `--resume` 与单次 `run.py` 无关，仅恢复 batch 状态。

单次 reproduce run 的 checkpoint 与该 run 的数据快照绑定在同一个目录：

```text
files/runs/<run-id>/checkpoints/
```

```bash
python reproduce/run.py spider c3sql --resume
python reproduce/run.py spider c3sql --resume-from files/runs/<run-id>/checkpoints/state.json
```

`--resume` 选择该 dataset-method 最近一次可恢复的 run；`--resume-from` 则恢复
指定 run。恢复过程复用原 run ID 和原 checkpoint datasets，不会创建一个只继承
completed IDs、却丢失历史行数据的新 workspace。

---

## 产物与路径

Config 中路径均相对 `reproduce/`，常见落盘位置：

| 类型 | 典型路径 | 说明 |
|------|----------|------|
| 数据源缓存 | `../files/data_source/` | benchmark 加载后的 JSON |
| Schema | `../files/schema_source/` | 解析后的 schema |
| 阶段 dataset | `../files/datasets/{dataset}_{method}_{stage}.json` | 各 stage 中间结果 |
| 预测 SQL | `../files/pred_sql/{dataset}_{method}/` | Actor 写出的 SQL 文件 |
| 评估 scores | `artifacts/<dataset>-<method>-YYYYMMDD-HHMMSS/` | `scores.json`、`meta-evo-input.json` 等 |

命名示例（C3SQL）：

- `spider_c3sql_reduce.json` / `spider_c3sql_parse.json` / `spider_c3sql_full.json`
- `../files/pred_sql/spider_c3sql/`

---

## 评估

### 终端指标

`run.py` 默认输出：

| 层级 | 指标 |
|------|------|
| 最终 SQL | **EX**（执行准确率） |
| 自定义（需 sqlglot） | **EM**, **SF1**, **SC**, **VES**, **CF1**, **FD** |
| 阶段（多 stage config） | 各 `task_meta.eval_type`（如 `reduce_recall`、`parse_exact_matching`） |

阶段指标从各 stage 的 `dataset_save_path` checkpoint 读取；`generate_num > 1` 时会带 iteration 后缀。

### 环境变量

| 变量 | 作用 |
|------|------|
| `SQURVE_EVAL_MODE=minimal` | 只跑 EX + 基础自定义指标，不写 scores 详情 |
| `SQURVE_EVAL_MODE=scores_only` | 静默报告，仍写 scores |
| `SQURVE_EVAL_MODE=full` | 默认：完整报告 + scores |
| `SQURVE_EVAL_OUTPUT_DIR=<path>` | 指定 scores 输出目录 |
| `SQURVE_EVAL_SKIP_TOKEN=1` | scores 中跳过 token 统计 |
| `SQURVE_EVAL_SKIP_PIPELINE_DELTA=1` | 跳过 pipeline delta 计算 |
| `SQURVE_EVAL_BASELINE_SCORES=<path>` | 与 baseline scores 对比，写 `delta-report.json` |
| `SQURVE_EVAL_SCOPE=smoke` | 缩小 scores 统计范围 |

### 依赖

- 基础 EX：Squrve `core.evaluate`
- EM / SF1 / SC / VES / CF1 / FD：`pip install sqlglot`（缺失时 EX 仍可用，自定义指标会跳过）

### 可选外部指标

外部或 benchmark-specific 指标不属于默认评估。它们应放在
`reproduce/external_metrics/<metric_id>/`，与 `reproduce/metrics/` 中的通用
Squrve 指标分开。

默认规则：

- 没有 `external_eval` 或 `external_eval.enabled: false` 时，不运行外部指标。
- 外部指标启用必须先由 `metric-adapter` 交互确认，并写入
  `artifacts/<slug>/metric/spec.json`。
- reproduce config 的 `external_eval` 只是运行时开关，必须引用确认过的
  `metric/spec.json`。
- 外部指标结果未来应写入 `scores.json.external_metrics`，不要混入
  `aggregate` 的内置指标。

示例结构：

```json
"external_eval": {
  "enabled": true,
  "adapters": [
    {
      "id": "ehrsql_reliability",
      "enabled": true,
      "source_artifact": "artifacts/<slug>/metric/spec.json"
    }
  ]
}
```

---

## 接入新 method

1. 在 feature 分支完成 Actor + Task 注册（见仓库 `CLAUDE.md` 分支策略）
2. 复制 `configs/template.json` → `configs/<dataset>/<method>.json`
3. 校验：

```bash
python tools/verify.py json-load --path reproduce/configs/<dataset>/<method>.json
python tools/verify.py config-task --path reproduce/configs/<dataset>/<method>.json --expected-task <TaskClass>
python tools/verify.py reproduce-contract --path reproduce/configs/<dataset>/<method>.json
```

4. 跑通：

```bash
python reproduce/run.py <dataset> <method>
```

更完整的接入流程见 `skills/run/SKILL.md` 与 `integration-pipeline/SKILL.md`。

---

## 相关文档

- Config schema：`skills/shared-references/reproduce-config-schema.md`
- 框架总览：`skills/shared-references/squrve-framework.md`
- `/run` skill：`skills/run/SKILL.md`

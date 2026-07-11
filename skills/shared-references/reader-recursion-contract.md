# Reader Recursion & Actor Allocation Contract

`candidate-reader` 与 `validate-reader-artifacts` 的共同依据。

## 1. 递归覆盖

### 1.1 Squrve 仓库（subagent A）

**探索根 = Squrve 仓库根目录**，递归扫描整个仓库，不得只读 `core/`/`reproduce/`/`config/`。

| 必须纳入 inventory | 说明 |
|--------------------|------|
| `core/` | Router、Engine、Actor、Task、LLM、RAG |
| `config/`、`reproduce/` | 系统配置与运行入口 |
| `benchmarks/` | 目录结构与 schema/dataset 格式（可不读全量 `.sqlite`） |
| `skills/`、`tools/` | harness 流程、shared-references、artifact_state |
| `files/` | 运行时产物路径约定 |
| 根目录 | `CLAUDE.md` 等接入约束 |

允许跳过：`.git`、`__pycache__`、`.venv`、大二进制、其它 slug 的 `artifacts/`、
`files/pred_sql/` 等（写入 `skipped_paths`）。

`squrve_component` 取值：`llm`、`embedding`、`prompt`、`rag`、`actor.*`、
`task`、`evaluator`、`harness`、`benchmark`、`config` 等。

### 1.2 Candidate 仓库（subagent B）

从 `<source_path>`（候选路径）递归扫描 `**/*.py`, `**/*.sh`, `requirements.txt`, `**/*.yaml` 等。
允许跳过 `.git`/`__pycache__`/大二进制/数据目录（写入 `skipped_paths` 并注明 reason）。

**共同规则**：每个应扫描文件 ∈ `scanned_files` ∪ `skipped_paths`；每个 scanned ∈ 某 `modules[].files`。

### Module 必填字段

```json
{
  "id": "table_recall",
  "files": ["src/table_recall.py"],
  "summary": "LLM ranks tables → filtered schema",
  "squrve_component": "actor.reducer",
  "inputs": ["question", "raw_schema"],
  "outputs": ["instance_schemas"],
  "io_artifact": "instance_schemas"
}
```

## 2. I/O → Actor Layer

按**数据流语义**分配，禁止按文件物理打包。

| `io_artifact` | Layer | stage |
|---------------|-------|-------|
| `instance_schemas` | reducer | reduce |
| `schema_links` | parser | parse |
| `sub_questions` | decomposer | decompose |
| `pred_sql_candidates` | scaler | scale |
| `pred_sql` | generator | generate |
| `pred_sql`（精修） | optimizer | optimize |
| `pred_sql`（择优） | selector | select |

## 3. Anti-Monolith

校验 FAIL 条件：

1. coverage 有 `actor.parser`，manifest `actor.parser` 为空
2. ≥2 module 不同 `io_artifact` 却只对应一个 actor layer 且无 `standalone_fallback`
3. 文件错层（parser 文件出现在 generator 的 `source_files`）
4. `exec_process` stage 数 ≠ 非空 layer 数

### standalone_fallback（唯一合并例外）

candidate 确实无独立中间产物时可归入 generator：

```json
{ "standalone_fallback": true, "standalone_reason": "schema inlined in prompt" }
```

## 4. 合成算法

```
coverage modules → 按 io_artifact 去重 → pipeline stages
每个 layer 一条 manifest 条目（source_files = 该 layer 的 module.files）
同一 .py 多 stage → 按函数拆 module
validate-reader-artifacts
```

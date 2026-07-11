---
name: retrieval-adapter
description: 配置 RAG 索引和 few-shot 检索，用 Squrve 原生 RagPipeLines 和 add_few_shot 接口。
disable-model-invocation: true
---

# Retrieval Adapter

1 个 skill 映射 2 个 state stage：`rag` 与 `few_shot`。

`state.rag === null` **且** `state.few_shot === null` → **整个跳过**。

**接收**：`manifest.components.rag` + `manifest.components.few_shot`  
**产出**：`rag/index-config.json` + `rag/few-shot-config.json` → 供 `config-adapter`

---

## 交互门控

`rag/spec-draft.md` → SPEC_REVIEW → configs → DELIVERY → 各 stage done。

## RAG（`state.rag !== null` 时）

1. `artifact_state.py gate rag <slug>`
2. 写 `rag/index-config.json`（含 `config_snippet.database`）
3. 仅 `needs_new_retrieval_strategy` 时修改 `RagPipeline.py`
4. `verify.py rag-index --path <dir>`
5. `artifact_state.py done rag <slug>`

## FEW-SHOT（`state.few_shot !== null` 时）

1. `artifact_state.py gate few-shot <slug>`
2. 写 `rag/few-shot-config.json`（含 `config_snippet.dataset`）
3. 新 db_type 示例 → `files/reasoning_examples/system/<db_type>/`
4. `verify.py few-shot-examples --path <dir> --minimum 1`
5. `artifact_state.py done few-shot <slug>`

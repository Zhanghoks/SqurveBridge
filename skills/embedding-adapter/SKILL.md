---
name: embedding-adapter
description: 配置 embedding 模型，按需扩展 Squrve RAG 初始化。用 Squrve 原生 embedding 工厂，不复制候选 embedding 代码。
disable-model-invocation: true
---

# Embedding Adapter

`state.embedding === null` → 跳过。

**接收**：`manifest.components.embedding`  
**产出**：`model/embedding-config.json` → 供 `config-adapter` 合并

---

## 交互门控

`model/embedding-spec-draft.md` → SPEC_REVIEW → config → DELIVERY → done。

## Steps

1. `artifact_state.py gate embedding <slug>`
2. 只读 `manifest.components.embedding`
3. 写 `model/embedding-config.json`（含 `text_embed` config_snippet）
4. 组件为空但 rag/few_shot 非空 → 用 Squrve 默认 embedding，不改源码
5. `needs_new_embed_model=true` 时最小修改 `get_hf_embedding_model()` 等工厂
6. `verify.py json-load --path <config>`
7. `artifact_state.py done embedding <slug> --set needs_new_embed_model=<bool>`

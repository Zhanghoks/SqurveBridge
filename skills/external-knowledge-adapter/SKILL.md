---
name: external-knowledge-adapter
description: 配置 external knowledge，按需扩展 Squrve add_external 处理函数。
disable-model-invocation: true
---

# External Knowledge Adapter

`state.external === null` → 跳过。

**接收**：`manifest.components.external`  
**产出**：`external/external-config.json` → 供 `config-adapter`

---

## 交互门控

`external/spec-draft.md` → SPEC_REVIEW → config → DELIVERY → done。

## Steps

1. `artifact_state.py gate external <slug>`
2. 只读 `manifest.components.external`
3. 写 `external/external-config.json`（含 `config_snippet`）
4. method 新函数 → 扩展 external 处理模块；database → `benchmarks/<slug>/<sub>/external/`；已有函数 → 只写 config
5. `verify.py json-load` → `artifact_state.py done external <slug>`

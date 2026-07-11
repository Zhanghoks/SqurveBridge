---
name: schema-adapter
description: 校验或转换 benchmark schema 为 Squrve 统一格式。
disable-model-invocation: true
---

# Schema Adapter

**接收**：`manifest.components.schema`  
**产出**：`schema/conversion.md` + 转换后的 schema.json → 供 `config-adapter`

---

## 交互门控

`schema/spec-draft.md`（字段映射、是否新脚本）→ SPEC_REVIEW → 转换 → DELIVERY → done。

## Steps

1. `artifact_state.py gate schema <slug>`
2. 只读 `components.schema`
3. `needs_conversion=false` → 只验证记录
4. `needs_conversion=true` → 优先复用 `central_schema_process()`，否则新增转换脚本
5. **逐条处理**所有数组元素
6. 写 `schema/conversion.md`
7. `verify.py json-load` 验证所有 schema.json
8. `artifact_state.py done schema <slug>`

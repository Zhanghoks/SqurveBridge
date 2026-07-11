---
name: db-backend-adapter
description: 仅在 sqlite/big_query/snowflake 不支持时新增 database backend。高风险操作须单独确认。
disable-model-invocation: true
---

# DB Backend Adapter

`state.db_backend === null` → 跳过。

**接收**：`manifest.components.db_backend`  
**产出**：`db_connect.py` 最小扩展 + `db/backend.md`

---

## 交互门控

`db/spec-draft.md` + **高风险单独确认** → SPEC_REVIEW → 实施 → DELIVERY → done。

## Steps

1. `artifact_state.py gate db-backend <slug>`
2. 只读 `components.db_backend`
3. 最小扩展 `core/db_connect.py`（不改 Engine/Router/Evaluator）
4. 写 `db/backend.md`（为何现有 backend 不适用、凭证边界、回归命令）
5. 验证 → `artifact_state.py done db-backend <slug>`

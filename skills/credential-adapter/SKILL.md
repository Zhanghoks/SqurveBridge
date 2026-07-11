---
name: credential-adapter
description: 为远程 database 生成不含密钥值的 credential 配置占位。
disable-model-invocation: true
---

# Credential Adapter

`state.credential === null` → 跳过。

**接收**：`manifest.components.credential`  
**产出**：`credential/config.json`（占位符 + config_snippet）→ 供 `config-adapter`

---

## 交互门控

`credential/spec-draft.md`（字段名、env 引用，**不含 secret**）→ SPEC_REVIEW → DELIVERY → done。

## Steps

1. `artifact_state.py gate credential <slug>`
2. 写 `credential/config.json`（字段名 + 环境变量引用，**禁止写真实 secret**）
3. `verify.py json-load` → `artifact_state.py done credential <slug>`

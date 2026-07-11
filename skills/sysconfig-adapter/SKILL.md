---
name: sysconfig-adapter
description: 将 benchmark 幂等注册到 config/sys_config.json。
disable-model-invocation: true
---

# Sysconfig Adapter

**接收**：`benchmark/registration.json` + `manifest.components.benchmark_meta`  
**产出**：`sys_config.json` 更新 + `sysconfig/registration.json` → 供 `config-adapter`
模板：`templates/benchmark/registration.json`、`templates/benchmark/sys-config-entry.schema.json`

---

## 交互门控

`sysconfig/spec-draft.md` → SPEC_REVIEW → 注册 → DELIVERY → done。

## Steps

1. `artifact_state.py gate sysconfig <slug>`
2. 只读 `components.benchmark_meta`
3. 按 `benchmark-registration.md` 新增条目（禁止重复 id）；条目骨架见 `templates/benchmark/sys-config-entry.schema.json`
4. **逐条注册**所有数组元素
5. 写 `sysconfig/registration.json`
6. `verify.py benchmark-registered --slug <slug>`
7. `artifact_state.py done sysconfig <slug>`

---
name: method-adapter
description: 兼容入口；调用 integration-pipeline 的 method 分支
argument-hint: "<slug>"
---

# Method Adapter Compatibility Wrapper

读取 `skills/integration-pipeline/SKILL.md`。确认
`artifacts/<slug>/reader/manifest.json` 的 `type` 为 `method`，然后严格执行
integration-pipeline 的 method 序列。此 skill 不直接实现或注册 Actor，也不直接写
最终 config；对应职责分别属于细粒度 adapters、workflow-adapter 与 config-adapter。

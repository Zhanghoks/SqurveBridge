---
name: database-adapter
description: 兼容入口；调用 integration-pipeline 的 database 分支
argument-hint: "<slug>"
---

# Database Adapter Compatibility Wrapper

读取 `skills/integration-pipeline/SKILL.md`。确认
`artifacts/<slug>/reader/manifest.json` 的 `type` 为 `database`，然后严格执行
integration-pipeline 的 database 序列。此 skill 不直接复制 benchmark 或写最终
config；对应职责属于细粒度 database adapters 与 config-adapter。

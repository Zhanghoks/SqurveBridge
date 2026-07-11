---
name: prompt-adapter
description: 接入 prompt 模板或 schema-linking prompt，理解候选 prompt 策略后用 Squrve 原生方式实现。
disable-model-invocation: true
---

# Prompt Adapter

**接收**：`manifest.components.prompt`  
**产出**：`prompt/spec.json` + 模板文件 → 供 Actor 和 `config-adapter` 使用

---

## 原生重构

理解候选的 prompt 设计思想，在 Squrve prompt 体系中重新实现。不复制候选 prompt 构造代码。

## 交互门控

`prompt/spec-draft.md`（inline vs 新类、layer 绑定）→ SPEC_REVIEW → 落盘 → DELIVERY → done。

## Steps

1. `artifact_state.py gate prompt <slug>`
2. 只读 `manifest.components.prompt`
3. 全部 `needs_prompt_class=false` → spec 记 `status: inline`，`done prompt <slug> --status inline`
4. 独立 prompt → `core/actor/prompts/<Name>Prompt.py`
5. schema-linking prompt → 扩展 PromptStore / SchemaLinkingTool
6. `verify.py json-load` → `artifact_state.py done prompt <slug>`

---
name: actor-adapter
description: 按 Squrve Actor API 原生重写候选方法的算法逻辑，产出各 layer 的 Actor 实现。不复制候选源码，忠于算法重构。
disable-model-invocation: true
---

# Actor Adapter

**前置阅读**：`shared-references/squrve-framework.md` §原生重构、`shared-references/actor-registration-chain.md`

**接收**：`manifest.components.actor` + `reader/handoff.md`  
**产出**：`core/actor/<layer>/<Name>.py` + `<layer>/spec.json` → 交给 `workflow-adapter`

---

## 原生重构（核心原则）

**不 import 候选仓库任何模块**。候选源码仅作为算法文档：

1. 从 `handoff.md` 和候选源码**理解**算法逻辑、prompt 模板、数据流
2. 用 `Base*` 基类 + `act()` 签名**从零编写** Squrve Actor
3. LLM 调用走 `self.llm`，schema 走参数，保存走 Squrve 约定路径
4. 保留候选方法的算法思想（prompt 策略、投票逻辑、pipeline 设计），代码全新

---

## 交互门控

每层先写 `<layer>/spec-draft.md` → SPEC_REVIEW → approve → 写代码 → DELIVERY → done。

---

## Steps

Gate `actor`，只读 `manifest.components.actor`。按固定顺序处理存在的层：

`generator → parser → reducer → scaler → decomposer → optimizer → selector → agent`

每层：

1. **SPEC_REVIEW**：写 `<layer>/spec-draft.md`（class_name、源文件映射、task_meta 草案）→ 用户 approve
2. **创建 Actor**：`core/actor/<layer>/<Name>.py`，继承 `Base*`，实现 `act()`
3. **写 spec.json**：layer、actors[]、task_meta（含 task_id、task_type、meta）
4. **禁止**修改 `__init__.py` 或 Task `load_actor()`（归 workflow-adapter）
5. **验证**：`verify.py actor-syntax --path <file> --class-name <Class>`
6. **DELIVERY** → `artifact_state.py done actor <slug> --layer <layer> --class-name <Class>`

### task_meta 格式

```json
{
  "task_meta": {
    "task_id": "<slug>_<layer>",
    "task_type": "<Layer>Task",
    "meta": {
      "task": { "<layer>_type": "<ClassName>" },
      "actor": { "自定义参数" }
    }
  }
}
```

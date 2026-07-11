---
name: workflow-adapter
description: 汇聚 Actor spec，完成导出、Task 分支注册和 ComplexTask 编排。actor-adapter 完成后触发。
disable-model-invocation: true
---

# Workflow Adapter

**前置阅读**：`shared-references/actor-registration-chain.md` §②③

**接收**：`<layer>/spec.json`（所有已完成 layer）  
**产出**：`__init__.py` 导出 + Task 分支 + `workflow/changes.json` → 交给 `config-adapter`

---

## 交互门控

写 `workflow/spec-draft.md`（分支列表、ComplexTask）→ SPEC_REVIEW → 实施 → DELIVERY → done。

---

## Steps

Gate `workflow`，读 manifest + 所有 `<layer>/spec.json`。

按 layer 幂等更新：

1. `core/actor/<layer>/__init__.py`：追加 try/import 导出
2. `core/task/meta/<Layer>Task.py::load_actor()`：
   - 顶部 import
   - `registered_*_type` 列表追加
   - if-elif 链追加分支（在 fallback 前）
3. 仅 `need_complex_task=true` 时处理 ComplexTask

**不得实现 Actor**。写 `workflow/changes.json` 记录注册目标。

### ComplexTask 执行模式

`ComplexTask` 有两种执行模式，**默认逐样本**（`pipeline_run_mode = "sample"`），无需显式配置：

| 模式 | pipeline_run_mode | 行为 |
|------|-------------------|------|
| **逐样本**（默认） | `"sample"` | 线程池并发，每线程拿一个样本跑完完整 pipeline 的所有 stage |
| 逐 stage | `"stage"` | 全部样本先跑完 Stage 1，再一起 Stage 2，最后 Stage 3 |

**选择规则**：始终默认逐样本模式。只有在需要分阶段评估中间指标（如 schema linking recall）时才切换到 `"stage"`。

> 详见 `skills/run/SKILL.md` §2.2

### 验证

```bash
verify.py actor-import --layer <layer> --class-name <Class>
verify.py task-branch --path <Task.py> --actor-type <type> --class-name <Class>
```

全部通过 → `artifact_state.py done workflow <slug>`。

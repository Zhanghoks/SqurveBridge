# Actor Registration Chain

新方法接入 Squrve 的 **5 步注册链**。

## 原生重构提醒

写 Actor 时是**用 Squrve API 重新实现算法**，不是复制候选源码。参考候选的 prompt 模板和数据流，产出的 `.py` 必须是从零构建的 Squrve Actor。详见 [squrve-framework.md](squrve-framework.md) §原生重构。

## 5 步

```
① 写 Actor     core/actor/<layer>/<Name>.py      ← actor-adapter
② 导出         core/actor/<layer>/__init__.py     ← workflow-adapter
③ Task 分支    core/task/meta/<Layer>Task.py      ← workflow-adapter
④ Reproduce    reproduce/configs/<dataset>/<method>.json  ← config-adapter
⑤ 验证         verify.py actor-import / json-load
```

### ① 写 Actor

```python
class <Name>Generator(BaseGenerator):
    def act(self, item, schema=None, schema_links=None, sub_questions=None, **kwargs):
        ...
```

`__init__` 必须接受 `**kwargs`。

### ② 导出（追加末尾）

```python
try:
    from .NewMethodGenerate import NewMethodGenerator
except Exception:
    NewMethodGenerator = None
```

### ③ Task 分支

```python
elif actor_type in ("FooGenerator", "Foo") and FooGenerator:
    actor = FooGenerator(**generate_args)
    return actor
```

### ④ Reproduce config

`meta.task.generate_type` = `"<Name>Generator"`

### ⑤ 验证

```bash
verify.py actor-import --class-name <Name>Generator
verify.py json-load --path reproduce/configs/<dataset>/<method>.json
```

## 9 层一览

| Layer | 基类 | Task | 配置键 |
|-------|------|------|--------|
| Generate | `BaseGenerator` | `GenerateTask` | `generate_type` |
| Parse | `BaseParser` | `ParseTask` | `parse_type` |
| Reduce | `BaseReducer` | `ReduceTask` | `reduce_type` |
| Scale | `BaseScaler` | `ScaleTask` | `scale_type` |
| Decompose | `BaseDecomposer` | `DecomposeTask` | `decompose_type` |
| Optimize | `BaseOptimizer` | `OptimizeTask` | `optimize_type` |
| Select | `BaseSelector` | `SelectTask` | `select_type` |
| Agent | `BaseAgent` | `AgentTask` | `agent_type` |
| Nest | `ComplexActor` | `ComplexTask` | — |

## 多阶段方法

每层完成 ①–③；config-adapter 聚合：

- 多条 `task_meta`（`task_id`: `<slug>_<layer>`）
- 一条 `cpx_task_meta`（`task_lis` = 数据流顺序）
- `exec_process` → `"<slug>_full"`

详见 [reproduce-config-schema.md](reproduce-config-schema.md) §多阶段。

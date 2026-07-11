# Fine-grained Adapter Integration Contract

adapter 与 state 的绑定规则。DAG 设计见 [adapter-integration-dag.md](adapter-integration-dag.md)。

## 主流程

```
candidate-reader → integration.dag adapters → config-adapter → /run
```

接入顺序由 `integration.dag` 声明，**不是**固定 pipeline。各 stage 写最终产物前须 SPEC_REVIEW（见 [user-interaction-contract.md](user-interaction-contract.md)）。

## 原生重构要求

每个 adapter 实现的代码必须是 **Squrve 原生代码**：

- actor-adapter：用 `Base*` 基类重写算法，不 import 候选模块
- llm/embedding/prompt：对接 Squrve 已有工厂和接口
- 候选源码仅作为算法理解参考

详见 [squrve-framework.md](squrve-framework.md) §原生重构。

## Skill ↔ State

| Skill | State stage |
|-------|-------------|
| `retrieval-adapter` | `rag`, `few_shot` |
| `config-adapter` | `adapter` |
| 其余 | 同名（连字符→下划线） |

## Skip 规则

`state.<stage> === null` 时不 gate/done：

| Skill | 跳过条件 |
|-------|----------|
| embedding-adapter | `state.embedding === null` |
| retrieval-adapter | `rag` **且** `few_shot` 均 null |
| external-knowledge-adapter | `state.external === null` |
| db-backend-adapter | `state.db_backend === null` |
| credential-adapter | `state.credential === null` |

## Adapter 规范

1. **Gate**：`gate <stage> <slug>`
2. **只读**自己的 `manifest.components.<group>`
3. **只写**文档规定的 artifact 目录与源文件
4. 跑 verification
5. **Done**：`done <stage> <slug>`（须 DELIVERY approve）

数组遍历：`components.*` 均为数组，必须处理**每一个**元素。

## Status 语义

| 值 | 含义 |
|----|------|
| `done` | 已完成验证 |
| `inline` | 合并在其它组件内 |
| `null` | Reader 判定不存在 |
| `pending` | 未运行 |

## 所有权

| 组件 | 拥有者 |
|------|--------|
| Actor 实现 + spec.json | actor-adapter |
| Actor 导出 + Task 分支 | workflow-adapter |
| reproduce config | config-adapter |
| index/few-shot config | retrieval-adapter |

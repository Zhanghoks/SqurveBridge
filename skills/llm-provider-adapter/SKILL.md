---
name: llm-provider-adapter
description: 接入或配置候选方法声明的 LLM provider，对接 Squrve LLM 工厂。用 Squrve 原生接口配置，不复制候选调用代码。
disable-model-invocation: true
---

# LLM Provider Adapter

**接收**：`manifest.components.llm`  
**产出**：`model/config.json`（config_snippet）→ 供 `config-adapter` 合并

---

## 原生重构

不复制候选的 LLM 调用代码。对接 Squrve 已有 `init_llm()` / `load_llm_by_args()` 工厂；仅 `needs_new_provider` 时最小扩展。

## 交互门控

`model/spec-draft.md` → SPEC_REVIEW → config.json → DELIVERY → done。

## Steps

1. `artifact_state.py gate llm-provider <slug>`
2. 只读 `manifest.components.llm`
3. 写 `model/config.json`（含 `config_snippet`）
4. **`api_key` 段只写 placeholder 或 `${ENV:...}`**，不写真实 key；用户在仓库根 `.env` 维护 secret（见 `run` skill §API Key 与 `.env`）
5. 仅 `needs_new_provider` 时创建 `core/llm/<Provider>Model.py`，最小改 `data_manage.py`
6. `verify.py provider-registered --provider <p> --model-class <C>`
7. `artifact_state.py done llm-provider <slug> --set needs_new_provider=<bool>`

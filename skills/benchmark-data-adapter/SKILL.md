---
name: benchmark-data-adapter
description: 接入 benchmark 的 dataset、schema 与 database 文件到 Squrve benchmarks 目录。
disable-model-invocation: true
---

# Benchmark Data Adapter

**接收**：`manifest.components.dataset` + `manifest.components.database_files`  
**产出**：`benchmarks/<slug>/<sub_id>/` 数据 + `benchmark/registration.json` → 供 `sysconfig-adapter`

---

## 交互门控

`benchmark/spec-draft.md`（splits、路径、条数）→ SPEC_REVIEW → 落盘 → DELIVERY → done。

## Steps

1. `artifact_state.py gate benchmark-data <slug>`
2. 只读 `components.dataset` + `components.database_files`
3. 数据写入 `benchmarks/<slug>/<sub_id>/`（dataset.json + schema.json + database/）
4. **逐条处理**所有数组元素（多 split/多语言）
5. 写 `benchmark/registration.json`（split、记录数、db_type、config_snippet）
6. `verify.py json-load` 逐个验证
7. `artifact_state.py done benchmark-data <slug>`

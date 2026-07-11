# Benchmark Registration

Benchmark 通过 `config/sys_config.json` 的 `benchmark[]` 注册。

可复制骨架见 `templates/benchmark/registration.json`、
`templates/benchmark/sys-config-entry.schema.json` 与
`templates/benchmark/layout.md`。

## 条目 Schema

```json
{
  "id": "<slug>",
  "root_path": "../benchmarks/<slug>",
  "db_type": "sqlite",
  "has_sub": true,
  "external": false,
  "database": true,
  "sub_data": [
    { "sub_id": "dev", "has_label": true, "use_local_database": false }
  ]
}
```

## 目录结构

```
benchmarks/<slug>/
├── <sub_id>/
│   ├── dataset.json     # [{db_id, question, query, ...}]
│   ├── schema.json      # Squrve 统一格式
│   └── database/        # 可选
│       └── <db_id>/<db_id>.sqlite
```

## 注册步骤

1. 数据写入 `benchmarks/<slug>/<sub_id>/`
2. `dataset.json` + `schema.json`（schema-adapter 可协助转换）
3. database 文件按 db_id 放入
4. `sys_config.json` 新增条目（sysconfig-adapter）
5. 从 `template.json` 生成冒烟 config
6. `verify.py benchmark-registered --slug <slug>`

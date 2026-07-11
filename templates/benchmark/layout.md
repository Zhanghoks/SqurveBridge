# Benchmark Layout — <slug>

```text
benchmarks/<slug>/
└── <sub_id>/
    ├── dataset.json
    ├── schema.json
    └── database/
        └── <db_id>/<db_id>.sqlite
```

## Required Checks

- `dataset.json` uses Squrve row fields.
- `schema.json` uses Squrve unified schema format.
- `database/` path matches `db_id` when `use_local_database=true`.
- `config/sys_config.json` has one unique `benchmark[].id`.

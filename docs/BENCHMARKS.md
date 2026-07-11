# Benchmark Sources and Distribution Scope

SqurveBridge normalizes each benchmark into a shared interface containing database
files, schema metadata, questions, gold SQL when available, splits, execution
settings, and benchmark-specific evaluation assumptions.

## Bundled Benchmarks

| Benchmark | Upstream source | Local path | Distribution |
| --- | --- | --- | --- |
| Spider | https://github.com/taoyds/spider | `benchmarks/spider/` | Bundled with public examples |
| BIRD | https://bird-bench.github.io/ | `benchmarks/bird/` | Bundled with public examples |

Large SQLite files are stored with Git LFS. Run `git lfs pull` if a clone contains
pointer files instead of databases.

## Referenced Benchmarks

The paper evaluates additional domain-specific settings. Their data is not
redistributed in this repository.

| Benchmark | Source | Expected local ID |
| --- | --- | --- |
| EHRSQL-2024 | https://github.com/glee4810/ehrsql-2024 | `ehrsql-2024` |
| BookSQL | https://github.com/Exploration-Lab/BookSQL | `BookSQL` |
| BookSQL dataset mirror | https://huggingface.co/datasets/Exploration-Lab/BookSQL | `BookSQL` |

BULL-en is referenced by the paper's financial-domain experiments, but the current
source evidence does not provide a public redistribution URL. SqurveBridge therefore
does not redistribute it or invent an unofficial download location.

## Normalized Layout

```text
benchmarks/<id>/
  <split>/dataset.json
  <split>/schema.json
  database/*.sqlite
```

After adding a benchmark, register its split and database behavior in
`config/sys_config.json`, then validate every reproduction configuration that uses
it. Third-party data remains subject to its upstream license and terms.

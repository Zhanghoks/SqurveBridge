# Benchmark Sources and Distribution Scope

SqurveBridge normalizes each benchmark into a shared interface containing database
files, schema metadata, questions, gold SQL when available, splits, execution
settings, and benchmark-specific evaluation assumptions.

## Bundled Benchmarks

| Benchmark | Upstream source | Git LFS package | Installed path |
| --- | --- | --- | --- |
| Spider | https://github.com/taoyds/spider | `benchmarks/packages/spider.zip` | `benchmarks/spider/` |
| BIRD | https://bird-bench.github.io/ | `benchmarks/packages/bird.zip` | `benchmarks/bird/` |

The package contract is recorded in `benchmarks/packages/manifest.json`. Each ZIP
contains exactly one top-level benchmark directory, and the manifest records its
source, version, checksum, sizes, required files, and sample count. Pull and
install the archives with:

```bash
git lfs pull --include="benchmarks/packages/*.zip"
python tools/benchmarks.py verify-archives
python tools/benchmarks.py install spider
python tools/benchmarks.py install bird
```

The installed directories are ignored by Git. Do not commit expanded databases or
replace the official packages with archives from unofficial mirrors.

Ordinary pull-request CI validates the manifest and Git LFS pointers without
downloading the large payloads:

```bash
python tools/benchmarks.py verify-pointers
```

Release CI downloads both payloads and runs `verify-archives`. The verifier rejects
checksum mismatches, path traversal, absolute paths, symbolic links, encrypted
members, duplicate paths, system metadata, credential files, and abnormal
compression ratios before extraction.

## External Benchmarks

SqurveBridge can normalize additional domain-specific settings when their data is
obtained under the upstream distribution terms. These datasets are not
redistributed in this repository.

| Benchmark | Source | Expected local ID |
| --- | --- | --- |
| EHRSQL-2024 | https://github.com/glee4810/ehrsql-2024 | `ehrsql-2024` |
| BookSQL | https://github.com/Exploration-Lab/BookSQL | `BookSQL` |
| BookSQL dataset mirror | https://huggingface.co/datasets/Exploration-Lab/BookSQL | `BookSQL` |

Additional datasets without a verified public redistribution URL are intentionally
not mirrored. SqurveBridge does not invent unofficial download locations.

## Normalized Layout

```text
benchmarks/<id>/
  <split>/dataset.json
  <split>/schema.json
  database/*.sqlite
```

After installing or adding a benchmark, register its split and database behavior in
`config/sys_config.json`, then validate every reproduction configuration that uses
it. Third-party data remains subject to its upstream license and terms.

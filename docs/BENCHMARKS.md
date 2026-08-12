# Benchmark Sources and Distribution Scope

SqurveBridge normalizes each benchmark into a shared interface containing database
files, schema metadata, questions, gold SQL when available, splits, execution
settings, and benchmark-specific evaluation assumptions.

## Distributed Benchmark Packages

The normalized benchmark snapshots are distributed as checksummed ZIP archives
through the Hugging Face dataset recorded in
`benchmarks/packages/manifest.json` (`distribution.hf_dataset`). The Git
repository keeps only the manifest — source, version, SHA-256, sizes,
required files, and sample counts per package — never the payloads.

| Benchmark | Upstream source | Package | Installed path |
| --- | --- | --- | --- |
| Spider | https://github.com/taoyds/spider | `spider.zip` | `benchmarks/spider/` |
| BIRD (dev) | https://bird-bench.github.io/ | `bird.zip` | `benchmarks/bird/` |
| Spider 2.0 Lite | https://github.com/xlang-ai/Spider2 | `spider2.zip` | `benchmarks/spider2/` |
| EHRSQL-2024 (MIMIC-IV Demo) | https://github.com/glee4810/ehrsql-2024 | `ehrsql-2024.zip` | `benchmarks/ehrsql-2024/` |
| BookSQL | https://paperswithcode.com/dataset/booksql | `BookSQL.zip` | `benchmarks/BookSQL/` |
| BULL-CN / BULL-EN | https://bull-text-to-sql-benchmark.github.io/ | `bull-cn.zip`, `bull-en.zip` | `benchmarks/bull-cn/`, `benchmarks/bull-en/` |
| AmbiDB | https://huggingface.co/datasets/satissss/AmbiDB | `ambidb.zip` | `benchmarks/ambidb/` |

Every snapshot is redistributed under its upstream distribution terms; the
EHRSQL-2024 package contains only the openly licensed MIMIC-IV Demo subset.
Download and install with:

```bash
python tools/benchmarks.py download spider    # or `download all`
python tools/benchmarks.py install spider
```

`download` verifies the SHA-256 and size of every fetched archive against the
manifest before it is kept; a corrupted or tampered download is rejected. The
installed directories are ignored by Git. Do not commit expanded databases or
replace the official packages with archives from unofficial mirrors.

Ordinary pull-request CI validates the manifest and any locally present
archives without downloading the large payloads:

```bash
python tools/benchmarks.py verify-pointers
```

Scheduled and release CI downloads every payload and runs `verify-archives`.
The verifier rejects checksum mismatches, path traversal, absolute paths,
symbolic links, encrypted members, duplicate paths, system metadata,
credential files, and abnormal compression ratios before extraction.

Historical note: releases up to the LFS retirement distributed the same
archives as Git LFS objects; those pointers remain valid in the published
history but new payloads ship only through the Hugging Face dataset.

## External Benchmarks

Datasets without a verified public redistribution URL are intentionally not
mirrored. SqurveBridge does not invent unofficial download locations; obtain
such data under the upstream terms and normalize it locally.

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

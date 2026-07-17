# Packaged benchmarks

SqurveBridge versions its normalized benchmark snapshots as Git LFS archives:

- `spider.zip`
- `bird.zip`
- `bull-en.zip` (SQLite and schema only)
- `ehrsql-2024.zip` (SQLite and schema only)

The archives are redistribution packages for research reproducibility, not new licenses. Review each benchmark's upstream terms and cite the original dataset. Provenance, sizes, checksums, expected sample counts, and layout requirements are recorded in `manifest.json`.

## Download and install

```bash
git lfs install
git lfs pull --include="benchmarks/packages/*.zip"

python tools/benchmarks.py verify-archives
python tools/benchmarks.py install spider
python tools/benchmarks.py install bird
python tools/benchmarks.py install bull-en
python tools/benchmarks.py install ehrsql-2024
python tools/benchmarks.py verify spider
python tools/benchmarks.py verify bird
python tools/benchmarks.py verify bull-en
python tools/benchmarks.py verify ehrsql-2024
```

Installation verifies the archive checksum and layout before replacing a benchmark directory. Pass `--force` only when intentionally replacing an existing verified installation.

## Maintainer workflow

Prepare the expanded benchmark directory locally, then run:

```bash
python tools/benchmarks.py build all
python tools/benchmarks.py verify-archives
git lfs ls-files
```

Archive construction uses stable path ordering, fixed timestamps, fixed permissions, and excludes local scripts, caches, `.DS_Store`, and SQLite WAL/SHM files. Rebuilding unchanged inputs must produce the same SHA-256.

Ordinary CI can validate LFS pointer metadata without downloading the payloads:

```bash
python tools/benchmarks.py verify-pointers
python -m unittest tests.test_benchmarks -v
```

# Packaged benchmarks

SqurveBridge versions its normalized benchmark snapshots as checksummed ZIP
archives distributed through the Hugging Face dataset recorded in
`manifest.json` (`distribution.hf_dataset`):

- `spider.zip`
- `bird.zip`
- `ambidb.zip`
- `BookSQL.zip`
- `bull-cn.zip`
- `bull-en.zip`
- `ehrsql-2024.zip`
- `spider2.zip`

The archives are redistribution packages for research reproducibility, not new licenses. Review each benchmark's upstream terms and cite the original dataset. Provenance, sizes, checksums, expected sample counts, and layout requirements are recorded in `manifest.json`.

## Download and install

```bash
python tools/benchmarks.py download all   # or a single slug, e.g. `download spider`

python tools/benchmarks.py install spider
python tools/benchmarks.py verify spider
# repeat for bird, ambidb, BookSQL, bull-cn, bull-en, ehrsql-2024, spider2
```

Every download is verified against the manifest SHA-256 and size before it is
kept. Installation verifies the archive checksum and layout before replacing a
benchmark directory. Pass `--force` only when intentionally replacing an
existing verified installation.

## Maintainer workflow

Prepare the expanded benchmark directory locally, then run:

```bash
python tools/benchmarks.py build all
python tools/benchmarks.py verify-archives
```

Archive construction uses stable path ordering, fixed timestamps, fixed permissions, and excludes local scripts, caches, `.DS_Store`, and SQLite WAL/SHM files. Rebuilding unchanged inputs must produce the same SHA-256.

After rebuilding, upload the changed archives to the Hugging Face dataset
declared in `manifest.json` and commit the refreshed manifest in the same
change. Ordinary CI validates the manifest and any local archives without
downloading the payloads:

```bash
python tools/benchmarks.py verify-pointers
python -m unittest tests.test_benchmarks -v
```

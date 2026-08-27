# Contributing to SqurveBridge

SqurveBridge is built on the original Squrve modular runtime. Contributions
must preserve reproducibility, evidence lineage, and the distinction between the
upstream runtime and SqurveBridge's integration/evaluation layer.

## Core Rules

- Reconstruct community methods through native Squrve Actors; do not vendor or
  execute candidate repositories as opaque dependencies.
- Keep benchmark payloads, credentials, local artifacts, archives, and media
  exports out of Git unless the release contract explicitly distributes them.
- Prefer adapters and registration over Engine, Router, DataLoader, or Evaluator
  changes.
- Isolate method development in a feature branch or worktree.
- Back benchmark claims with the exact config and recorded run artifacts.

## Pull Request Gate

```bash
uv run python tools/release_check.py --skip-history
cd demo-app && npm ci && npm run build
```

Changes to the two distributed benchmark packages must update the package
manifest and must pass `python tools/benchmarks.py verify-archives`. Do not commit
expanded benchmark directories or add another ZIP payload without an explicit
distribution and license review.

Maintainers preparing a release should have `uv` and Node.js 22.19+ available,
download the benchmark payloads (`uv run python tools/benchmarks.py download all`),
and run:

```bash
uv sync --python 3.11
uv build
uv run python tools/release_check.py --full
```

Follow [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md). Report security problems through
[SECURITY.md](SECURITY.md), not a public issue.

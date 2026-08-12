# Changelog

All notable changes to SqurveBridge are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versions are Git
tags on `main`, and the tag matching the published paper is archived for a
citable DOI (see `CITATION.cff`).

## [Unreleased]

### Added

- Iterative AI review loop for Meta-Evo: candidate change plans, patches, and
  reports pass a bounded review -> findings -> revise cycle with a
  deterministic ledger before any evaluation budget is spent
  (`reproduce/evolve/review.py`, `tools/evolve_review.py`,
  `tools/evolve_status.py`).
- Interactive SQL query workspace in the Demo, replacing the full-flow
  evidence workspaces.
- Sandboxed smoke tests for the Claude Code / Codex symlink harness
  installer (`tests/test_harness_install.py`).
- Weekly scheduled CI run covering the full suite and benchmark package
  integrity.

### Changed

- The embedded Pi runtime is consumed as the pinned npm SDK
  `@earendil-works/pi-coding-agent` declared in `demo/package.json`; the
  vendored `pi/` source tree is gone and scan tooling no longer carries
  vendored-path exemptions.
- Evaluation restructured into registry-driven packages under
  `reproduce/eval/`, and the Meta-Evo engine moved to `reproduce/evolve/`
  with a baseline-centered search strategy (cumulative action chains,
  strictly positive promotion, experience warm-start).
- README leads with a pinned 30-minute reproduce path and documents the
  three interchangeable agent runtimes (Embedded Pi, Claude Code, Codex).
- CI pins the single reproduction environment (Python 3.11, Node 22.19) and
  cancels superseded pull-request runs; dependabot updates are grouped into
  one monthly PR per ecosystem.

### Fixed

- Publication completeness is enforced at evidence-bundle export.
- The Pi bridge exits quietly when the parent closes the event pipe instead
  of crashing, and legacy `/name` skill shortcuts now cover every discovered
  skill.

## [0.1.0]

Initial public release: Squrve-native method integration (C3SQL, DIN-SQL,
FinSQL and more), benchmark contracts with checksummed packages, reproduce
configs with four-layer evidence, the embedded Pi agent Demo, Hugging Face
Space deployment, and the deterministic release gate.

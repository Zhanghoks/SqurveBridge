# Evolution Artifact Contract

All evolution evidence is stored under `artifacts/evolve/`.

Directory skeleton: `templates/evolution/artifact-layout.md`.

Global file:

- `artifacts/evolve/evolution-memory.md`: cross-run markdown memory of success and failure patterns

Per-run directory:

- `evolve-state.json`
- `process-events.jsonl`
- `artifact-manifest.json`
- `progress.md`
- `baseline-summary.md`
- `meta-evo-input.json`
- `weakness_profile.md`
- `weakness-profile.json`
- `weakness-analysis.md`
- `journal.json`
- `experience.md`
- `best-node.md`
- `comparison-report.json`
- `comparison-report.md`
- `nodes/`

Each node directory contains:

- `node.json`
- `change-plan.md`
- `patch.diff`
- `run-command.sh`
- `attempts/<stage>-<ordinal>/command.json`
- `attempts/<stage>-<ordinal>/stdout.txt`
- `attempts/<stage>-<ordinal>/stderr.txt`
- `attempts/<stage>-<ordinal>/scores.json`
- `attempts/<stage>-<ordinal>/status.json`
- `scores.smoke50.json`
- `scores.bounded200.json`
- `scores.full.json`
- `evaluator-report.md`
- `delta.json`
- `status.json`

Ownership:

- `evolve-state.json` is the current run-control state and resume pointer.
- `journal.json` is the node/search evidence ledger.
- `process-events.jsonl` is append-only process history.
- `artifact-manifest.json` indexes durable artifacts with fingerprints, producers, consumers, and lineage.
- `progress.md` is a derived human summary and must not be used as a fact source.

Missing optional files must be explained by node status. For example, a `buggy` node may have no bounded scores but must still have `status.json` with the failure reason.

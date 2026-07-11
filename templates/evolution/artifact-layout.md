# Evolution Artifact Layout — <evolve_slug>

```text
artifacts/evolve/<evolve_slug>/
├── evolve-state.json
├── process-events.jsonl
├── artifact-manifest.json
├── progress.md
├── baseline-summary.md
├── meta-evo-input.json
├── weakness_profile.md
├── weakness-profile.json
├── weakness-analysis.md
├── journal.json
├── experience.md
├── best-node.md
├── comparison-report.json
├── comparison-report.md
└── nodes/
    └── <node_id>/
        ├── node.json
        ├── change-plan.md
        ├── patch.diff
        ├── run-command.sh
        ├── attempts/
        │   └── <stage>-<ordinal>/
        │       ├── command.json
        │       ├── stdout.txt
        │       ├── stderr.txt
        │       ├── scores.json
        │       └── status.json
        ├── scores.smoke50.json
        ├── scores.bounded200.json
        ├── scores.full.json
        ├── evaluator-report.md
        ├── delta.json
        └── status.json
```

`evolve-state.json` is the current run-control state. `journal.json` is the node/search evidence ledger. `artifact-manifest.json` indexes durable files and fingerprints. `process-events.jsonl` is append-only process history. `progress.md` is a human-readable summary derived from those machine artifacts and is not a fact source.

Missing optional files must be explained in `status.json`.

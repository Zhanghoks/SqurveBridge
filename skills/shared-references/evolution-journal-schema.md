# Evolution Journal Schema

`artifacts/evolve/<evolve_slug>/journal.json` is the node/search evidence ledger.

Use `evolve-state.json` for the current run-control phase and resume pointer. Use `journal.json` for nodes, scores, best-node evidence, recommendation, and stagnation. A valid transition must be reconstructable from `evolve-state.json`, `journal.json`, `process-events.jsonl`, and `artifact-manifest.json`.

Copy/fill skeleton: `templates/evolution/journal.json`.

Required top-level fields:

- `evolve_slug`
- `baseline_run_slug`
- `method`
- `benchmark`
- `policy`
- `round`
- `rounds_completed`
- `nodes`
- `best_node`
- `recommendation`
- `stagnation`

`nodes` contains serialized `EvolutionNode` records. `best_node` is recomputed from evaluated node fitness. `stagnation.branch_stagnant` lists branch ids with no recent improvement, `stagnation.global_stagnant` marks global plateau, and `stagnation.dry_rounds` counts repeated dry rounds.

The journal must be sufficient to locate every node directory, patch, command, score file, delta, and status without relying on chat history. Cross-run file lineage and fingerprints are indexed in `artifact-manifest.json`.

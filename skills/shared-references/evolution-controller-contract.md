# Evolution Controller Contract

Meta-Evo is the only public evolution-controller entry. It must not introduce a second skill, engine, runner, or artifact flow.

## Layer Boundary

- `skills/Meta-Evo/SKILL.md` frontmatter registers `/meta-evo`; its body handles user interaction, workflow sequencing, and human review.
- `tools/` exposes thin deterministic wrappers only.
- `reproduce/metrics/mcts/orchestrator.py` owns MCTS search stages and delegates run-level phase transitions to the evolution state machine.
- `reproduce/metrics/evolution_pkg/` owns deterministic state, process artifacts, node, journal, budget, fitness, sampling, experience, and artifact helpers.
- `artifacts/evolve/` is the artifact source for every evolution run.

## State And Evidence Split

- `evolve-state.json`: current run-control pointer, phase, active stage, current node, human gate, failure, and last transition.
- `journal.json`: append/history evidence ledger for nodes, scores, best node, recommendation, and stagnation.
- `process-events.jsonl`: append-only process history for transitions, commands, artifacts, decisions, gates, and failures.
- `artifact-manifest.json`: file index with producer/consumer lineage and fingerprints.
- `progress.md`: human-readable summary derived from machine artifacts; never use it as a fact source.

A phase is valid only when `evolve-state.json`, `journal.json`, and the manifest agree. If they disagree, the controller must fail closed instead of inferring from chat history.

## Default Loop

The default lightweight loop is:

```text
baseline scores -> weakness profile -> candidate nodes -> smoke50 -> bounded200 -> full best only -> user review
```

The loop contract is documented in `docs/meta-evo-loop.md` and the broader architecture in `docs/evolution-harness-design.md`.

## Human Gates

Scope B changes may be proposed and smoke-tested automatically. Scope C changes that touch `core/**`, evaluator, router, DataLoader, database backends, or shared Engine/runtime behavior require explicit user confirmation before patch application.

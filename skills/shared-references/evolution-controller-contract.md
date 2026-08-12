# Evolution Controller Contract

Meta-Evo is the only public evolution-controller entry. It must not introduce a second skill, engine, runner, or artifact flow.

## Layer Boundary

- `skills/Meta-Evo/SKILL.md` frontmatter registers `/meta-evo`; its body handles user interaction, workflow sequencing, and human review.
- `skills/evolve-review/SKILL.md` is the internal AI review-loop protocol (roles, rubric, loop rhythm); its deterministic ledger and verdict live in `reproduce/evolve/review.py` behind `tools/evolve_review.py`.
- `tools/` exposes thin deterministic wrappers only.
- `reproduce/evolve/mcts/orchestrator.py` owns MCTS search stages and delegates run-level phase transitions to the evolution state machine.
- `reproduce/evolve/` owns deterministic state, process artifacts, node, journal, budget, fitness, sampling, experience, and artifact helpers.
- `artifacts/evolve/` is the artifact source for every evolution run.

## State And Evidence Split

- `evolve-state.json`: current run-control pointer, phase, active stage, current node, human gate, failure, and last transition.
- `journal.json`: append/history evidence ledger for nodes, scores, best node, recommendation, and stagnation.
- `review-state.json` (per review target, under `reviews/<target>/` or `nodes/<node_id>/review/`): the review-loop ledger and verdict (`evolution-review-loop.md`).
- `process-events.jsonl`: append-only process history for transitions, commands, artifacts, decisions, gates, and failures.
- `artifact-manifest.json`: file index with producer/consumer lineage and fingerprints.
- `progress.md`: human-readable summary derived from machine artifacts; never use it as a fact source.

A phase is valid only when `evolve-state.json`, `journal.json`, and the manifest agree. If they disagree, the controller must fail closed instead of inferring from chat history.

## Resume Protocol

`python3 tools/evolve_status.py --evolve-dir artifacts/evolve/<slug>` is the
single resume entry (`state_machine.next_step`). It returns the phase, the
review-gate map, consistency, and one ready-to-run `next_command`. Agents must
resume from this output, never from chat memory. When candidate nodes lack an
approved review, the resume action is `run_candidate_review` and the search
stages are withheld.

## Review-Gate Phases

The state machine records the review loop with two optional phases:
`candidates_reviewed` (between `actions_generated` and `smoke_running`) and
`report_reviewed` (between `full_confirming` and `review_pending`). The direct
legacy transitions remain valid so pre-review runs still resume, but new runs
must record the gated path.

## Default Loop

The default lightweight loop is:

```text
baseline scores -> weakness profile -> [review loop] -> candidate nodes -> [review loop]
    -> smoke50 -> bounded200 -> full best only -> [review loop] -> user review
```

Each `[review loop]` is the iterative AI review gate defined in
`evolution-review-loop.md` and executed via `skills/evolve-review/SKILL.md`:
review -> findings -> revise -> re-review until the deterministic verdict in
`reproduce/evolve/review.py` returns `approve`, or `escalate` hands the
target to the human gate. Evaluation budget is only spent on approved
candidates.

The loop contract is documented in `docs/design/meta-evo-loop.md` and the broader architecture in `docs/design/evolution-harness-design.md`.

## Human Gates

Scope B changes may be proposed and smoke-tested automatically. Scope C changes that touch `core/**`, evaluator, router, DataLoader, database backends, or shared Engine/runtime behavior require explicit user confirmation before patch application.

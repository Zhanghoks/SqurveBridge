# Evolution Harness Design

This document describes the deterministic engine underneath the Meta-Evo loop
(`docs/meta-evo-loop.md`): module responsibilities, the search algorithm, the
state machine, and every tunable policy parameter. All components are plain
Python with no LLM dependency, so the harness is unit-testable end to end
(`tests/test_evolution_search.py`, `tests/test_evolution_strategy.py`).

## Module Map

| Module | Responsibility |
|---|---|
| `reproduce/evolve/mcts/orchestrator.py` | Search loop (`run_search`), stage funnel (`run_bounded_funnel`), CLI |
| `reproduce/evolve/mcts/tree.py` | UCT tree, shared action bandit (`ActionStats`), warm start |
| `reproduce/evolve/mcts/expand.py` | `Action` schema, executable filtering, chain composition, heuristic templates |
| `reproduce/evolve/mcts/rollout.py` | Git-worktree rollouts, patch application, verdicts |
| `reproduce/evolve/fitness.py` | Multi-objective fitness and baseline-centered improvement |
| `reproduce/evolve/budget.py` | Promotion gates between smoke, bounded, and full stages |
| `reproduce/evolve/journal.py` | Evidence ledger, best-node tracking, stagnation detection |
| `reproduce/evolve/review.py` | Review-loop ledger and deterministic verdict (`tools/evolve_review.py` CLI) |
| `reproduce/evolve/state_machine.py` | Run phases, resume logic, Scope C gating |
| `reproduce/evolve/experience.py` | Markdown memory read/write, prior extraction from journals |
| `reproduce/evolve/artifacts.py` | `artifacts/evolve/` layout, review recording, reports |

## Search Algorithm

`run_search` runs UCT over candidate actions with four strategy properties:

1. **One evaluation per node.** Rollout results are memoized per action
   chain. A memo hit never re-backpropagates; repeat visits either extend the
   tree or close exhausted subtrees. Tree statistics therefore count
   informative evaluations, and the `evaluations` field of the result is the
   true budget spent.
2. **Cumulative action chains.** With `cumulative_updates` (default for the
   funnel and CLI), a rollout evaluates the composite of the whole
   root-to-leaf chain: patches are merged in chain order, scope and risk take
   the most severe value, and the composite is recorded in the journal node
   so later stages replay the full change. Chains are capped at
   `max_chain_depth` and may only stack actions that individually earned a
   CONTINUE verdict.
3. **Progressive widening with exploration decay.** Node width grows with
   `ceil(sqrt(visits))` (capped at 4) and the UCT exploration constant decays
   after 50% budget, shifting from exploration to exploitation.
4. **Stagnation-aware selection.** Branches flagged stagnant in the journal
   are skipped during descent while non-stagnant alternatives exist; closed
   subtrees are never re-selected.

### Reward

```text
reward = fitness_from_scores(candidate, delta) - fitness_from_scores(baseline)
       + target_bonus_weight * delta(target_metric)
```

`fitness_from_scores` combines EX, EM, VES, hard-slice EX, relative cost and
latency deltas, and the per-sample regression rate under `DEFAULT_WEIGHTS`
(overridable via `fitness_weights`). Subtracting the baseline fitness makes a
no-op candidate score exactly 0. `R_INVALID = -2.0` sits below the worst
achievable valid improvement (about -1.15), so crashed rollouts always rank
last among evaluated candidates.

### Promotion

`smoke_gate_promote` / `bounded_eval_promote` rank passing nodes by fitness
and require `fitness > 0`:

- DRY no-op candidates (reward 0) never advance to bounded or full stages.
- Cost-only improvements (flat EX, positive reward from the cost term)
  remain eligible.
- STOP and REGRESSION rollouts are recorded with status `buggy` and are
  excluded before ranking.

### Experience Warm Start

`warm_start_action_stats` seeds the shared action bandit from prior journals
(`experience.action_priors_from_journal`):

- Each historical evaluation contributes `discount` pseudo-visits (default
  0.3) with its recorded fitness.
- Failed priors (rolled back, buggy, REGRESSION/STOP verdicts) contribute a
  negative reward (`R_INVALID / 2`) instead — down-weighted, not excluded.
- Untried actions keep an infinite UCT score, so fresh candidates are always
  sampled before previously failed ones.

### Stagnation

`journal.global_stagnant` compares the best fitness of the last 4 scored
nodes against the best before them. The orchestrator invokes it once per
fresh evaluation (never on memo hits), so `dry_rounds` counts informative
rollouts. The search stops after `dry_round_limit` consecutive dry
evaluations (default 4). `branch_stagnant` feeds the selection pruning
described above.

## Rollout Isolation

`run_action_rollout` creates a detached git worktree, applies the (possibly
composite) action's patches, runs the stage command, and reads the resulting
`scores.json`. Patch conflicts — including conflicts between chained actions
— return a STOP verdict for that candidate instead of raising. Scope C paths
require `allow_scope_c=True`, which only the human gate grants. Worktrees are
always removed, pass or fail.

## State Machine

`evolution_pkg/state_machine.py` owns run phases
(`initialized -> ... -> actions_generated -> candidates_reviewed ->
smoke_running -> smoke_promoted -> bounded_running -> bounded_promoted ->
full_confirming -> report_reviewed -> review_pending ->
accepted/continued/rolled_back`), resume actions after interruption, and
Scope C classification. `candidates_reviewed` and `report_reviewed` record
the AI review gates (`docs/meta-evo-loop.md`); the ungated legacy transitions
remain valid for old runs. `next_step(evolve_dir)` — exposed as
`tools/evolve_status.py` — combines phase, review gates, consistency, and a
ready-to-run next command into one status object, and withholds search stages
while any candidate lacks an approved review.
`run_bounded_funnel` delegates every phase transition to it; a phase is valid
only when `evolve-state.json`, `journal.json`, and the artifact manifest
agree (see `skills/shared-references/evolution-controller-contract.md`).

## Policy Configuration

`reproduce/configs/evolution/bounded_search_default.json` is the default
policy consumed via `--policy-config`:

| Key | Default | Meaning |
|---|---|---|
| `dry_round_limit` | 4 | Fresh non-improving evaluations before stopping |
| `stagnation_window` | 4 | Recent scored nodes compared against the earlier best |
| `cumulative_updates` | true | Evaluate root-to-leaf chains (disable with `--no-cumulative`) |
| `max_chain_depth` | 3 | Maximum stacked actions per chain |
| `target_bonus_weight` | 0.15 | Proportional bonus on the action's declared target metric |
| `promotion.smoke_top_k` | 2 | Candidates promoted from smoke to bounded |
| `promotion.bounded_top_k` | 1 | Candidates promoted from bounded to full |
| `experience.discount` | 0.3 | Pseudo-count weight per historical evaluation |
| `fitness_weights` | see file | Multi-objective fitness weights |
| `env` | see file | Environment applied to rollout commands |

CLI equivalents: `--rollouts`, `--baseline-scores`, `--prior-journal`
(repeatable), `--max-chain-depth`, `--no-cumulative`, `--stage`.

## Testing

- `tests/test_evolution_search.py`: fitness terms, multi-objective reward
  ordering, failed-rollout penalties, memoization, budget usage.
- `tests/test_evolution_strategy.py`: baseline-centered rewards and the
  target bonus, promotion gating (no-op exclusion, cost-only inclusion),
  executable-pool filtering, chain composition/verification/depth caps,
  memo statistics, experience priors and warm-start ordering, review-to-memory
  wiring, dry-round semantics, and stagnant-branch pruning.

All tests drive `run_search` with simulated evaluators; no real evaluation
runs are required.

# Meta-Evo Loop

Meta-Evo is SqurveBridge's bounded, human-gated evolution loop. It turns a
completed evaluation run into diagnosed weaknesses, searches a small space of
candidate changes under an explicit budget, and asks a human to accept or
roll back the best candidate. It is deliberately **not** an autonomous
self-modification system: every change that lands in a runnable configuration
passes a human review gate.

## Loop Overview

```text
baseline scores -> weakness profile -> [review loop] -> candidate nodes -> [review loop]
    -> smoke50 -> bounded200 -> full best only -> [review loop] -> user review
```

| Stage | Input | Owner | Output |
|---|---|---|---|
| Diagnose | `scores.json` | `reproduce/metrics/profile.py`, `evolution.py` | `weakness_profile.md`, `meta-evo-input.json` |
| Candidates | weakness profile | Meta-Evo agent (`skills/Meta-Evo/SKILL.md`) | `action-pool.json` with concrete patches |
| Review loop | profile / candidate / report | `skills/evolve-review/SKILL.md` + `reproduce/evolve/review.py` | `review-state.json` with verdict `approve`/`revise`/`escalate` |
| Smoke search | action pool, baseline scores | `reproduce/evolve/mcts/orchestrator.py` | journal nodes, `mcts-tree.smoke.json` |
| Bounded search | smoke-promoted actions | same orchestrator | `mcts-tree.bounded.json`, best node |
| Full confirmation | best node only | same orchestrator | `scores.full.json`, `comparison-report.md` |
| Review | comparison report | human | accept / continue / rollback |
| Memory | review outcome | `evolution_pkg/artifacts.record_user_review` | `experience.md`, `evolution-memory.md` |

The stage budgets (50-sample smoke slices, 200-sample bounded slices, full
confirmation for the single best node) are defined in
`skills/shared-references/bounded-search-policy.md`; search-strategy
parameters live in `reproduce/configs/evolution/bounded_search_default.json`.

## Iterative Review Loop

Before any evaluation budget is spent — and before anything reaches a human —
the relevant artifact passes an iterative AI review loop
(`skills/evolve-review/SKILL.md`, contract in
`skills/shared-references/evolution-review-loop.md`):

- A critic pass (fresh subagent, or an adversarial re-read from disk)
  raises structured findings (`blocker`/`major`/`minor`/`nit`) against a
  per-artifact rubric; the author revises and resolves them; the loop
  repeats.
- The verdict is deterministic (`reproduce/evolve/review.py`): `approve`
  requires zero open blocking findings plus a clean re-review round;
  `escalate` fires when `max_rounds` (default 5) is exhausted, handing the
  target and its open findings to the human gate. The loop is bounded by
  construction.
- `review-state.json` is the only fact source for a review; "reviewed in
  chat" does not count. Smoke rollouts may only start for candidates whose
  verdict is `approve`.

## Reward: Improvement over Baseline

Candidate rollouts are scored with a baseline-centered reward:

```text
reward = fitness(candidate) - fitness(baseline) + target_bonus
```

- `fitness` is the multi-objective score in
  `reproduce/evolve/fitness.py` (EX, EM, VES, hard-slice EX,
  cost delta, latency delta, per-sample regression rate).
- A candidate that reproduces the baseline exactly earns `0` and is **not**
  promoted; promotion requires a strictly positive reward
  (`evolution_pkg/budget.py`). Cost-only improvements (same EX, cheaper) stay
  eligible.
- `target_bonus = target_bonus_weight * delta(target_metric)` credits an
  action in proportion to how much it actually moved the metric it declared
  to fix, tying the search back to the weakness profile.
- Crashed or STOP rollouts earn `R_INVALID`, which is strictly below the
  worst achievable valid improvement, so a broken candidate can never outrank
  one that ran and merely regressed.

## Action Chains

The search composes changes, not just single edits. In cumulative mode
(default for the funnel and CLI):

- A rollout applies the whole root-to-leaf action chain in a disposable git
  worktree, capped at `max_chain_depth` (default 3) stacked actions.
- Only actions that individually earned a CONTINUE verdict may be stacked
  onto a chain; unverified or DRY actions never get combined blindly.
- Conflicting patches on a chain produce a STOP verdict for that candidate
  instead of crashing the harness.
- Journal nodes record the composite action that was actually evaluated, so
  bounded and full stages replay the full change set.

## Experience Memory

Review outcomes feed the next run:

- `record_user_review` appends accepted runs under **Successful Patterns**
  and rollbacks under **Failed Patterns** in `artifacts/evolve/evolution-memory.md`,
  with machine-readable `- Action: <id>` anchors.
- The next search can warm-start its action bandit from past journals
  (`run_search(prior_journals=...)` or `--prior-journal`): each historical
  evaluation contributes discounted pseudo-counts (default discount 0.3).
  Failed patterns are down-weighted, not excluded — they remain selectable
  when fresh evidence favors them, and untried actions always rank ahead of
  previously failed ones.

## Stopping and Budget Discipline

- Rollout results are memoized per action chain; a memo hit never
  re-backpropagates, so tree statistics count informative evaluations only.
- `dry_rounds` increments once per fresh evaluation that fails to improve the
  global best; the search stops after `dry_round_limit` (default 4) dry
  evaluations.
- Branches flagged stagnant in the journal are pruned from UCT selection
  while alternatives exist.
- Actions with neither patches nor a run command are filtered out at
  pool-loading time (they would only re-measure the baseline). The heuristic
  candidates from `expand.generate_actions` are outlines for the agent to
  fill in, not executable actions.

## Human Gates

- Scope B changes (prompts, configs, adapters) may be proposed and
  smoke-tested automatically.
- Scope C changes (`core/**`, evaluator, router, DataLoader, database
  backends, shared Engine behavior) require explicit user confirmation before
  any patch is applied (`rollout.apply_action` enforces this).
- Nothing is written back to a runnable configuration without an explicit
  `accept` review outcome.

## Current Limitations (Future Work)

- Candidate patches are authored by the Meta-Evo agent; there is no automated
  patch synthesis.
- Experience warm-starts operate on action identifiers; semantic matching of
  similar-but-renamed changes is future work.
- Accepted changes are applied by the agent under review; there is no
  unattended config write-back service, by design.

See `docs/design/evolution-harness-design.md` for the module-level architecture and
`skills/shared-references/evolution-controller-contract.md` for the layer
boundaries.

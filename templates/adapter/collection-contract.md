# Process-Signal Collection Contract (v2)

What every adapted method must leave behind during a run so the L5 process
layer can evaluate stage-level behavior. The reproduce runtime captures most
of this automatically; adapters only need to respect the naming rules.

## Cross-stage SQL snapshots

- Whenever an actor overwrites `pred_sql`, the previous value is persisted as
  `pred_sql_before_<stage>` by `reproduce.metrics.snapshots.capture_pred_sql_snapshot`,
  where `<stage>` is the actor's `name` (falling back to its class name).
- Adapters must give pipeline actors stable, stage-identifying names so the
  snapshot key matches the task id declared in the reproduce config.
- Readers must resolve snapshot keys through
  `reproduce.eval.sample.process.find_before_key(row, stage_id=..., needles=...)`.
  Raw substring matching against row keys is the deprecated legacy path and
  will be removed once recorded rows predating this contract age out.

## Runtime signals (captured automatically)

- `_actor_trace`: per-actor structured trace (elapsed, row delta, error) via
  `core/trace.py`; `stage_name` must carry the task id.
- `_act_elapsed_s`: per-sample actor wall time (feeds `aggregate.latency`).
- Token usage: logged with tags `sample:<instance_id>|<task_id>` so cost is
  attributable per sample and per stage.
- Stage checkpoints: every task with `eval_type` declared writes its
  `dataset_save_path` checkpoint; stage metrics (recall/precision/...) are
  recomputed offline from these checkpoints, never live.

## Run gate events (derived, no new hooks)

Every evaluated sample yields an ordered five-gate outcome with early
termination, derived from already-captured fields by
`reproduce.eval.sample.process.gate_outcome`:

1. `parseable` — a non-empty `pred_sql` was produced
2. `timely` — execution was not killed by a timeout (`exec_error` text)
3. `executable` — `exec_error` is empty
4. `correct` — `ex == 1`
5. `efficient` — only with an explicit latency budget; `act_elapsed_s <= budget`

Per-run survival rates land in `aggregate.funnel.gate`; the first failed gate
per sample answers "where did this run die".

## Canonical roles

Process metrics compare methods through the Squrve task taxonomy:

| task_type | canonical role |
| --- | --- |
| ReduceTask, ParseTask | linking |
| GenerateTask, ScaleTask | generation |
| OptimizeTask | refinement |
| SelectTask | selection |
| DecomposeTask | decomposition |

A method-specific `task_id` may be anything; its `task_type` decides which
L5 metrics apply.

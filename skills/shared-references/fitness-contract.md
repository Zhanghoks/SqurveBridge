# Fitness Contract

Fitness is deterministic and lives in `reproduce/evolve/fitness.py`.

Inputs may include:

- `ex`
- `em`
- `ves`
- `hard_slice_score`
- `cost_delta`
- `latency_delta`
- `regression_rate`

Default behavior favors EX, rewards hard-slice gains, and penalizes cost, latency, and regressions. The output is a single numeric score used for smoke and bounded promotion. Fitness does not call LLMs and must be reproducible from stored scores and delta files.

`fitness_from_scores` reads quality terms from a score bundle and the remaining
terms from a `compare_scores` delta against the baseline bundle. Without that
delta the cost, latency, and regression terms stay at zero, so a search that
omits the baseline optimizes EX alone.

`cost_delta` and `latency_delta` are fractions of the baseline, not absolute
token counts or seconds; the raw delta is divided by the baseline value before
weighting so the bonus cannot saturate on a real run.

`R_INVALID` is the reward for a candidate that produced no usable evaluation.
It sits below the worst achievable valid *improvement* (worst candidate
fitness minus best baseline fitness) so a crashed rollout can never outrank a
candidate that ran and merely regressed.

The MCTS loop backpropagates a baseline-centered reward:
`improvement_from_scores` returns `fitness(candidate) - fitness(baseline)`
under the same weights, so a no-op candidate scores exactly 0. An optional
target bonus (`target_bonus_weight * delta(target_metric)`, default weight
0.15) credits an action in proportion to how much it moved the metric it
declared to fix. Promotion requires a strictly positive reward, which keeps
DRY no-op candidates out of bounded and full stages while cost-only
improvements stay eligible. The raw target metric is reported separately in
the search verdict. Absolute fitness is still recorded per node as
`metadata.fitness_abs` for reporting.

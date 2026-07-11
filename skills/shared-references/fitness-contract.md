# Fitness Contract

Fitness is deterministic and lives in `reproduce/metrics/evolution_pkg/fitness.py`.

Inputs may include:

- `ex`
- `em`
- `ves`
- `hard_slice_score`
- `cost_delta`
- `latency_delta`
- `regression_rate`

Default behavior favors EX, rewards hard-slice gains, and penalizes cost, latency, and regressions. The output is a single numeric score used for smoke and bounded promotion. Fitness does not call LLMs and must be reproducible from stored scores and delta files.

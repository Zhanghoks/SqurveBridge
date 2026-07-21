# Runtime workspace

This directory holds **local runtime data only**. Nothing here is published
except this README.

```text
workspace/
  sessions/
    evaluations/   # Demo evaluation jobs and score-bundles
    runtime/       # demo/start.sh pid and log files
    pi-agent/      # embedded Pi agent state
  runs/            # reproduce intermediate outputs and checkpoints
  artifacts/       # CLI score bundles, eval-store.sqlite, evolve
  uploads/         # user-uploaded databases and temporary demo data
```

Override the root with `SQURVE_WORKSPACE_DIR` (HF Space defaults to
`/app/workspace`; attach persistent storage at `/data/workspace` when needed).

Published evidence lives under `evidence/reported-results/`. Benchmark packages
live under `benchmarks/packages/`. Never commit API keys, uploaded databases,
or score-bundle contents from this tree.

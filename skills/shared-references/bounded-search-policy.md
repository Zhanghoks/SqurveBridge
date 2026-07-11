# Bounded Search Policy

Evolution uses a three-stage funnel:

1. Smoke gate: 50 samples, all initial candidates, promote top 2 passing candidates by fitness.
2. Bounded evaluation: 200 samples, only smoke-promoted candidates, promote top 1 by fitness.
3. Full confirmation: full reproduce run, best node only.

Smoke and bounded runs should set `SQURVE_EVAL_SCOPE=smoke`, `SQURVE_EVAL_SAMPLE_LIMIT`, `SQURVE_EVAL_OUTPUT_DIR`, and speed flags such as `SQURVE_EVAL_SKIP_TOKEN=1` when appropriate.

Full confirmation must not use smoke scope. It compares the best candidate against baseline with `SQURVE_EVAL_BASELINE_SCORES`.

Dry-round termination: when global stagnation repeats until `dry_rounds >= 2`, stop search and report the best available node.

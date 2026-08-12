# Bounded Search Policy

Evolution uses a three-stage funnel:

0. Review gate (precondition): only candidates whose `review/review-state.json` verdict is `approve` may enter the funnel (`evolution-review-loop.md`); `tools/evolve_status.py` reports `run_candidate_review` until this holds.
1. Smoke gate: 50 samples, all review-approved candidates, promote top 2 passing candidates by fitness.
2. Bounded evaluation: 200 samples, only smoke-promoted candidates, promote top 1 by fitness.
3. Full confirmation: full reproduce run, best node only.

Smoke and bounded runs should set `SQURVE_EVAL_SCOPE=smoke`, `SQURVE_EVAL_SAMPLE_LIMIT`, `SQURVE_EVAL_OUTPUT_DIR`, and speed flags such as `SQURVE_EVAL_SKIP_TOKEN=1` when appropriate.

Full confirmation must not use smoke scope. It compares the best candidate against baseline with `SQURVE_EVAL_BASELINE_SCORES`.

Dry-round termination: `dry_rounds` counts fresh (non-memoized) evaluations that fail to improve the global best; when `dry_rounds >= 4` (policy `dry_round_limit`), stop search and report the best available node.

# Reproducibility and Recorded Evidence

SqurveBridge treats a reproduction configuration and its persisted outputs as the
source of truth. Terminal output and chat history are not evaluation evidence.

## Reproduction Unit

One run must identify:

1. method, benchmark, and split;
2. sample scope and random seed;
3. provider, model, and workflow configuration;
4. evaluator and metric definitions; and
5. the output directory containing the resulting evidence.

Do not compare runs that differ on these fields without labeling the difference.

## Configuration Validation

Run deterministic checks before spending inference tokens:

```bash
python tools/verify.py reproduce-contract --path reproduce/configs/spider/c3sql.json
python tools/verify.py reproduce-contract --path reproduce/configs/bird/e-sql-smoke.json
```

## Bundled Configurations

| Configuration | Role | Data source |
| --- | --- | --- |
| `spider/c3sql` | C3SQL three-stage workflow | `spider:dev:200` |
| `bird/e-sql-smoke` | E-SQL BIRD example | `bird:dev:` |

Inspect the JSON before running. Provider calls incur cost, and parallel settings
can increase request volume.

```bash
cp .env.example .env
python reproduce/run.py spider c3sql
python reproduce/run.py bird e-sql-smoke
```

## Four-Layer Score Bundle

The unified evaluation system records evidence at four diagnostic layers:

| Layer | Evidence | Interpretation |
| --- | --- | --- |
| L1 SQL Quality | EX, EM, SF1, VES, RVES when configured | Correctness and valid efficiency |
| L2 Runtime Cost | Token usage, mean/p95 Actor latency | Operational cost of the workflow |
| L3 Structure | SQL-component CF1 and feature deltas | Clause-level strengths and weaknesses |
| L4 Errors | Deterministic attribution labels | Concrete diagnostic categories for failed samples |

Not every configuration enables every metric. Missing evidence must remain missing;
it must not be reconstructed from unrelated runs.

## Persisted Outputs

Depending on the run mode and configuration, outputs include:

| Artifact | Purpose |
| --- | --- |
| `scores.json` | Aggregate score bundle and diagnostic summaries |
| stage dataset snapshots | Inputs and outputs at Actor boundaries |
| workflow trace | Stage timing, row changes, and errors |
| detailed report | Human-readable evaluation evidence |
| evaluation store | Queryable sample- and run-level records |

Runtime files are written below ignored `files/` and `artifacts/` directories. A
paper result is reproducible only when its configuration and concrete run artifacts
are retained together.

## Sampling

The reproduction configuration controls the dataset source. Optional evaluation
sampling uses:

- `SQURVE_EVAL_SAMPLE_LIMIT`
- `SQURVE_EVAL_SAMPLE_MODE`
- `SQURVE_EVAL_SAMPLE_SEED`

Record all three values with any reported slice. A smoke or bounded run is not a
full-split result.

## Evidence Boundaries

- **Source-aligned reproduction** requires the same method, origin benchmark,
  split, model, and evaluation protocol as the source result.
- **Cross-benchmark execution** shows that an integrated method runs on another
  normalized benchmark; it is not source alignment.
- **Metric-guided loop evidence** requires a baseline, candidate checkpoints,
  accept/reject decisions, and target plus monitor results.
- Never merge values from separate runs into a single result row without an
  explicit aggregation rule.

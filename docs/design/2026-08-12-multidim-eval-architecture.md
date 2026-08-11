# Multi-Dimensional Evaluation Architecture

Status: implemented (migration steps 1-4; legacy `reproduce/metrics/` facades
retained until external callers migrate)
Date: 2026-08-12
Scope: `reproduce/eval/`, `reproduce/evolve/`, `reproduce/metrics/` (facades),
`tools/evidence.py`, `templates/adapter/collection-contract.md`

Implementation notes against the original proposal:

- The evolution engine additionally moved out of `reproduce/metrics/` into
  `reproduce/evolve/` (search loop under `evolve/mcts/`), with
  `compare_scores` landing in `reproduce/eval/bundle/compare.py`.
- The eval-store schema v2 uses long tables (`sample_metrics`, `sample_meta`,
  opt-in `sample_text`); `sql_features` and `stage_metrics` kept their layout.
- Publication completeness is enforced by `reproduce/eval/views/evidence.py`
  plus unit tests executed by the release gate, rather than a separate gate
  step.

## 1. Motivation

The current evaluation system already collects rich signal but has structural
problems that make "adding one more dimension" expensive and error-prone:

1. Dimensions are hardcoded. `assembly.build_scores` returns a fixed dict of
   eight top-level views; adding a slice touches six files (assembly, report,
   evidence allowlist, eval-store DDL, demo, docs).
2. Slice logic is copied four times with inconsistent metric sets
   (`_by_hardness`, `_by_db_type`, `_by_component_hardness`,
   `feature_slices._slice_stats`). Only 2 of 7 CF1 components appear in
   hardness/db_type slices.
3. The runtime-cost layer is incomplete inside the metrics package: latency is
   captured per sample (`act_elapsed_s`) but never aggregated; the published
   claim of avg/p95 actor latency is computed in the demo layer.
   `_aggregate_token.per_call_p95` is actually a max over per-tag means.
4. Captured-but-unaggregated signals: `sl_recall`, workflow
   `attribution.root_stage`.
5. No uncertainty. `statistical_validity` is a pass-through string; every
   number is a point estimate. Bounded evolution decisions at n=50 need
   intervals to be meaningful.
6. Publication policy is divorced from metric definitions.
   `tools/evidence.py` keeps a hand-maintained allowlist; published bundles
   silently lost cf1/token/hardness, and `token_usage` is allowed but never
   written.
7. `eval_store.samples` is a wide table with six hardcoded metric columns and
   embeds raw question/SQL text.
8. Process-level signals exist twice (`workflow.py` signals vs
   `pipeline_delta.py`) with overlapping field names and no declared source of
   truth; cross-stage SQL snapshots are located by substring-matching key
   names (`_find_before_key`).

## 2. Layer model

L1–L4 keep their existing meaning. Two layers are added.

| Layer | Content | Unit of analysis |
| --- | --- | --- |
| L1 SQL quality | EX, EM, SF1, SC, VES, RVES (+ optional test-suite acc) | final SQL |
| L2 runtime cost | tokens (total/per-stage/per-sample), latency avg/p50/p95, wall time, cost-per-correct | run log |
| L3 structure | 7-component CF1, 16-dim feature delta, `sl_recall` promoted to a first-class metric | SQL pair |
| L4 error attribution | root-cause labels (multi-label with co-occurrence), stage attribution | failed sample |
| **L5 process** | per-canonical-stage quality + run gate funnel | pipeline stage |
| **L6 cross-method** | correctness/time matrix and derived comparative metrics | (query, method) matrix |

### 2.1 L5: process layer

Method-specific `task_id`s map to canonical roles via `task_type`
(ReduceTask/ParseTask/GenerateTask/OptimizeTask/SelectTask/ScaleTask/
DecomposeTask), so process metrics are comparable across methods.

Per-role metrics (aggregated, sliceable):

| Role | Metrics | Existing raw signal |
| --- | --- | --- |
| linking (Reduce/Parse) | schema recall, schema precision (new), fatal-miss rate | `reduce_recall`, `gold_schemas`/`instance_schemas`, `extra_schemas` |
| generation | pass@1, oracle@k, exec-validity rate, candidate diversity | `_sql_stage_signals`, `_scaler_delta` |
| refinement (Optimize) | fix rate, degradation rate, net gain, avg debug turns | `_optimizer_delta` |
| selection | selection accuracy, regret (oracle − selected), missed-correct rate | `_selector_signals` / `_selector_delta` (merge) |
| decomposition | trigger rate, trigger accuracy | `_aggregate_pipeline.decomposer` |
| all roles | tokens, latency per role | token tag `sample:<id>|<step>`, `_act_elapsed_s` |

Two funnel views:

- **Stage survival funnel**: fraction of samples still solvable after each
  canonical role (linking: recall = 1; generation: oracle@k = 1; selection:
  selected_ex = 1). Dual of the existing `bottleneck_distribution`.
- **Run gate funnel** (adapted from arXiv 2602.15564 §4.2.1): parseable
  output → within timeout → SQL executes → result correct → efficiency
  headroom. Recorded per run as ordered gate events with early termination;
  reported as per-gate survival rates. Structural-failure rate (gate 1)
  becomes a standing report column alongside accuracy and time.

### 2.2 L6: cross-method comparative layer

Primary data asset: matrix `(q_k, W_i) -> (Y_i(q_k), t_i(q_k))` where `Y` is
correctness and `t` is latency. Stored in the eval store across runs; no new
collection is required beyond adding latency to stored per-sample rows.

Derived metrics (definitions follow arXiv 2602.15564 §3, App. B/C):

- `EX_dynamic = E_q[max_i Y_i(q)]`, `EX_static = max_i E_q[Y_i(q)]`,
  oracle gap `Δ = EX_dynamic − EX_static` (method complementarity).
- Pairwise disagreement `D_sample(i,j) = mean_k 1{Y_i(q_k) ≠ Y_j(q_k)}` and
  `D_eff(i,j) = mean_k |t_i−t_j|/(t_i+t_j)`; combined `D = (D_sample+D_eff)/2`.
- Empirical difficulty `N(q)` = number of methods solving `q`; per-method
  uniquely-solved count (irreplaceability).
- Efficiency headroom under correctness `Δ_eff(N)` per difficulty stratum.

## 3. Collection contract (during generation)

Existing instrumentation is kept; the contract makes it explicit and fixes
the fragile parts:

1. `core/trace.py record_actor_trace` stays the per-actor event source
   (elapsed, row_delta, error). Requirement: `stage_name` must always be the
   `task_id`.
2. Stage checkpoints (`dataset_save_path`) stay the per-stage dataset source
   evaluated offline by `stage_eval.py`. No LLM calls at evaluation time;
   intermediate candidates are re-executed against the database offline.
3. Cross-stage SQL snapshots use the fixed key `pred_sql_before_<task_id>`.
   Substring guessing (`_find_before_key`, `pipeline_delta._find_key`) is
   removed after a deprecation window. The schema lands in
   `templates/adapter/` so integration skills enforce it at adapter time.
4. Token logging keeps tag format `sample:<instance_id>|<task_id>`.
5. New: run gate events. The runner records the five-gate outcome per sample
   (`gates: [parseable, timeout, executable, correct, efficiency]`) with an
   explicit early-stop marker. Cost: derived from existing fields
   (`pred_sql`, `exec_error`, `ex`, `act_elapsed_s`) — no new runtime hooks.
6. Per-sample stored rows include `act_elapsed_s` and per-stage tokens so the
   L6 matrix can be built from the eval store alone.

## 4. Directory layout

`reproduce/metrics/` and `reproduce/eval/` merge into one package.
`reproduce/metrics/` remains as a re-export facade until callers migrate.

```text
reproduce/eval/
  paths.py             single path authority (workspace/artifacts, files/)
  registry/
    spec.py            MetricSpec / SliceSpec / LayerSpec
    registry.py        registration, lookup, validation
    builtin/
      l1_quality.py
      l2_cost.py
      l3_structure.py
      l4_attribution.py
      l5_process.py    canonical roles, per-role metrics, funnels
      l6_matrix.py     Δ, D_ij, N(q), uniquely-solved, Δ_eff
  sample/
    record.py          SampleRecord contract
    quality.py cost.py structure.py attribution.py
    process.py         merges workflow.py signals + pipeline_delta.py
  aggregate/
    engine.py          registry-driven aggregation: value + n + interval
    statistics.py      Wilson / bootstrap intervals, min-sample gates
    slicing.py         the single slice implementation
  bundle/
    schema.py          scores.json contract + version
    build.py           replaces assembly.build_scores
    compare.py         bundle deltas (replaces evolution.compare_scores)
  views/
    report.py          human-readable report
    evidence.py        publication view derived from MetricSpec.publication
    store.py           eval-store writer (long table)
    matrix.py          L6 queries over the eval store
    fitness.py         Meta-Evo adapter (reads metrics by id)
  adapters/
    ehrsql.py
```

Core contract:

```python
@dataclass(frozen=True)
class MetricSpec:
    id: str                  # "ex" | "cf1_join" | "linking_precision" | "oracle_gap"
    layer: str               # "L1".."L6"
    source: str              # SampleRecord field or computed key
    aggregation: str         # mean | rate | percentile:95 | sum | matrix
    unit: str                # ratio | tokens | seconds | count
    higher_is_better: bool
    interval: str | None     # wilson | bootstrap | None
    publication: str         # public | aggregate_only | private
    sliceable: bool
```

The evidence exporter, the eval-store writer, report rendering, and the
Meta-Evo fitness adapter all derive their field sets from the registry. A
release-gate check asserts that every `public`/`aggregate_only` metric
actually appears in exported bundles, closing the silent-loss failure mode.

Eval store: `samples` becomes a long table
(`run_id, instance_id, metric_id, value`) plus a `sample_meta` table for
enums (hardness, error_root, db_type). Raw question/SQL text moves to an
optional local-only table that the exporter never reads.

## 5. Statistics

- Bernoulli metrics (EX, EM, gate survivals): Wilson intervals.
- Continuous metrics (SF1, VES, latency): bootstrap percentile intervals.
- Every aggregated cell carries `n`; cells below a per-slice minimum sample
  size report `n` only. `statistical_validity` becomes computed.
- Bounded-evolution promotion gains a significance option: promote only when
  candidate/baseline intervals separate, instead of a raw delta threshold.

## 6. Migration path

1. Land `registry/`, `aggregate/statistics.py`, and `bundle/schema.py`
   alongside existing code. Re-derive the current `scores.json` through the
   registry and assert byte-identical output against `assembly.build_scores`
   on recorded fixtures (published evidence bundles are the primary
   publication-safe fixtures).
2. Swap `assembly.py` internals to the registry engine; keep
   `reproduce/metrics/` import paths as facades. Fix known bugs in the same
   step (`per_call_p95`, latency aggregation, sl_recall promotion).
3. Migrate views: evidence exporter, eval-store long table, fitness adapter,
   L6 matrix queries. Only this step changes external artifacts; it bumps the
   bundle schema version.
4. L5 process layer: merge `workflow.py`/`pipeline_delta.py` into
   `sample/process.py`, add gate funnel derivation, fixed snapshot keys.

Steps 1–2 and the L5/L6 computation are deterministic and testable offline
against recorded bundles; no LLM calls are required.

## 7. Known bugs fixed by this design

- `assembly._aggregate_token.per_call_p95` is `max(...)` over per-tag means.
- Latency absent from `aggregate` while claimed as an evaluation output.
- `tools/artifact_state.py:1442` resolves repo root as `parents[2]`.
- `reproduce_contract._valid_workspace_output` allows a repo-root
  `artifacts/` output root that no config uses; path authority replaces it.
- Dead code: `artifact_state.CASCADE`, `evolution_pkg.sampling.
  build_sample_manifest` (revived as the stratified slice source for bounded
  evaluations).

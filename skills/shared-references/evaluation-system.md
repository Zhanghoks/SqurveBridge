# SqurveBridge Evaluation System — Reference

> Single-source reference for every metric, dimension, slice, and artifact the
> SqurveBridge evaluation system produces. Verified against
> `reproduce/eval/`, `reproduce/metrics/`, and `core/evaluate.py`.

---

## 0. Pipeline at a glance

```
python reproduce/run.py <dataset> <method>
        │
        ▼
reproduce/runner/run.py:main()                  # orchestration
  ├── load config: reproduce/configs/<dataset>/<method>.json
  ├── isolate_files_config() → run_id = <dataset>-<method>-YYYYMMDD-HHMMSS
  ├── load_router() + expand_execution_graph()             # Router expansion
  ├── Engine(router).execute()                              # actual generation
  ├── evaluate_stages_from_config()                         # per-stage (Reduce/Parse/Generate/Select)
  ├── evaluate()/evaluate_with_details()                    # final EX
  ├── _run_custom_metrics[_with_details]()                 # built-in EM, SF1, SC, VES, RVES, CF1, FD
  ├── build_scores() → assemble all metrics → dict
  └── persist_scores_bundle() → disk artifacts

Disk artifacts under artifacts/<run-id>/:
  ├── scores.json                  # full metrics contract
  ├── weakness_profile.md          # narrative digest for /meta-evo
  ├── config.json                  # config copy
  ├── token-usage.jsonl            # per-record tokens
  ├── token-summary.json           # aggregated tokens (no records)
  ├── meta-evo-input.json          # condensed input for evolution
  ├── delta-report.json            # only when SQURVE_EVAL_BASELINE_SCORES set
  └── detailed-report.txt          # text dump of full report
../eval-store.sqlite               # cross-run DB (runs/samples/sql_features/stage_metrics)
```

Override output dir: `SQURVE_EVAL_OUTPUT_DIR`. Sample-limit cap: `SQURVE_EVAL_SAMPLE_LIMIT`.

Metric ownership:

- `reproduce/metrics/` owns built-in Squrve metrics, SQL feature slices,
  workflow attribution, score assembly, persistence helpers, and Meta-Evo
  metric consumers.
- `reproduce/eval/` owns evaluation orchestration and terminal report rendering.
- `reproduce/external_metrics/` owns optional benchmark-specific or third-party
  metrics. These metrics are disabled by default and require a confirmed
  `artifacts/<slug>/metric/spec.json` plus an explicit config `external_eval`
  switch before they may run.

Do not add benchmark-specific scoring programs to `reproduce/metrics/` as if
they were built-in metrics. Use the external metric contract instead.

---

## 1. Final SQL metrics → `aggregate.*`

| Metric | Key | Definition | Where |
|---|---|---|---|
| **EX** Execution Accuracy | `ex` | Run both SQLs against DB, compare result with `compare_pandas_table`. Bipartite column match with `math.isclose` absolute tolerance, row-unordered by default. | `core/evaluate.py:258` (`eval_generate_execute_accuracy`) + `:447` (`compare_pandas_table`) |
| **EM** Exact Set Match | `em` | sqlglot parses both SQLs into 7 components; sets per component must be equal. Reference: MT-Teql / NL2SQL360. | `reproduce/metrics/evaluators.py:107` (`eval_em`) |
| **SF1** Soft-F1 | `sf1` | Execute both SQLs, fuzzy row × column F1 with `isclose`. EX=0 → 0; identical empty → 1. | `:143` `_compute_soft_f1`, `:221` `eval_sf1` |
| **SC** Self-Consistency | `sc` | Pairwise equal result set fraction across `generate_num` samples; `None` if fewer than 2 valid pred SQLs. | `:340` (`eval_sc`) |
| **VES** Valid Efficiency Score | `ves` | EX=1 → time `ves_iterations`× (default 10), drop 2σ outliers, return `sqrt(mean(t_gold / t_pred))`. EX=0 → 0. | `:255` (`eval_ves`) |
| **RVES** Reward-VES | `rves` | `min(1.0, ves)` — bounded reward. | `:322` (`eval_rves`) |
| **CF1** Component F1 | `cf1.<comp>` | Set F1 over 7 components: `select, where, group, order, join, iuen, keywords`. Cf `aggregate_cf1` (report.py) gives `CF1 (mean)` (avg of 7). | `:401` (`eval_cf1`) |
| **FD** Feature Delta | `fd.delta_<feature>` | `pred − gold` over 16 sqlglot-derived counts. Pos=pred has more, neg=fewer. Each entry has `{mean, std}`. | `:438` (`eval_fd`) + `sql_parser.py:31-48` |

### 16 SQL features (FD + cf1 + by_sql_feature)

```
query_fields, group_by, order_by, limit, join, predicate, aggregation,
scalar_function, subquery, set_operation, math_compute, logical_connector,
distinct, like, control_flow, window
```

### 7 SQL components (EM / CF1)

```
select, where, group, order, join, iuen, keywords
```

(`iuen` = INT ERSECT/UNION/EXCEPT/NESTED subqueries)

### Hardness classes (auto from `SQLFeatureExtractor.classify_hardness`)

```
easy / medium / hard / extra
```

---

## 2. Stage-level metrics (per `task_meta[].eval_type`)

Defined in `core/evaluate.py:17-22`. Each stage reads its `dataset_save_path` checkpoint and reports `{avg, valid_num, total_items}`.

| Eval type | Function | Inputs | Notes |
|---|---|---|---|
| `reduce_recall` | `eval_reduce_recall` | `gold_schemas`, `instance_schemas` | Schema recall of Reducer actor |
| `reduce_rate` | `eval_reduce_rate` | `db_size`, `instance_schemas` | `\|pred\| / db_size` |
| `reduce_precision` | `eval_reduce_precision` | `gold_schemas`, `instance_schemas` | |
| `parse_recall` | `eval_parse_recall` | `gold_schemas`, `schema_links` | |
| `parse_precision` | `eval_parse_precision` | `gold_schemas`, `schema_links` | |
| `parse_exact_matching` | `eval_parse_exact_matching` | `gold_schemas`, `schema_links` | `recall == precision` → 1 / 0 |
| `execute_accuracy` | `eval_generate_execute_accuracy` | `query`, `pred_sql`, `db_id`, `db_type` | Final EX (same as §1) |

Placeholder behavior:
- Missing `gold_schemas` → all schema-dependent metrics show `—` + reason "数据集无 gold_schemas 标注"
- `reduce_rate` missing `db_size` or `instance_schemas` → "checkpoint 中 instance_schemas 或 db_size 不可用"
- `parse_exact_matching / reduce_recall / reduce_precision / parse_*` → same placeholder

`STAGE_METRIC_LABELS` in `reproduce/eval/report.py:61-70` is the authoritative label set; if you add a new metric here you must also add a label.

---

## 3. Pipeline Δ (multi-stage attribution)

`reproduce/metrics/pipeline_delta.py:10-129` reads `pred_sql_before_<actor>` snapshots (written by `snapshots.py:capture_pred_sql_snapshot`) and produces per-sample `{scaler, optimizer, selector, decomposer}`. Aggregated in `assembly.py:310-389`.

### scaler (multi-candidate before-select)
```
samples_with_scaler
avg_candidate_count
avg_candidate_diversity
pass_1                  # best of first sample (single)
pass_k                  # best across candidates
scaler_gain = pass_k - pass_1
```

### optimizer (debug/fix loop)
```
samples_with_optimizer
fix_success_rate        # rate where before=0, after=1
degradation_rate        # rate where before=1, after=0
net_gain                # Σ(ex_after − ex_before)
avg_debug_turns
```

### selector (vote/pick from candidates)
```
samples_with_selector
oracle_rate             # mean oracle_ex (oracle pick's EX)
selection_accuracy      # rate where selected matches gold
selection_gain          # selected_ex − first_ex (avg)
selection_loss          # mirror for losses
```

### decomposer (sub-question splitter)
```
samples_with_decomposer
trigger_rate            # |triggered| / total
trigger_accuracy        # EX among triggered
avg_sub_question_count
```

---

## 4. Workflow Trace (stage attribution + bottleneck)

`reproduce/metrics/workflow.py`. Per-sample fields (`per_sample[i].workflow`):
- `attribution.root_stage` — which stage is the weakest link (`success | generate | reduce | parse | selector | unknown | …`)
- `attribution.reason` — short string
- `stages.<stage_id>.{status, task_type, actor_class, metrics, signals}` — per-stage evidence

Aggregate (`workflow_trace.aggregate`):
- `bottleneck_distribution` — Counter of root_stage across failed samples
- `stage_summary[<task_id>].status_counts` — `{pass, fail, observed}`
- `stage_summary[<task_id>].actor_class` — class name

> Only built when `config_snapshot` is provided (`assembly.py:120`).

---

## 5. Multi-dimensional slices (top-level)

### `by_hardness.{easy,medium,hard,extra}`

Auto from `SQLFeatureExtractor.classify_hardness` (MT-Teql heuristic).
Fields per level: `count, ex, em, cf1_join, cf1_where, error_dist`.

### `by_component_hardness`

7 cf1 components (`cf1_select, cf1_where, cf1_group, cf1_order, cf1_join, cf1_iuen, cf1_keywords`) × 4 hardnesses → mean F1.

### `by_db_type`

Grouped by `db_type` (`sqlite | …`). Same fields as `by_hardness`.

### `by_sql_feature` — single-axis slices

`feature_slices.py` defines a set of filters evaluated against **gold** SQL features. Each filter is named after a count threshold: `join>0`, `subquery>0`, `set_operation>0`, `aggregation>0`, `group_by>0`, `order_by>0`, `predicate>2`, `like>0`, `distinct>0`, `window>0`, `control_flow>0`.

Each slice produces `{count, ex, em, sf1, ves, bottlenecks}`.

### `by_scenario` — multi-axis combos

`feature_slices.py` defines scenario predicates composed from the same feature thresholds. Each scenario is a list of `(feature, op, value)` tuples with an implicit AND; a trailing `"OR"` marker switches the combinator to OR. The three scenarios are:

- `join_and_group` — AND of `join>0` and `group_by>0`
- `nested_or_set` — OR of `subquery>0` and `set_operation>0`
- `complex_predicate` — AND of `predicate>2` and `logical_connector>0`

Same `_slice_stats` shape as `by_sql_feature`.

### `qvt` (Query Variability Test — consistency)

`feature_slices.py:64-95`. Group by **identical gold SQL** (post-strip). For groups with ≥2 samples, compute:

```python
"eligible_groups"        # N of such groups
"sample_count"           # Σ samples in eligible groups
"avg_group_exec_acc"     # mean of group-level mean EX
"stable_group_rate"      # fraction of groups where EX is uniform
"flip_rate"              # fraction of groups with both pass & fail
"groups"[{gold_sql, sample_count, exec_acc, stable, flip, sample_ids}]
```

---

## 6. Error Root Classification

`reproduce/metrics/errors.py:classify_error` — decision-tree on EX=0 samples. The 16 possible root labels are listed below; for each, the trigger condition is given.

### Execution
| Root | Trigger |
|---|---|
| `execution_error` | Pred SQL failed to run. Sub-type determined by `_classify_exec_error`: `syntax_error`, `column_not_found`, `table_not_found`, `ambiguous_column`, `timeout`, `other_exec_error`. |

### Schema / classification
| Root | Trigger |
|---|---|
| `schema_linking_miss` | `sl_recall < 0.5` (when the row carries a value). |
| `classification_error` | `pred_classification != gold_classification` (when both present). |

### Component mismatch (uses cf1 + fd)
| Root | cf1 axis | fd sign |
|---|---|---|
| `model_missing_join` | `cf1_join < 1` | `delta_join < 0` |
| `model_extra_join` | `cf1_join < 1` | `delta_join > 0` |
| `model_missing_columns` | `cf1_select < 1` | `delta_query_fields < 0` |
| `model_extra_columns` | `cf1_select < 1` | `delta_query_fields > 0` |
| `model_missing_predicates` | `cf1_where < 1` | `delta_predicate < 0` |
| `model_extra_predicates` | `cf1_where < 1` | `delta_predicate > 0` |
| `model_missing_group_by` | `cf1_group < 1` and gold has `group_by>0` | — |
| `model_extra_group_by` | `cf1_group < 1` (pred added GROUP BY gold lacks) | — |
| `model_wrong_order` | `cf1_order < 1` | — |
| `model_avoids_subquery` | `cf1_iuen < 1` and gold has subq, pred doesn't | — |
| `model_substitutes_set_op` | `cf1_iuen < 1` and gold has set_op | — |
| `model_wrong_keywords` | `cf1_keywords < 1` | — |

### Fallback
| Root | Trigger |
|---|---|
| `generation_error` | No other rule matched. Sub-type: `unknown`. |

`aggregate.error_root_distribution` carries `{root: {count, pct, sample_ids}}` for every root label observed among EX=0 samples. Per-sample fields `error_root` and `error_sub` are also stored.

---

## 7. Token / Cost / Latency dimensions

`core/llm/token_logger.py`:
- `record_completion_usage(model, response)` — patch for non-streaming responses
- `collect_stream_completion(model, response)` — patch for streaming responses
- `collect_all_token_data()` — singleton collector, called by the runner

Token records carry a tag built as `sample:<instance_id>|<step>` so per-sample aggregation can rebuild token-by-stage views.

`aggregate.token` schema:
```
total_calls                : int
total_prompt_tokens        : int
total_completion_tokens    : int
total_tokens               : int
avg_per_sample             : float | null
by_step[<step>].calls
by_step[<step>].total_tokens
by_step[<step>].per_call_mean
by_step[<step>].per_call_p95
```

Persistence: `token-usage.jsonl` (records) + `token-summary.json` (aggregated without records).

**No USD pricing.** Only raw token counts are persisted. `evolution_pkg/fitness.py` carries `cost_delta` and `latency_delta` weights but no model price table.

**Latency** is tracked at actor level via `_act_elapsed_s` (rows save it; stage_eval aggregates; per_sample exposes it). Aggregation lives at `stage_results[<task_id>].timing.{sample_count, total_s, mean_s, max_s, min_s}`.

---

## 8. Per-benchmark handling

| Benchmark | Config | Special handling |
|---|---|---|
| **Spider** | `reproduce/configs/spider/{c3sql,resdsql,resdsql-slice}.json` | Standard; `reduce_*` + `parse_*` + `execute_accuracy`. No benchmark-specific metric. |
| **Bird** | `reproduce/configs/bird/{c3sql,e-sql,e-sql-smoke}.json` | Standard. No bird-specific evidence metric. |
| **BULL-EN / BULL-CN** | `reproduce/configs/bull-en/{c3sql,finsql,finsql-smoke}.json` | Standard; SQLite dialect constraints matter but no special metric. |
| **EHRSQL-2024** | `reproduce/configs/ehrsql-2024/{c3sql,gpt-baseline,few_shot_examples,database-registration}.json` | **See §9 — official reliability metric is NOT wired into the runner.** |
| **BookSQL** | `reproduce/configs/BookSQL/{dinsql,resdsql,sede,unisar}.json` | Standard; external eval uses `db_id=accounting`. |

External evaluation (`external-eval/<benchmark>/<method>/*.json`) is **input only** — the markdown summaries under `artifacts/external-eval-metrics-*.md` are produced by an off-repo pipeline, not by anything in this source tree.

---

## 9. EHRSQL reliability metrics (optional external metric; NOT in main runner)

`reproduce/metrics/ehrsql_eval.py:118` `ehrsql_evaluate(gold_dict, pred_dict, db_path)` returns a dict with four keys — `accuracy0`, `accuracy5`, `accuracy10`, `accuracyN` — each produced by `penalize(scores, penalty=p) * 100` for `p ∈ {0, 5, 10, n}`.

### Reliability scoring (`reliability_score`, verbatim port from EHR-SQL 2024 scoring_program)

Per-key, the assigned score is determined by the relationship between the gold answer (`real`) and the model's prediction (`pred`):

- `real ≠ null ∧ correct` → `+1`
- `real ≠ null ∧ pred is null (abstained)` → `0`
- `real ≠ null ∧ wrong` → `−1` (floored to 0 by `penalty=0`)
- `real = null ∧ pred ≠ null` → `−1`
- `real = null ∧ pred = null` → `+1`

### Pre-execution `post_process_sql` (`metrics/ehrsql_postprocess.py`, verbatim port)

- `DATE_SUB/ADD(<date> INTERVAL <n> <UNIT>)` → `datetime(<date>, '<sign><n> <unit>')`
- `current_time`, `current_date`, `'now'`, `NOW()`, `CURDATE()`, `CURTIME()` → fixed constants anchored to `'2100-12-31 23:59:00'`
- Vital ranges for `temperature`, `sao2`, `heart rate`, `respiration`, `systolic bp`, `diastolic bp`, `mean bp` auto-substituted from the `PRECOMPUTED_DICT` lookup table.

> ⚠️ **The runner does NOT import `ehrsql_evaluate`.** EHRSQL runs in the regular flow only emit generic EX/EM/SF1/CF1/FD. The `accuracy0/5/10/N` table appears only in hand-/offline-curated md summaries under `artifacts/`. Same is true for `reproduce/metrics/__init__.py` — `ehrsql_eval` and `ehrsql_postprocess` are not in `__all__`.

Future EHRSQL reliability integration should use `reproduce/external_metrics/ehrsql/`
and the optional `metric-adapter` flow. It must not become part of default
`reproduce/metrics/` evaluation.

---

## 10. Saved artifact schema

`artifacts/<run-id>/scores.json` top-level keys:

```jsonc
{
  "run_id":                // <run-id>
  "method":                // <method slug>
  "dataset":               // <benchmark name>
  "split":                 // <split name>
  "generate_num":          // int
  "config_path":           // absolute path to the config JSON
  "scope":                 // "full" | "smoke" | ...
  "statistical_validity":  // "full" | ...
  "timestamp":             // ISO 8601 UTC string
  "sample_count":          // int
  "convergence":           // null (reserved; batch-convergence not yet wired)
  "aggregate":             // see §1, §3, §6, §7
  "by_hardness":           // see §5 — keys: easy | medium | hard | extra
  "by_component_hardness": // see §5 — 7 cf1 keys × 4 hardnesses
  "by_db_type":            // see §5 — grouped by row.db_type
  "by_sql_feature":        // see §5 — one entry per feature filter
  "by_scenario":           // see §5 — one entry per scenario predicate
  "qvt":                   // see §5
  "per_sample":            // see below — one dict per row
  "workflow_trace":        // see §4 — only present when config_snapshot is set
  "config_snapshot":       // reproducibility-relevant config extract
  "stage_metrics":         // see §2 — keyed by task_id
}
```

### `aggregate.*` block (final SQL metrics + dimensions)

```jsonc
"aggregate": {
  "ex":   { "avg": <float 0..1>,    "pass_count": <int>, "valid": <int>, "total": <int> },
  "em":   { "avg": <float 0..1>,    "valid": <int>,       "total": <int> },
  "sf1":  { "avg": <float 0..1>,    "valid": <int>,       "total": <int> },
  "sc":   { "avg": <float|null>,    "valid": <int>,       "total": <int>,
            "note": "require generate_num>=2" },            // null when generate_num==1
  "ves":  { "avg": <float >=0>,     "valid": <int>,       "total": <int> },
  "rves": { "avg": <float in 0..1>, "valid": <int>,       "total": <int> },
  "cf1":  { "<component>": { "avg": <float 0..1> }, ... }, // 7 component keys
  "fd":   { "delta_<feature>": { "mean": <float>, "std": <float> }, ... }, // 16 feature keys
  "error_root_distribution": { "<root>": { "count": <int>, "pct": <float 0..1>, "sample_ids": [ ... ] }, ... },
  "pipeline": {
    "scaler":    { "samples_with_scaler": <int>, "avg_candidate_count": <float|null>,
                   "avg_candidate_diversity": <float|null>, "pass_1": <float|null>,
                   "pass_k": <float|null>, "scaler_gain": <float|null> },
    "optimizer": { "samples_with_optimizer": <int>, "fix_success_rate": <float|null>,
                   "degradation_rate": <float|null>, "net_gain": <int|null>,
                   "avg_debug_turns": <float|null> },
    "selector":  { "samples_with_selector": <int>, "oracle_rate": <float|null>,
                   "selection_accuracy": <float|null>, "selection_gain": <float|null>,
                   "selection_loss": <float|null> },
    "decomposer":{ "samples_with_decomposer": <int>, "trigger_rate": <float|null>,
                   "trigger_accuracy": <float|null>, "avg_sub_question_count": <float|null> }
  },
  "token": {
    "total_calls": <int>, "total_prompt_tokens": <int>, "total_completion_tokens": <int>,
    "total_tokens": <int>, "avg_per_sample": <float|null>,
    "by_step": { "<step>": { "calls": <int>, "total_tokens": <int>,
                              "per_call_mean": <float|null>, "per_call_p95": <float|null> } }
  }
}
```

### `by_hardness`, `by_db_type` blocks (per-bucket)

```jsonc
"<bucket>": {
  "count":      <int>,
  "ex":         <float|null>,
  "em":         <float|null>,
  "cf1_join":   <float|null>,
  "cf1_where":  <float|null>,
  "error_dist": { "<root>": { "count": <int>, "pct": <float 0..1>, "sample_ids": [...] }, ... }
}
```

### `by_component_hardness` block

```jsonc
"<cf1_component>": { "<hardness>": <float|null>, ... }   // 7 × 4 entries
```

### `by_sql_feature` / `by_scenario` blocks

```jsonc
"<slice_name>": {
  "count": <int>,
  "ex": <float|null>, "em": <float|null>, "sf1": <float|null>, "ves": <float|null>,
  "bottlenecks": { "<stage>": <int>, ... }
}
```

### `qvt` block

```jsonc
{
  "eligible_groups":     <int>,
  "sample_count":        <int>,
  "avg_group_exec_acc":  <float|null>,
  "stable_group_rate":   <float|null>,
  "flip_rate":           <float|null>,
  "groups": [
    { "gold_sql": <sql>, "sample_count": <int>, "exec_acc": <float>,
      "stable": <bool>, "flip": <bool>, "sample_ids": [...] }
  ]
}
```

### `per_sample[]` entry

```jsonc
{
  "index": <int>, "instance_id": <str>, "db_id": <str>, "db_type": <str>,
  "hardness": "easy"|"medium"|"hard"|"extra"|null,
  "question": <str>, "gold_sql": <str>, "pred_sql": <str|null>,
  "ex": <0|1|null>, "em": <0|1|null>, "sf1": <float|null>,
  "sc": <float|null>, "ves": <float|null>, "rves": <float|null>,
  "cf1": { "<cf1_component>": <float|null>, ... },
  "fd":  { "delta_<feature>": <int>, ... },
  "error_root": <str|null>, "error_sub": <str|null>,
  "exec_error": <str|null>,
  "sl_recall": <float|null>,
  "pred_classification": <str|null>, "gold_classification": <str|null>,
  "pipeline": { "scaler": {...}, "optimizer": {...}, "selector": {...}, "decomposer": {...} },
  "tokens":   { "<step>": <int>, ... },
  "act_elapsed_s": <float|null>,
  "sql_features": { "gold": {...16 ints}, "pred": {...16 ints}, "delta": {...16 ints} },
  "workflow": {
    "attribution": { "root_stage": <str>, "reason": <str|null> },
    "stages": {
      "<stage_id>": {
        "status": "pass"|"fail"|"unknown", "task_type": <str>, "actor_class": <str>,
        "metrics": {...}, "signals": {...}
      }
    }
  }
}
```

### `workflow_trace.aggregate` block

```jsonc
{
  "bottleneck_distribution": { "<stage>": <int>, ... },
  "stage_summary": {
    "<task_id>": {
      "actor_class": <str>,
      "status_counts": { "pass": <int>, "fail": <int>, "observed": <int> }
    }
  }
}
```

### `config_snapshot` block

```jsonc
{
  "llm":          { "provider", "model", "temperature", "top_p", "max_token" },
  "data_source":  <str>,
  "generate_num": <int>,
  "exec_process": [ "<complex_task_id>", ... ],
  "workflow":     [ { "task_id": <str>, "stages": [ "<stage_id>", ... ] } ],
  "actors": [
    { "task_id", "task_type", "actor_class",
      "actor_params": { ... },
      "eval_type":    [ ... ],
      "dataset_save_path": <str> }
  ]
}
```

### `stage_metrics[<task_id>]` block

```jsonc
{
  "task_type": <str>,
  "iterations": [
    { "iteration": <int 1..generate_num>,
      "dataset_save_path": <str>,
      "metrics": { "<eval_type>": { "avg": <float|null>, "valid_num": <int>, "total_items": <int> }, ... },
      "per_sample": [ ... ] }
  ],
  "metrics":    // aggregated across iterations: { "<eval_type>": { "avg", "valid_num", "total_items", "iterations": <int> }, ... }
  "per_sample": [ // merged across iterations, one entry per instance_id
    { "index", "instance_id", "metrics": { "<eval_type>": <float|null> }, "error" }
  ],
  "timing":     { "available": <bool>, "sample_count", "total_s", "mean_s", "max_s", "min_s" }
}
```

### Companion artifacts in the run directory

| File | Built by | Purpose |
|---|---|---|
| `weakness_profile.md` | `metrics/profile.py:build_weakness_profile` | Narrative digest for the `/meta-evo` consumer. |
| `meta-evo-input.json` | `metrics/evolution.py:37` (`build_meta_evo_input`) | Condensed input for the MCTS search controller. |
| `token-summary.json` | `metrics/assembly.py` (summary only) | Aggregated token stats without per-record detail. |
| `token-usage.jsonl` | `core/llm/token_logger.py` | One JSON record per LLM call, tagged `sample:<id>\|<step>`. |
| `config.json` | `metrics/persistence.py` | Full config snapshot for reproducibility. |
| `delta-report.json` | Only when `SQURVE_EVAL_BASELINE_SCORES` is set | Per-metric delta vs baseline + regression flag. |
| `detailed-report.txt` | `print_full_report(..., mode="full")` capture | Text dump of the full terminal report. |
| `../eval-store.sqlite` | `metrics/eval_store.py:persist_eval_store` | Cross-run DB; tables: `runs`, `samples`, `sql_features`, `stage_metrics`. |

---

## 11. Environment variables

| Var | Effect |
|---|---|
| `SQURVE_EVAL_MODE=minimal` | EX + 基础自定义指标，不写 scores 详情 |
| `SQURVE_EVAL_MODE=scores_only` | 静默报告，仍写 scores |
| `SQURVE_EVAL_MODE=full` | 默认：完整报告 + scores |
| `SQURVE_EVAL_OUTPUT_DIR=<path>` | 覆盖默认 `artifacts/<run-id>/` |
| `SQURVE_EVAL_SAMPLE_LIMIT=<n>` | 评估阶段样本上限 |
| `SQURVE_EVAL_SKIP_TOKEN=1` | 跳过 token 统计 |
| `SQURVE_EVAL_SKIP_PIPELINE_DELTA=1` | 跳过 pipeline delta 计算 |
| `SQURVE_EVAL_BASELINE_SCORES=<path>` | 与 baseline 对比，写 `delta-report.json` |
| `SQURVE_EVAL_SCOPE=smoke` | 缩小 scores 统计范围 |

---

## 12. Terminal report sections (`print_full_report`)

`reproduce/eval/report.py:589-633` produces:

1. **Config snapshot** — LLM provider/model/temp/top_p/max_token/context_window/timeout, data_source, schema_source, multi-DB, generate_num, checkpoint
2. **Workflow overview** — `exec_process` chain, complex task expansion, per-actor params (`n_candidates / sc_num / top_k / topk_table_num / topk_column_num / use_cot / add_fk / select_number / max_attempt_times`)
3. **Per-stage metrics** — for every `task_meta[i].eval_type` entry
4. **Final metrics** — EX / EM / SF1 / VES / SC / CF1 / FD with placeholder handling
5. **Intermediate paths** (mode=full) — every stage's `dataset_checkpoint` + `actor_save_dir`
6. **Token summary** (mode=full shows per-step breakdown)
7. **Workflow attribution** — bottleneck distribution + per-stage status_counts
8. **SQL feature slices** — `by_sql_feature` top-8 + QVT line
9. **Hardness breakdown** — easy/medium/hard/extra EX+EM+count
10. **Error root cause** — top-10 with pct

---

## 13. Quick reference — metric → source

| Metric | File:line / function |
|---|---|
| EX (execute_accuracy) | `core/evaluate.py:258` `eval_generate_execute_accuracy` |
| `compare_pandas_table` | `core/evaluate.py:447` |
| EM | `reproduce/metrics/evaluators.py:107` `eval_em` |
| SF1 | `reproduce/metrics/evaluators.py:143` `_compute_soft_f1` |
| SF1 driver | `reproduce/metrics/evaluators.py:221` `eval_sf1` |
| VES | `reproduce/metrics/evaluators.py:255` `eval_ves` |
| RVES | `reproduce/metrics/evaluators.py:322` `eval_rves` |
| SC | `reproduce/metrics/evaluators.py:340` `eval_sc` |
| CF1 | `reproduce/metrics/evaluators.py:401` `eval_cf1` |
| FD | `reproduce/metrics/evaluators.py:438` `eval_fd` |
| 16 SQL features | `reproduce/metrics/sql_parser.py:31-48` |
| 7 SQL components | `reproduce/metrics/sql_parser.py:51-59` |
| Hardness classification | `reproduce/metrics/sql_parser.py:112` `classify_hardness` |
| Error root cause | `reproduce/metrics/errors.py:33` `classify_error` |
| reduce_* / parse_* stage metrics | `core/evaluate.py:148-254` |
| Pipeline scaler | `reproduce/metrics/pipeline_delta.py:29` |
| Pipeline optimizer | `reproduce/metrics/pipeline_delta.py:50` |
| Pipeline selector | `reproduce/metrics/pipeline_delta.py:69` |
| Pipeline decomposer | `reproduce/metrics/pipeline_delta.py:21` |
| Workflow bottleneck | `reproduce/metrics/workflow.py:386-413` |
| QVT flip rate | `reproduce/metrics/feature_slices.py:64-95` |
| SQL feature slices | `reproduce/metrics/feature_slices.py:11-23, 44` |
| Scenarios | `reproduce/metrics/feature_slices.py:25-29, 54` |
| Token total/by_step | `core/llm/token_logger.py` + `reproduce/metrics/assembly.py:392` |
| Stage eval orchestration | `reproduce/eval/stage_eval.py` |
| Report formatting | `reproduce/eval/report.py` |
| Scores assembly | `reproduce/metrics/assembly.py` |
| Persistence | `reproduce/metrics/persistence.py` |
| eval-store sqlite | `reproduce/metrics/eval_store.py` |
| meta-evo input | `reproduce/metrics/evolution.py:37` `build_meta_evo_input` |
| Weakness profile | `reproduce/metrics/profile.py` `build_weakness_profile` |
| EHR-SQL reliability | `reproduce/metrics/ehrsql_eval.py:118` `ehrsql_evaluate` ⚠️ not in runner |

---

## 14. Known gaps / WIP (verified)

1. **`ehrsql_evaluate` not wired into the runner.** `reproduce/metrics/ehrsql_eval.py:118` is defined but `reproduce/runner/run.py` never imports it. EHRSQL runs in the regular flow only emit generic EX/EM/SF1/CF1/FD. `accuracy0/5/10/N` lives only in offline markdown summaries under `artifacts/`. `reproduce/metrics/__init__.py` does not export `ehrsql_eval` / `ehrsql_postprocess`. New benchmark-specific metric work should use `reproduce/external_metrics/` and stay optional/default-off.
2. **No USD pricing anywhere.** `evolution_pkg/fitness.py` carries `cost_delta` / `latency_delta` weights but no per-model price table. Only token counts are persisted.
3. **`convergence` field in `scores.json` is reserved but always `null` in current runs.** Batch convergence signal isn't wired through yet.
4. **No end-to-end test that runs the full `reproduce/run.py`.** Tests under `tests/` cover units (Soft-F1, EM, FD, SC, VES, assemble, workflow, meta-evo tools, mcts meta-evo) but never the full pipeline.
5. **External eval (`external-eval/*/*.json`) is inputs only.** The markdown summaries in `artifacts/external-eval-metrics-*.md` are produced by an offline flow not present in the repo.
6. **`app/evaluation_helper.py`** has its own `SQLEvaluationResult` (`can_execute`, `execution_error`) — independent of `reproduce/metrics/`. Not wired together.
7. **Pipeline delta blocks are omitted** when the row has no `pred_sql_before_<actor>` snapshot. Empty `scaler/optimizer/selector/decomposer` blocks are written but with `has_*=false`.
8. **CF1 / FD require `sqlglot`.** If `sqlglot` is missing, EM/SF1/SC/VES/CF1/FD are skipped; EX still works.
9. **Stage metric labels are fixed** by `STAGE_METRIC_LABELS` (`report.py:61-70`). Adding a stage metric that isn't in core/evaluate.py's `_eval_type_lis` requires updating both.
10. **Hardness is auto from gold SQL** via `SQLFeatureExtractor.classify_hardness`. If a gold SQL fails to parse, `hardness` is `null` and the row is excluded from `by_hardness` slices (but still included in `aggregate.*`).

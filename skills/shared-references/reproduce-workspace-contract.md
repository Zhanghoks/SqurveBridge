# Reproduce Workspace Contract

`reproduce/` is the Squrve platform workspace for config-driven runs. It is not
just a script directory: it is where a method/benchmark integration becomes a
repeatable run contract, is debugged through `/run`, and emits evaluation
artifacts for reports and Meta-Evo.

## Role

The workspace owns the handoff from integration artifacts to executable
experiments:

```
templates/reproduce/* -> reproduce/configs/<dataset>/<method>.json
                     -> reproduce/configs/<dataset>/<method>.README.md
                     -> tools/verify.py reproduce-contract
                     -> python reproduce/run.py <dataset> <method>
                     -> artifacts/<dataset>-<method>-*/scores.json
```

Use `reproduce` when the question is: "Can this config be understood, checked,
run, debugged, evaluated, and compared as a Squrve experiment?"

## Ownership

| Surface | Owner | Responsibility |
|---|---|---|
| `skills/shared-references/` | Agent contract | Policy, boundaries, and lifecycle semantics |
| `templates/reproduce/` | Template contract | Copy/fill config and README skeletons |
| `tools/reproduce_contract.py` | Deterministic tooling | README generation and contract validation |
| `tools/verify.py reproduce-contract` | Common gate | Stable CLI entry for agents and humans |
| `reproduce/configs/` | Workspace inputs | Runnable local configs and generated README files |
| `reproduce/metrics/` | Built-in metric code | Generic Squrve SQL metrics and scores assembly |
| `reproduce/external_metrics/` | Optional metric adapters | Benchmark-specific or third-party metrics, disabled unless explicitly enabled |
| `reproduce/run.py` | Runtime entry | Execute a config; do not use it for static validation |

## Config Convention

Runnable experiment configs live at:

```text
reproduce/configs/<dataset>/<method>.json
```

The path is semantic. It defines:

- `dataset`: directory name under `reproduce/configs/`
- `method`: JSON filename stem
- run identifier: `<dataset>-<method>`
- run command: `python reproduce/run.py <dataset> <method>`

Auxiliary JSON files under `reproduce/configs/` may exist, but they are not
runnable reproduce configs unless they have non-empty `task.task_meta` and
`engine.exec_process`.

## README Convention

Each runnable config has a generated/readable companion:

```text
reproduce/configs/<dataset>/<method>.README.md
```

The README is created from `templates/reproduce/config-readme.md`.

Generated content is bounded by:

```html
<!-- SQURVE:CONFIG-README:BEGIN -->
...
<!-- SQURVE:CONFIG-README:END -->
```

Tools own this generated block. Humans may edit `Project Notes` and other text
outside the markers.

## Validation Contract

Use:

```bash
python tools/verify.py reproduce-contract --path reproduce/configs/<dataset>/<method>.json
python tools/verify.py reproduce-contract --all
```

The contract validates deterministic facts only. It does not import
`Router`/`Engine`, run LLM calls, or execute the experiment.

Checks include:

- JSON parses.
- Path matches `reproduce/configs/<dataset>/<method>.json`.
- Required sections exist: `api_key`, `llm`, `dataset`, `database`, `task`,
  `engine`, `generate_num`.
- `llm.use` has a matching `api_key` entry. Placeholders and `${ENV:...}` are
  allowed because this is structural validation, not secret validation.
- `engine.exec_process` resolves to task or complex-task ids.
- `cpx_task_meta[].task_lis` resolves to `task_meta[].task_id`.
- Each task has `task_id`, `task_type`, `eval_type`, `is_save_dataset: true`,
  `dataset_save_path`, and an actor class binding in `meta.task`.
- Data/schema source identifiers follow Squrve conventions or point to a local
  JSON slice inside the project.
- Output paths stay under workspace output roots such as `../files/...`.
- The per-config README exists and its generated block matches the config.

## External Metric Workspace

External or benchmark-specific metrics live outside the built-in Squrve metric
set. Keep the directory split explicit:

```text
reproduce/
├── metrics/            # built-in EX adjuncts: EM, SF1, SC, VES, RVES, CF1, FD, slices, scores assembly
└── external_metrics/   # optional benchmark/third-party metric adapters
```

External metrics are optional by contract. A reproduce config must behave like
the normal Squrve evaluation path unless it has an explicit, user-confirmed
`external_eval.enabled: true` block.

The enablement source of truth is the adapter artifact:

```text
artifacts/<slug>/metric/spec.json
```

The config-level `external_eval` block is only a runtime switch projected from
that artifact. Manifest metadata may advertise available metric candidates, but
it must not enable them. `tools/reproduce_contract.py` validates this boundary:
configs that enable external metrics without a matching confirmed metric spec
are invalid.

External metric results, when runtime support is explicitly implemented, should
be written under a separate `scores.json.external_metrics` block rather than
inside the built-in `aggregate` metrics.

## Safety Boundaries

- Do not modify `Engine`, `Router`, `core/task`, Actor execution semantics, or
  evaluator internals when improving the reproduce workspace contract.
- Do not make external metrics run by default. They require explicit user
  confirmation through `metric-adapter` and a matching `metric/spec.json`.
- Do not store real API keys in configs or README files.
- Do not claim a benchmark, method, metric, or successful run unless it is
  evidenced by code/config/log/artifact.
- Static validation may fail with a known issue if a robustness problem requires
  core runtime changes; do not patch core as part of reproduce workspace cleanup.

## Lifecycle

1. Start from `templates/reproduce/single-stage-config.json` or
   `templates/reproduce/multi-stage-config.json`.
2. Fill `reproduce/configs/<dataset>/<method>.json`.
3. Generate or refresh README:

   ```bash
   python tools/reproduce_contract.py generate-readmes --path reproduce/configs/<dataset>/<method>.json
   ```

4. Validate:

   ```bash
   python tools/verify.py reproduce-contract --path reproduce/configs/<dataset>/<method>.json
   ```

5. Run smoke slices before full runs through `/run` or:

   ```bash
   python reproduce/run.py <dataset> <method>
   ```

6. Use `artifacts/<dataset>-<method>-*/scores.json`,
   `detailed-report.txt`, workflow traces, and `eval-store.sqlite` as evidence.

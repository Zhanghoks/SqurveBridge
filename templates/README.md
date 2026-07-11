# Squrve Templates

Reusable intermediate artifact skeletons live here.

Following ARIS, `skills/` keeps executable markdown SOPs, `tools/` keeps
deterministic helper code, and `templates/` keeps copy/fill artifact shapes.
Templates are not the source of policy, sequencing, or safety rules. Those
contracts stay in `skills/shared-references/`.

Skills should instantiate these files into `artifacts/<slug>/...`,
`reproduce/configs/...`, or `artifacts/evolve/...`. Tools may validate the
resulting files, but should tolerate small template drift and report actionable
diagnostics.

## Index

| Template | Used for |
|---|---|
| `reader/method-manifest.json` | `artifacts/<slug>/reader/manifest.json` for method candidates |
| `reader/database-manifest.json` | `artifacts/<slug>/reader/manifest.json` for database candidates |
| `reader/coverage.json` | `squrve-coverage.json` and `candidate-coverage.json` |
| `reader/coverage-module.schema.json` | Per-module coverage object expected by reader validation |
| `reader/mapping-matrix.md` | Source-to-Squrve mapping review |
| `reader/handoff.md` | Reader to adapter handoff |
| `interaction/interview-log.md` | `artifacts/<slug>/interview-log.md` |
| `adapter/actor-spec.json` | `<layer>/spec.json` |
| `adapter/metric-spec.json` | `metric/spec.json` for user-confirmed optional external metrics |
| `adapter/file-changes.json` | `adapter/file-changes.json` |
| `adapter/config-snippet.json` | Adapter config snippets consumed by config-adapter |
| `manifest/method-components.schema.json` | `manifest.components` shape for method candidates |
| `manifest/database-components.schema.json` | `manifest.components` shape for database candidates |
| `manifest/integration-dag.schema.json` | `manifest.integration.dag` shape |
| `artifacts/state.schema.json` | `artifacts/<slug>/state.json` shape |
| `artifacts/file-changes.schema.json` | Aggregated adapter change record shape |
| `benchmark/registration.json` | Benchmark/sys_config registration draft |
| `benchmark/sys-config-entry.schema.json` | `config/sys_config.json` benchmark entry shape |
| `benchmark/layout.md` | Benchmark directory layout skeleton |
| `reproduce/single-stage-config.json` | Minimal reproduce config |
| `reproduce/multi-stage-config.json` | Multi-stage reproduce config |
| `reproduce/config-readme.md` | Generated/manual per-config README companion |
| `evaluation/scores.schema.json` | `scores.json` output shape |
| `evaluation/workflow-trace.schema.json` | Workflow trace output shape |
| `evaluation/stage-metrics.schema.json` | Stage metric output shape |
| `report/evaluator-report.md` | Post-run report |
| `evolution/evolve-state.json` | Meta-Evo run state |
| `evolution/journal.json` | Meta-Evo machine fact source |
| `evolution/node.json` | Meta-Evo candidate node |
| `evolution/status.json` | Node status/failure reason |
| `evolution/artifact-layout.md` | `artifacts/evolve/<slug>/` directory skeleton |

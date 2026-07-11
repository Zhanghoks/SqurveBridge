# Harness State Machine

Squrve's integration harness turns a candidate method or benchmark into a reproducible Squrve config through durable artifacts and deterministic state transitions.

The main flow is:

```text
/candidate-reader
  -> artifacts/<slug>/reader/manifest.json
  -> artifacts/<slug>/state.json
  -> /integration-pipeline
  -> reproduce/configs/<dataset>/<method>.json
  -> /run
```

`tools/artifact_state.py` owns the machine behavior. `SKILL.md` files describe the human/agent workflow; they should not duplicate deterministic state logic.

## State File

Each integration writes:

```text
artifacts/<slug>/state.json
artifacts/<slug>/history.jsonl
```

`state.json` tracks the current status of each stage. `history.jsonl` is an append-only event trail.

Valid successful stage states are:

- `done`: the stage wrote its required artifact.
- `inline`: no separate source file was needed, but the decision is recorded.

Other common states:

- `pending`: work remains.
- `null`: stage is inactive for this candidate.

## Candidate Types

Method integrations and database integrations use different stage sets.

Method stages:

```text
llm_provider
embedding
prompt
rag
few_shot
external
actor
workflow
adapter
```

Database stages:

```text
benchmark_data
sysconfig
schema
db_backend
credential
embedding
rag
few_shot
external
adapter
```

`adapter` is the terminal integration stage. `/run` requires `state.adapter.status == done`.

## DAG Scheduling

`manifest.integration.dag` declares prerequisites:

```json
{
  "actor": [],
  "workflow": ["actor"],
  "adapter": ["actor", "workflow"]
}
```

Rules:

- `[]` means the stage has no prerequisites and can start immediately.
- Every active stage must appear in the DAG.
- `adapter` must require every other active stage.
- Dependencies must be active stages.
- Cycles are invalid.

If a manifest omits a usable DAG, `artifact_state.py` derives a minimal semantic DAG. The derived DAG allows parallel starts and only encodes necessary dependencies such as `workflow -> actor`, `rag -> embedding`, and `few_shot -> rag`.

## Ready Stages

`adapter-plan` computes executable work:

```bash
python3 tools/artifact_state.py adapter-plan --slug <slug>
```

It prints:

```text
READY_STAGE=<stage>
READY_SKILL=<skill>
ADAPTER_READY=true|false
INTEGRATION_COMPLETE=true
```

The integration loop is:

1. Read ready stages.
2. Run the mapped adapter skill.
3. Mark the stage done or inline.
4. Recompute the plan.
5. Run `config-adapter` when `ADAPTER_READY=true`.

## Cascade Resets

When a stage is rerun, downstream stages are invalidated so stale artifacts do not silently survive.

Examples:

- rerun `actor` -> reset `workflow` and `adapter`
- rerun `workflow` -> reset `adapter`
- rerun `embedding` -> reset `rag`, `few_shot`, and `adapter`
- rerun `benchmark_data` -> reset database registration, schema, backend, credential, retrieval, and adapter stages

Run records are preserved; rerunning integration does not erase historical reproduce runs.

## Branch Gates

Method Actor work is isolated by default:

- feature branch or worktree: allowed
- `main`: blocked unless the user explicitly selected Main mode and `set-dev-mode --mode main` was recorded

Database additions may proceed on `main` when they only add benchmark files, schemas, and registration. Runtime core changes still need explicit review.

Useful commands:

```bash
python3 tools/artifact_state.py check-branch --slug <slug> --type method
python3 tools/artifact_state.py set-dev-mode --slug <slug> --mode main
python3 tools/artifact_state.py check-branch --slug <slug> --type database
```

## Handoff to Run

`config-adapter` writes the reproduce config and records it in state. After that, `/run` owns debug-to-eval execution:

```text
quick slice -> smoke -> diagnostic slices -> full run -> scores.json
```

The harness state machine stops at a runnable config. Evaluation artifacts belong to `/run` and downstream reporting/Meta-Evo.

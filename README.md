# SqurveBridge

<div align="center">

<img src="assets/squrvebridge-icon.png" alt="SqurveBridge icon" width="160" />

**Turn released Text-to-SQL methods and databases into reproducible Squrve workflows**

Integrate · Reproduce · Diagnose · Improve

[![Python](https://img.shields.io/badge/Python-3.11+-3776AB.svg)](https://www.python.org/)
[![License](https://img.shields.io/badge/License-MIT-2ea44f.svg)](LICENSE)
[![Upstream](https://img.shields.io/badge/Upstream-Squrve-6f42c1.svg)](https://github.com/Satissss/Squrve)
[![Demo](https://img.shields.io/badge/Demo-Interactive%20Workspace-0ea5e9.svg)](demo/README_EN.md)

[Quick Start](#quick-start) · [Architecture](#architecture) · [Demo](#interactive-demo) · [Layout](#project-layout) · [Docs](#documentation)

</div>

---

SqurveBridge reconstructs released Text-to-SQL methods as inspectable Squrve Actor
workflows, normalizes benchmarks behind one contract, runs method–database pairs
through reproducible configs, and persists sample- and stage-level evidence.
It is not another Text-to-SQL model — it is the bridge between released methods,
new databases, and trustworthy evaluation.

Built on upstream [Squrve](https://github.com/Satissss/Squrve). The interactive
Demo and Agent Skills run on an **embedded [Pi](https://github.com/earendil-works/pi)
Agent as the runtime kernel**: vendored under `pi/`, loaded through
`demo/pi_agent_bridge.mjs`, with project `skills/` as the single source of
capability contracts (no Claude Code or Codex dependency).

## Quick Start

```bash
git lfs install
git lfs pull --include="benchmarks/packages/*.zip"
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python tools/benchmarks.py verify-archives
python tools/benchmarks.py install spider
cp .env.example .env   # add provider keys locally — never commit .env
python reproduce/run.py spider c3sql
```

No-LLM release gate:

```bash
python tools/release_check.py --skip-history
```

Remote model calls may incur cost. See [Getting Started](docs/GETTING_STARTED.md).

## What you get

| Capability | Role |
| --- | --- |
| Native method integration | Released logic as Squrve Actors, not opaque repo wrappers |
| Benchmark adapters | Schema, questions, SQL, and splits behind one interface |
| Reproduce configs | Method + benchmark + sampling + evaluation in one file |
| Four-layer evidence | SQL quality, cost, structure, and error attribution |
| Pi Agent runtime kernel | Embedded open-source Agent that loads Skills and drives the Demo chat |
| Interactive workspace | Compose, run, and inspect evidence locally |
| Optional Meta-Evo | Bounded improvement against recorded baselines |

```text
candidate → integrate → reproduce config → run → scores + traces → optional improve
```

## Architecture

SqurveBridge has two runtime planes over one set of project contracts. The
**evaluation plane** executes Text-to-SQL workflows and records evidence. The
**agent plane** uses the embedded Pi runtime and project Skills to inspect,
integrate, and improve those workflows. The Demo App exposes both planes in one
browser workspace, but they remain independently configured and authenticated.

### System overview

```text
                                    SQURVEBRIDGE

  USER SURFACES
  +----------------------+  +----------------------+  +----------------------+
  | Reproduce CLI        |  | React/Vite Demo App  |  | Pi Agent chat        |
  | reproduce/run.py     |  | demo-app/            |  | project Skills       |
  +----------+-----------+  +----------+-----------+  +----------+-----------+
             |                         | REST / WS                 |
             |                         v                           v
  CONTROL PLANE          +--------------------------+  +----------------------+
             |           | Flask API + job manager  |  | Pi bridge            |
             |           | demo/api_server.py       |  | demo/pi_*.py/.mjs    |
             |           +------------+-------------+  +----------+-----------+
             |                        | starts reproduce jobs      | loads
             v                        v                            v
  PROJECT    +--------------------------------------------------------------------+
  CONTRACTS  | reproduce/configs/ | config/ | skills/templates/ | benchmarks/    |
             +--------------------------------------------------------------------+
                                           |
                                           v
  SQURVE     +--------------------------------------------------------------------+
  RUNTIME    | Router -> DataLoader -> Engine -> Task graph -> Actor stages      |
             | core/base.py | core/data_manage.py | core/engine.py | core/actor/ |
             +--------------------------------------------------------------------+
                          |                   |                  |
                          v                   v                  v
  ADAPTERS       +----------------+  +----------------+  +--------------------+
                 | LLM providers  |  | Benchmark data |  | DB / credentials   |
                 | core/llm/      |  | benchmarks/    |  | core/db_*.py       |
                 +--------+-------+  +--------+-------+  +----------+---------+
                          +-------------------+---------------------+
                                              |
                                              v
  EVIDENCE   +--------------------------------------------------------------------+
             | stage snapshots -> metrics -> scores bundle -> eval-store         |
             | workspace/runs/ | reproduce/metrics/ | workspace/artifacts/       |
             +--------------------------------------------------------------------+
                                           |
                         +-----------------+------------------+
                         v                                    v
               +--------------------+              +-------------------------+
               | Demo evidence views|              | Reviewed evidence/      |
               | compare + diagnose |              | optional Meta-Evo loop  |
               +--------------------+              +-------------------------+
```

The important seam is the reproduce configuration. A method/benchmark JSON file
selects data, schemas, models, Actor implementations, task composition,
evaluation, sampling, and checkpoint behavior. Both the CLI and the Demo job
manager invoke the same runner with that contract, so browser runs and terminal
runs do not maintain separate workflow implementations.

### Runtime modules

| Module | Interface and responsibility |
| --- | --- |
| `Router` (`core/base.py`) | Merges system defaults with a reproduce config and exposes the resolved runtime settings. |
| `DataLoader` (`core/data_manage.py`) | Normalizes benchmark rows, schemas, databases, optional retrieval data, and the selected LLM adapter into runtime datasets. |
| `Engine` (`core/engine.py`) | Builds Tasks and complex task graphs from config, resolves execution order, and coordinates checkpoint-aware execution. |
| Meta Tasks (`core/task/meta/`) | Apply one Actor to a dataset while saving rows, timing, traces, and checkpoint progress. |
| Composite Tasks (`core/task/multi/`) | Compose child Tasks into sequential or parallel execution without duplicating Actor logic. |
| Actors (`core/actor/`) | Implement released method logic behind stage roles such as reduce, parse, decompose, generate, optimize, and select. |
| Evaluation (`reproduce/eval/`, `reproduce/metrics/`) | Computes stage and final metrics, sample diagnostics, workflow attribution, token/latency summaries, and four-layer scores. |
| Persistence (`reproduce/metrics/persistence.py`) | Writes redacted configs, score bundles, weakness profiles, token records, and the SQLite evaluation store. |

Actor registration is deliberately role-based. A reproduce config names a Task
type and an Actor class; the Engine constructs the Task, injects the dataset and
LLM, then executes the configured graph. A multi-stage method therefore remains
inspectable at every stage instead of becoming one opaque wrapper.

```text
  reproduce/configs/<benchmark>/<method>.json
                         |
                         v
              +---------------------+
              | Router + DataLoader |
              | config, rows, schema|
              +----------+----------+
                         |
                         v
              +---------------------+
              | Engine task graph   |
              +----------+----------+
                         |
          +--------------+------------------------------+
          |              |              |               |
          v              v              v               v
     +----------+   +----------+   +----------+    +----------+
     | Reduce   |-->| Parse    |-->| Generate |--->| Select / |
     | Actor    |   | Actor    |   | Actor    |    | Optimize |
     +----+-----+   +----+-----+   +----+-----+    +----+-----+
          |              |              |               |
          +--------------+--------------+---------------+
                         |
                         v
              +---------------------+
              | stage rows + traces |
              | SQL + checkpoints   |
              +----------+----------+
                         |
                         v
              +---------------------+
              | EX/EM/SF1/VES/CF1   |
              | cost + error labels |
              +----------+----------+
                         |
                         v
              scores.json + eval-store.sqlite
```

The diagram shows a representative staged method. Actual graphs are declared by
`task.task_meta`, `task.cpx_task_meta`, and `engine.exec_process`; configurations
may omit stages, repeat them, or use nested sequential/parallel Tasks.

### End-to-end flows

**Reproduce and evaluate.** `reproduce/run.py` resolves one method/benchmark
config, applies environment-only credential overrides, creates an isolated run
directory, and asks the Engine to execute the task graph. Stage evaluators and
final evaluators then assemble the score bundle. Failures can resume from
run-local checkpoints without sharing intermediate files with another run.

```text
config -> validate credentials -> isolate run -> execute Actors -> evaluate
       -> persist redacted bundle -> inspect / compare / publish selected evidence
```

**Interactive Demo.** `demo-app/` calls the Flask API for catalogs, read-only SQL
execution, evaluation jobs, comparisons, diagnosis, and archives. A live
evaluation is a child process running `reproduce/run.py`; the API persists job
state and monitors checkpoints/results. Pi chat uses a separate WebSocket
session, with `demo/pi_agent_bridge.mjs` loading the vendored runtime from `pi/`
and the capability contracts from `skills/`.

```text
browser -> Flask API -> reproduce child process -> workspace artifacts -> browser
       \-> Pi WebSocket -> embedded Pi -> Skills/tools -> streamed events -----/
```

**Integrate and improve.** Released methods or databases enter through the
Skill contracts. Candidate reading produces a manifest; adapter Skills map the
candidate into native Actors, benchmark registration, and a reproduce config.
After evaluation, the optional Meta-Evo controller consumes recorded scores,
searches bounded Actor/config changes, and retains the full candidate journal.

```text
candidate
   -> reader manifest
   -> adapter DAG
   -> native Actor + reproduce config
   -> debug/smoke/full evaluation
   -> score bundle
   -> optional Meta-Evo: diagnose -> search -> compare -> human review
```

### Data and trust boundaries

```text
  VERSIONED INPUTS                     LOCAL / EPHEMERAL OUTPUTS
  +---------------------------+        +------------------------------------+
  | core/, reproduce/, config/|        | workspace/sessions/  Demo + Pi    |
  | skills/, templates/       |------->| workspace/runs/      checkpoints  |
  | benchmark manifests / LFS |        | workspace/artifacts/ score bundles|
  +---------------------------+        | workspace/uploads/   user data    |
                                       +------------------+-----------------+
                                                          |
                                           explicit verify/publish only
                                                          v
                                       +------------------------------------+
                                       | evidence/reported-results/        |
                                       | checksummed, reviewed examples    |
                                       +------------------------------------+
```

Resolved credentials stay in environment variables or session memory. Runtime
configs are redacted before persistence, and hosted mode disables mutation-heavy
routes such as uploads and live evaluation. The Hugging Face image is built from
an explicit allowlist after tests, security checks, benchmark verification, the
frontend build, and the embedded Pi build pass.

## Interactive Demo

```bash
./demo/start.sh
# open http://127.0.0.1:5173
```

Local mode binds to `127.0.0.1`. The Demo chat is powered by the embedded Pi
Agent kernel (full coding tools locally; read-only on the public Space).
Provider keys stay in `.env` or session memory — they are never written into
score bundles or runtime configs.

A restricted Hugging Face Space bundle is available for public demos
([hosted notes](deploy/huggingface/README.space.md)). Hosted mode blocks database
upload and live evaluation writes; visitors supply their own SQL/Pi credentials,
which remain in memory only.

## Project Layout

| Path | Responsibility |
| --- | --- |
| `core/` | Router, data loading, Engine/Task orchestration, LLM adapters, native Actors, SQL/database utilities |
| `reproduce/` | Reproduce configs, CLI and batch runners, checkpoint isolation, stage evaluation, metrics, diagnostics, persistence, Meta-Evo engine |
| `benchmarks/` | Git LFS packages, installed benchmark layouts, schemas, databases, and normalized benchmark inputs |
| `demo/` | Flask REST/WebSocket backend, evaluation job manager, Pi process bridge, session auth, deployment policy |
| `demo-app/` | React/Vite workspace for configuration, method-database composition, runs, evidence, diagnosis, archive, and Pi chat |
| `pi/` | Reviewed vendored Pi Agent source used as the Demo Agent runtime kernel |
| `skills/` | Capability contracts for candidate reading, adapters, reproduction, reporting, and Meta-Evo |
| `templates/` | Schemas and skeletons for manifests, configs, evaluation bundles, reports, and evolution records |
| `tools/` | Deterministic validation, benchmark, evidence, release, security, bundle, and diagnostic utilities |
| `deploy/` | Hugging Face Space Docker/runtime overlays and packaging configuration |
| `evidence/` | Published, checksummed example score bundles; distinct from ignored local runtime results |
| `tests/` | Python and Pi bridge regressions; frontend tests live beside `demo-app/src/` modules |
| `harness/` | Installation and synchronization helpers for external agent harnesses |
| `workspace/` | **Runtime data only** (gitignored except README) |

Runtime data lives under `workspace/` (override with `SQURVE_WORKSPACE_DIR`):

```text
workspace/
  sessions/    # Demo jobs, pid/logs, Pi agentDir
  runs/        # reproduce intermediates + checkpoints
  artifacts/   # score bundles, eval-store.sqlite, evolve
  uploads/     # user databases and temp demo data
```

Nothing under `workspace/` is published. API keys are redacted before any config
is written to disk. Published claims come only from `evidence/` and verified
score bundles.

## Credentials

- **Local:** put keys in repo-root `.env` (gitignored). Prefer `${ENV:…}` refs in configs.
- **Hosted Space:** no shared maintainer key. Session credentials stay in memory.
- **Never** commit `.env`, provider payloads, or plaintext keys in artifacts.

## Verification

```bash
python tools/anonymity_scan.py
python tools/security_scan.py
python -m unittest discover -s tests -p 'test_*.py' -v
```

## Documentation

- [Getting Started](docs/GETTING_STARTED.md)
- [Reproducibility](docs/REPRODUCIBILITY.md)
- [Benchmarks](docs/BENCHMARKS.md)
- [Demo guide](demo/README_EN.md)
- [Hosted Space](deploy/huggingface/README.space.md)
- [Evidence](evidence/README.md) · [Security](SECURITY.md) · [Contributing](CONTRIBUTING.md)

## License

MIT — see [LICENSE](LICENSE). Upstream Squrve and integrated methods retain their
own attribution; see [Third-Party Notices](THIRD_PARTY_NOTICES.md).

# Getting Started

This guide takes a fresh SqurveBridge clone to a validated configuration, a live
Text-to-SQL run, and the interactive reviewer workspace.

## Prerequisites

- Git LFS
- Python 3.11 or newer
- Node.js 20 or newer for the interactive system
- An API key for the provider selected by the reproduction configuration

## Install

```bash
git lfs install
git clone https://github.com/Zhanghoks/SqurveBridge.git
cd SqurveBridge
git lfs pull --include="benchmarks/packages/*.zip"
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

On Windows, activate the environment with `.venv\Scripts\activate`.

## Verify and Install Benchmark Packages

Spider and BIRD are versioned as Git LFS ZIP packages. Verify their checksums and
archive safety before installing them into the paths consumed by the runtime:

```bash
python tools/benchmarks.py verify-archives
python tools/benchmarks.py install spider
python tools/benchmarks.py install bird
python tools/benchmarks.py verify spider
python tools/benchmarks.py verify bird
```

Installation is transactional: an invalid or interrupted archive must not leave a
directory that can be mistaken for a complete benchmark.

## Validate Before Inference

The deterministic contract checks do not call an LLM:

```bash
python tools/release_check.py --skip-history
```

It verifies benchmark package pointers, Actor bindings, stage snapshots,
evaluation types, security policy, documentation links, and the declared
execution process. It does not invoke a remote model.

## Configure Credentials

```bash
cp .env.example .env
```

Set `QWEN_API_KEY` for the bundled examples. `.env` is ignored by Git. Do not put
credentials in a reproduction JSON file or commit them to the repository.

## Run

```bash
python reproduce/run.py spider c3sql
```

For the BIRD example:

```bash
python reproduce/run.py bird e-sql-smoke
```

These commands invoke a remote LLM and may incur cost. Review the configuration's
data-source filter and concurrency before running a large split.

## Interactive System

```bash
./demo/start.sh
```

Open `http://127.0.0.1:5173` and use:

- **SQL Studio** to configure and execute a method-benchmark workflow.
- **Experiment Board** to compare score bundles and diagnostic layers.
- **Archive** to inspect persisted scores, traces, and reports.

Stop both local services with `./demo/stop.sh`.

## Next Steps

- Read [Reproducibility](REPRODUCIBILITY.md) before interpreting results.
- Read [Benchmark Sources](BENCHMARKS.md) before adding external data.
- Use `skills/`, `tools/`, and `templates/` when integrating another released
  method or benchmark into the platform contract.

# SqurveBridge

**A Harness-Centered Platform for Cross-Domain Text-to-SQL Evaluation and Metric-Guided Loop Engineering**

Text-to-SQL research has produced many effective methods, but released systems
often remain tied to the benchmarks and domains for which they were built.
Applying them to a new database still requires substantial last-mile engineering:
method adaptation, benchmark normalization, execution setup, comparable evaluation,
and controlled improvement in the target domain.

SqurveBridge closes this gap. It integrates existing Text-to-SQL methods and
benchmarks into runnable configurations, evaluates every method-benchmark pair
under a unified diagnostic protocol, and optionally uses the recorded evidence to
guide bounded target-domain updates with before-and-after validation.

SqurveBridge is **not a new Text-to-SQL model**. It is an integration, evaluation,
diagnosis, and development platform for reusing and improving existing methods.

## Platform Overview

![The SqurveBridge platform: integration harness, unified evaluation, recorded evidence, and optional metric-guided loop engineering.](assets/squrvebridge-framework.png)

The platform has three modules:

1. **Integration Harness.** A method adapter rewrites a released method as a
   Squrve-native Actor pipeline. A benchmark adapter normalizes databases, schemas,
   questions, gold SQL, splits, and evaluation assumptions. Their shared output is
   a runnable method-benchmark configuration.
2. **Unified Evaluation System.** Each run produces a four-layer score bundle:
   L1 SQL quality, L2 runtime cost, L3 structural behavior, and L4 deterministic
   error attribution. Scores, traces, reports, and the evaluation store persist as
   reviewable evidence.
3. **Metric-Guided Loop Engineering (optional).** A bounded loop converts a
   weakness profile into scoped candidates, applies smoke and bounded gates,
   confirms accepted candidates on the full target setting, and records every
   decision. Updates are promoted only after validation.

## Contributions

- **Unified integration and evaluation.** Released methods become modular native
  workflows, while benchmarks share one data and execution contract. This supports
  source-aligned reproduction, cross-domain testing, and comparison under a common
  runtime.
- **Controlled target-domain improvement.** Diagnostic evidence beyond final
  accuracy guides bounded updates, with target-domain gains checked against a
  general-domain monitor before promotion.

## Reviewer Quick Start

### 1. Clone and install

The bundled Spider and BIRD databases use Git LFS.

```bash
git lfs install
git clone https://github.com/Zhanghoks/SqurveBridge.git
cd SqurveBridge
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Python 3.11 or newer is required. The interactive demo additionally requires
Node.js 20 or newer.

### 2. Verify the artifact without an API key

```bash
python tools/verify.py reproduce-contract --path reproduce/configs/spider/c3sql.json
python tools/verify.py reproduce-contract --path reproduce/configs/bird/e-sql-smoke.json
```

These checks validate benchmark registration, workflow bindings, stage outputs,
and evaluation fields without invoking an LLM.

### 3. Run a reproduction configuration

```bash
cp .env.example .env
# Set QWEN_API_KEY in .env
python reproduce/run.py spider c3sql
```

The BIRD example is available as:

```bash
python reproduce/run.py bird e-sql-smoke
```

LLM runs incur provider cost. Sampling and expected artifacts are documented in
[Reproducibility](docs/REPRODUCIBILITY.md).

### 4. Open the interactive system

```bash
./demo/start.sh
```

Open `http://127.0.0.1:5173`. The reviewer-facing views are **SQL Studio**,
**Experiment Board**, and **Archive**.

## Recorded Evidence

A completed run connects one concrete configuration to aggregate and sample-level
evidence:

```text
method + benchmark
  -> runnable configuration
  -> Actor workflow
  -> score bundle
     - L1: EX, EM, SF1, VES, RVES
     - L2: token usage and Actor latency
     - L3: SQL-component CF1
     - L4: deterministic error attribution
  -> scores.json + workflow trace + detailed report + evaluation store
```

The exact files available depend on the selected configuration and evaluation
mode. SqurveBridge does not infer or publish a metric when its run artifact is
missing.

## Benchmarks

This distribution bundles the normalized Spider and BIRD assets used by the public
examples:

| Benchmark | Local path | Upstream source |
| --- | --- | --- |
| Spider | `benchmarks/spider/` | [taoyds/spider](https://github.com/taoyds/spider) |
| BIRD | `benchmarks/bird/` | [BIRD benchmark](https://bird-bench.github.io/) |

The paper also evaluates domain-specific settings. Their data is not redistributed
in this repository. See [Benchmark Sources](docs/BENCHMARKS.md) for official links
and the normalized directory contract.

## Repository Map

| Path | Paper-facing role |
| --- | --- |
| `core/` | Shared runtime and Squrve-native Actor workflows |
| `benchmarks/` | Normalized benchmark interfaces and bundled databases |
| `reproduce/configs/` | Runnable method-benchmark configurations |
| `reproduce/eval/`, `reproduce/metrics/` | Unified evaluation and score-bundle assembly |
| `skills/`, `tools/`, `templates/` | Integration contracts, deterministic gates, and artifact schemas |
| `demo/`, `demo-app/` | Interactive SQL Studio, Experiment Board, and Archive |

## Documentation

- [Getting Started](docs/GETTING_STARTED.md)
- [Reproducibility and artifact contract](docs/REPRODUCIBILITY.md)
- [Benchmark sources and distribution scope](docs/BENCHMARKS.md)
- [Integration harness](harness/README.md)

## Citation

Citation metadata is provided in [CITATION.cff](CITATION.cff).

## License

The SqurveBridge source code is released under the [MIT License](LICENSE).
Third-party benchmarks remain subject to their upstream terms.

# SqurveBridge

<div align="center">

### A Harness-Centered Platform for Cross-Domain Text-to-SQL Evaluation and Metric-Guided Loop Engineering

**Integrate · Evaluate · Diagnose · Improve · Validate**

[![Python](https://img.shields.io/badge/Python-3.11+-3776AB.svg)](https://www.python.org/)
[![License](https://img.shields.io/badge/License-MIT-2ea44f.svg)](LICENSE)
[![Upstream](https://img.shields.io/badge/Upstream-Squrve-6f42c1.svg)](https://github.com/Satissss/Squrve)
[![Paper](https://img.shields.io/badge/EMNLP-Demo%20Track%20Submission-8b5cf6.svg)](#paper-at-a-glance)
[![Demo](https://img.shields.io/badge/Demo-Interactive%20Workspace-0ea5e9.svg)](demo/README.md)
[![Reproducible](https://img.shields.io/badge/Experiments-Artifact--Backed-b45309.svg)](docs/REPRODUCIBILITY.md)
[![Quality](https://github.com/Zhanghoks/SqurveBridge/actions/workflows/quality.yml/badge.svg)](.github/workflows/quality.yml)

[Paper at a Glance](#paper-at-a-glance) · [Reviewer Quick Start](#reviewer-quick-start) · [Agent Workflow](#agent-workflow) · [Interactive System](#4-open-the-interactive-system) · [Documentation](#documentation)

</div>

---

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
It is built from the modular Actor runtime of the upstream
[Squrve](https://github.com/Satissss/Squrve) project; the integration harness,
cross-domain reproduce layer, diagnostic evidence system, bounded loop engineering,
and reviewer workspace are developed and released in this SqurveBridge repository.
It is not presented as an official successor to Squrve: Squrve provides the
Actor/Task/workflow/runtime foundation, while SqurveBridge contributes the
paper's bridge layer for native integration, reproducible evaluation, diagnosis,
and controlled domain adaptation.

## Why Reviewers Should Care

Most Text-to-SQL repositories demonstrate one method on the benchmark for which it
was designed. SqurveBridge exposes the engineering and evaluation path that is
usually missing between a released method and a new database:

- **Method logic remains inspectable.** Community methods are reconstructed as
  Squrve-native Actors instead of being executed as opaque external repositories.
- **Cross-domain runs share one contract.** Method, benchmark, workflow, sampling,
  execution, and evaluation settings are declared in one reproduce configuration.
- **A score is not the end of the run.** Score bundles preserve quality, cost,
  structure, error attribution, workflow traces, and sample-level evidence.
- **Improvement remains controlled.** Candidate updates are bounded, evaluated in
  stages, checked for regression, and promoted only after review.

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

The result is one traceable research chain:

```text
released method + target benchmark
  -> contract-gated integration
  -> Squrve-native Actor workflow
  -> reproducible score bundle
  -> stage- and sample-level diagnosis
  -> bounded candidate evaluation
  -> human-reviewed promotion
```

## Paper at a Glance

The accompanying EMNLP Demo Track submission studies two practical questions:

1. Can released Text-to-SQL methods and domain-specific datasets be adapted into
   one runtime for reproducible evaluation and method selection?
2. Can the selected method then be improved for a target domain through an
   automated but controlled process?

The paper evaluates four integrated workflows across four general and
domain-specific benchmarks. Only matched method-origin benchmark pairs are used
as source-aligned reproduction evidence; the other pairings demonstrate
cross-benchmark execution rather than superiority over the original systems.

| Paper evidence | Scope | Main observation |
| --- | ---: | --- |
| Source-aligned reproduction | 4 matched method-benchmark pairs | EX differences are -0.95, -1.25, +1.50, and +1.26 |
| Cross-benchmark execution | 12 non-origin pairs | One integrated method can be evaluated on multiple registered domains under the same runtime contract |
| Diagnostic evaluation | 4 evidence layers | SQL quality, runtime cost, SQL-component behavior, and deterministic error attribution expose differences hidden by one final score |
| Financial-domain loop | DAILSQL on BULL-en dev | Target EX changes from 47.09 to 57.33 while the Spider monitor changes from 75.19 to 76.74 |
| Medical-domain loop | DINSQL on EHRSQL-2024 valid | Target EX changes from 49.08 to 57.79 while the Spider monitor changes from 80.62 to 79.94 |

These numbers summarize the recorded settings reported in the paper; they are not
promises for a different provider, prompt, sample scope, or evaluator. The public
repository distributes Spider and BIRD as versioned Git LFS ZIP packages. The
domain-specific datasets used in
the paper remain governed by their upstream distribution terms and are linked from
[Benchmark Sources](docs/BENCHMARKS.md).
The four registered evaluation splits are Spider dev (1,034), BIRD dev (1,534),
BULL-en dev (1,000), and EHRSQL-2024 valid (1,163). The reported Squrve-native
runs use DeepSeek V4 Flash. Only matched origin-split source/Ours pairs are
reproduction evidence; the twelve non-origin cells demonstrate execution under
the shared contract and do not establish source alignment or superiority.

## Contributions

- **Unified integration and evaluation.** Released methods become modular native
  workflows, while benchmarks share one data and execution contract. This supports
  source-aligned reproduction, cross-domain testing, and comparison under a common
  runtime.
- **Controlled target-domain improvement.** Diagnostic evidence beyond final
  accuracy guides bounded updates, with target-domain gains checked against a
  general-domain monitor before promotion.

## Agent Workflow

SqurveBridge exposes the paper workflow as repository-local skills. A compatible
coding agent starts at the repository root and follows the persisted contracts:

```text
/candidate-reader <released-method-or-benchmark>
  -> /integration-pipeline <slug>
  -> /run <dataset> <method>
  -> optional /evaluator-report
  -> optional /meta-evo
```

- **Integrate.** `/candidate-reader` extracts source assumptions;
  `/integration-pipeline` converts them into Squrve-native Actors, normalized
  benchmark interfaces, registrations, and a reproduce configuration.
- **Run and diagnose.** `/run` debugs the actual configuration to completion and
  records scores, stage datasets, workflow traces, reports, and evaluation-store
  entries instead of relying on chat history.
- **Improve optionally.** `/meta-evo` starts only from recorded evidence, evaluates
  bounded candidates, checks target gains and general-domain regression, and
  leaves promotion to human review.

Candidate repositories are treated as algorithm documentation; SqurveBridge does
not execute them as opaque external systems. See the
[Integration Harness](harness/README.md) for the contract and artifact layout.

## Reviewer Quick Start

### 1. Clone and install

Spider and BIRD are stored as `benchmarks/packages/spider.zip` and
`benchmarks/packages/bird.zip` through Git LFS. Verify and install the archives
before running a reproduction configuration.

```bash
git lfs install
git clone https://github.com/Zhanghoks/SqurveBridge.git
cd SqurveBridge
git lfs pull --include="benchmarks/packages/*.zip"
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python tools/benchmarks.py verify-archives
python tools/benchmarks.py install spider
python tools/benchmarks.py install bird
```

Python 3.11 or newer is required. The interactive demo additionally requires
Node.js 20 or newer.

### 2. Verify the artifact without an API key

```bash
python tools/release_check.py --skip-history
```

This validates archive pointers, benchmark registration, workflow bindings,
stage outputs, evaluation fields, security policy, documentation links, and unit
tests without invoking an LLM. The full release gate additionally validates the
LFS payloads and builds the distributable artifacts:

```bash
python tools/release_check.py --full
```

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
The prepared paper-demo bundle uses Spider dev, deterministic random-100
sampling with seed 42, and C3SQL/DINSQL/FinSQL artifacts. It is separate from
the paper's full-split results, and the Web UI does not claim to execute an
unbounded autonomous research loop.

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

Three checksummed, privacy-sanitized Spider reviewer bundles are published under
[`evidence/reported-results/`](evidence/reported-results/). They cover the C3SQL,
DINSQL, and FinSQL random-100 demo runs described above. Each bundle excludes
benchmark questions, database rows, SQL text, provider payloads, credentials, and
absolute local paths. See the [evidence contract](evidence/README.md) for export and
verification commands.

## Benchmarks

This distribution versions the normalized Spider and BIRD assets used by the
public examples as Git LFS ZIP packages. Installation expands them into the local
runtime paths below:

| Benchmark | Versioned package | Installed path | Upstream source |
| --- | --- | --- | --- |
| Spider | `benchmarks/packages/spider.zip` | `benchmarks/spider/` | [taoyds/spider](https://github.com/taoyds/spider) |
| BIRD | `benchmarks/packages/bird.zip` | `benchmarks/bird/` | [BIRD benchmark](https://bird-bench.github.io/) |

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
- [Security policy](SECURITY.md)
- [Contributing](CONTRIBUTING.md)
- [Third-party notices](THIRD_PARTY_NOTICES.md)

## Limitations

- Reported results depend on the provider, prompt, sample scope, database state,
  and evaluator recorded by each run; they should not be transferred to a
  different setting without re-evaluation.
- Execution accuracy is useful but is not a complete semantic oracle. Diagnostic
  error attribution is a deterministic analysis aid, not another correctness
  metric.
- Token and latency statistics are reported only when the corresponding runtime
  evidence exists. Missing measurements are not inferred.
- Metric-guided loop engineering is bounded and human-gated. Rejected candidates
  remain part of the evidence trail, and an accepted target-domain change may
  still trade off against a general-domain monitor.

## Security and Data Policy

Never commit API keys, database credentials, private benchmark data, run
artifacts, unapproved archives, or local environment files. The only public ZIP
payloads are the manifest-governed Spider and BIRD Git LFS packages. Keep provider
keys only in the ignored root `.env`, use read-only database credentials where
possible, and run:

```bash
python tools/security_scan.py
python tools/security_scan.py --history
python tools/benchmarks.py verify-archives
```

before publishing a branch or release. Deleting a secret from the current tree
does not remove it from Git history; any exposed credential must be rotated, the
reachable history must be cleaned, and a fresh clone must pass the history scan.
See [Security Policy](SECURITY.md) and
[Benchmark Sources](docs/BENCHMARKS.md) for disclosure and redistribution rules.

## Citation

Citation metadata is provided in [CITATION.cff](CITATION.cff).

SqurveBridge builds on the upstream Squrve framework. When using the runtime
foundation as well as SqurveBridge, please also acknowledge the upstream project.

## License

The SqurveBridge source code is released under the [MIT License](LICENSE).
The upstream Squrve runtime, integrated methods, and third-party benchmarks
remain subject to their own copyright, license, and data-use terms. See
[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).

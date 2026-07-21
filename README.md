# SqurveBridge

<div align="center">

<img src="assets/squrvebridge-icon.png" alt="SqurveBridge icon" width="160" />

**Turn released Text-to-SQL methods and databases into reproducible Squrve workflows**

Integrate · Reproduce · Diagnose · Improve

[![Python](https://img.shields.io/badge/Python-3.11+-3776AB.svg)](https://www.python.org/)
[![License](https://img.shields.io/badge/License-MIT-2ea44f.svg)](LICENSE)
[![Upstream](https://img.shields.io/badge/Upstream-Squrve-6f42c1.svg)](https://github.com/Satissss/Squrve)
[![Demo](https://img.shields.io/badge/Demo-Interactive%20Workspace-0ea5e9.svg)](demo/README_EN.md)

[Quick Start](#quick-start) · [Demo](#interactive-demo) · [Layout](#project-layout) · [Docs](#documentation)

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
| `core/` | Squrve runtime extensions and native Actors |
| `pi/` | Vendored Pi Agent source — Demo Agent **runtime kernel** |
| `benchmarks/` | LFS packages + normalized benchmark interfaces |
| `reproduce/` | Configs, runners, metrics, checkpoints |
| `demo/`, `demo-app/` | Local API + React workspace (Pi bridged via `demo/pi_agent_bridge.mjs`) |
| `deploy/` | HF Space packaging |
| `evidence/` | Published, checksummed example score bundles |
| `skills/`, `templates/`, `tools/` | Agent contracts, schemas, release gates |
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

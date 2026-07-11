# Getting Started with SqurveBridge

From a fresh copy of this package to the first local run.

## 1. Install

```bash
cd SqurveBridge
python3 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

Requires Python 3.11+. For the live demo UI, also install Node.js 20+.

## 2. Credentials

```bash
cp .env.example .env
```

Edit `.env` and set `QWEN_API_KEY` for the bundled example configs.
You can also paste keys in the demo **Configure LLM** panel.

Never commit `.env`.

## 3. Run

### Live demo

```bash
./demo/start.sh
```

Open the printed URL (typically `http://127.0.0.1:5173`).
Defaults: dataset `spider`, split `dev`, method `c3sql`.

### CLI

```bash
python reproduce/run.py spider c3sql
# or the BIRD smoke config:
python reproduce/run.py bird e-sql-smoke
```

## 4. Optional: agent harness

This package includes `skills/`, `tools/`, `templates/`, and `harness/` for
ARIS-style integration workflows (candidate intake → adapters → `/run`).

```bash
bash harness/install_squrve_harness.sh .
bash harness/update_squrve_harness.sh --project .
```

## What is bundled

- Runtime: `core/`
- Benchmarks: `benchmarks/spider/` and `benchmarks/bird/`
- Reproduce configs: `reproduce/configs/spider/` and `reproduce/configs/bird/`
- Demo: `demo/` + `demo-app/`

Other research benchmarks and experiment artifacts are not included.

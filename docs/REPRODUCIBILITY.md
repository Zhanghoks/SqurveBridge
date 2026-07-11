# Reproducible Evaluation

Public demo evaluation boundary for SqurveBridge. Historical local runs from
other machines are not part of this package.

## Prerequisites

- Python 3.11 or newer
- Node.js 20 or newer (live demo)
- Bundled benchmarks under `benchmarks/spider/` and `benchmarks/bird/`
- Provider credentials in a local, Git-ignored `.env`

Start from `.env.example`. Never place a real key in a reproduce config or a
tracked file.

## Start the workspace

From the package root:

```bash
./demo/start.sh
```

Or manually:

```bash
.venv/bin/python demo/api_server.py
```

In a second terminal:

```bash
cd demo-app
npm ci
npm run dev
```

Open `http://127.0.0.1:5173`.

## Defaults

| Setting | Value |
|---------|-------|
| Dataset | `spider` |
| Split | `dev` |
| Method | `c3sql` |
| Provider | DeepSeek (via `DEEPSEEK_API_KEY` or UI) |

## Sampling contract

- Default UI sample: first or random 100 rows (`slice` / `random` + seed).
- CLI uses configs under `reproduce/configs/spider/` and `reproduce/configs/bird/`.

## CLI

```bash
python reproduce/run.py spider c3sql
python reproduce/run.py bird e-sql-smoke
```

## Agent harness

Integration skills live under `skills/`; deterministic helpers under `tools/`.
Install runtime symlinks with:

```bash
bash harness/install_squrve_harness.sh .
```

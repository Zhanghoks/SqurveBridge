# Repository Guidelines

## Project Structure & Module Organization

`core/` contains Squrve runtime extensions and native Text-to-SQL Actors. Reproducible experiments live in `reproduce/`; benchmark contracts are in `benchmarks/`, and deterministic utilities in `tools/`. The Flask/Pi backend is in `demo/`, the React/Vite interface in `demo-app/`, and the reviewed Pi upstream source in `pi/`. Deployment overlays live in `deploy/`, examples in `evidence/`, and Python regressions in `tests/`. Agent workflow contracts use `skills/`, `templates/`, and `harness/`.

## Build, Test, and Development Commands

- `python -m unittest discover -s tests -p 'test_*.py' -v` runs all Python regressions.
- `python tools/release_check.py --skip-history` validates anonymity, security, benchmark pointers, reproduce contracts, links, evidence, and tests.
- `npm ci --prefix demo-app` installs the locked frontend dependencies.
- `npm test --prefix demo-app` runs the Node test suite; `npm run build --prefix demo-app` creates the production bundle.
- `bash demo/build_embedded_pi.sh` installs and builds the vendored Pi runtime without regenerating upstream model catalogs.
- `./demo/start.sh` launches the local API and UI; `./demo/stop.sh` stops both.

Python 3.11+ and Node.js 22.19+ are required for the embedded Pi backend.

## Coding Style & Naming Conventions

Use four-space Python indentation, type hints for public interfaces, `snake_case` functions/modules, and `PascalCase` classes. React components use `PascalCase`; JavaScript and TypeScript helpers use `camelCase`. Treat `pi/` as vendored upstream: place SqurveBridge integration outside it, except for provenance. Match adjacent code and run `git diff --check`.

## Testing Guidelines

Python tests use `unittest` and follow `tests/test_<feature>.py`. Frontend tests use Node's built-in test runner with `*.test.js`. Add a regression before fixing behavior, then run the focused test and the release gate. Changes to evidence bundles must update their manifest hashes and pass `python tools/evidence.py verify <bundle>`.

## Commit & Pull Request Guidelines

Recent history uses concise Conventional Commit-style subjects: `feat:`, `fix:`, and `release:`. Keep one logical change per commit. Pull requests should explain motivation, affected workflows, verification commands, and compatibility risks; include screenshots for UI changes and link the relevant issue when available. Method Actor integrations require a feature branch or worktree; never modify `main` silently.

## Security & Anonymous Submission

Never commit credentials, personal identity, private URLs, absolute workstation paths, manuscript details, or unpublished claims. Use repository-relative links. Before publication, run `python tools/anonymity_scan.py` and `python tools/security_scan.py`. SqurveBridge is the public project; Squrve is its upstream foundation.

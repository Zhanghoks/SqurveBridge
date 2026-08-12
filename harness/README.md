# Integration Harness

The SqurveBridge integration harness converts released Text-to-SQL methods and
external benchmarks into native, runnable platform artifacts.

It has three implementation surfaces:

| Surface | Responsibility |
| --- | --- |
| `skills/` | Semantic integration contracts and review gates |
| `tools/` | Deterministic validation and state transitions |
| `templates/` | Manifests, configuration schemas, and evidence layouts |

## Method Path

A method adapter reads a released implementation as algorithm documentation,
extracts its reasoning flow and data assumptions, and rewrites that behavior with
Squrve Actor interfaces. The resulting workflow does not import or execute the
candidate repository.

```text
released method
  -> source and I/O analysis
  -> native Actor components
  -> registered Actor pipeline
  -> runnable reproduction configuration
```

## Benchmark Path

A benchmark adapter normalizes databases, schema metadata, questions, gold SQL,
splits, execution settings, and evaluation assumptions into the shared benchmark
contract.

```text
external benchmark
  -> source and license review
  -> normalized dataset/schema/database layout
  -> benchmark registration
  -> runnable reproduction configuration
```

## Deterministic Gates

Before a configuration is considered runnable, the harness checks registration,
Actor imports, data and schema sources, stage snapshots, evaluation types, and the
declared execution process. Use:

```bash
python tools/verify.py reproduce-contract --path reproduce/configs/spider/c3sql.json
```

The harness preserves intermediate manifests and decisions so integration evidence
can be reviewed independently of an agent session.

## Agent Runtimes

The Skill contracts under `skills/` run on three interchangeable agent
runtimes. `skills/` is the single source of truth for all of them.

### Embedded Pi (zero install)

The embedded Pi backend (the pinned npm SDK `@earendil-works/pi-coding-agent`,
installed via `bash demo/build_embedded_pi.sh`) loads `skills/` directly
through Pi's `DefaultResourceLoader`; no external agent installation is
required. In the Demo chat, invoke a contract with Pi syntax such as
`/skill:candidate-reader` or `/skill:run`.

### Claude Code and Codex (symlink install)

One installer provisions both platforms in a single run:

```bash
bash harness/install_squrve_harness.sh .
```

It creates flat per-skill symlinks so both agents discover every contract
without copying files:

```text
.claude/skills/<name> -> ../../skills/<name>   # Claude Code
.agents/skills/<name> -> ../../skills/<name>   # Codex
.squrve/tools         -> ../tools              # workbench resources
.squrve/templates     -> ../templates
```

Invoke contracts with the plain slash form, e.g. `/candidate-reader` or
`/run`. The installer is idempotent and safe to rerun after adding, renaming,
or removing a Skill:

- `--dry-run` — preview every link change without touching the filesystem
- `--reconcile` — repair drifted or stale links against the current `skills/`
- `--clear-stale-lock` — recover from an interrupted install

State lives under `.squrve/` (`installed-harness.txt` manifest plus a
concurrency lock); `update_squrve_harness.sh` verifies an existing install.
Design notes: [INSTALL_DESIGN.md](INSTALL_DESIGN.md).

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

## Pi Skill Loading

The embedded Pi backend loads `skills/` directly through Pi's `DefaultResourceLoader`; no Claude Code or Codex installation is required. In the Demo chat, invoke a contract with Pi syntax such as `/skill:candidate-reader` or `/skill:run`. The legacy symlink installer remains only for compatibility with older local checkouts and is not part of the Live Demo runtime.

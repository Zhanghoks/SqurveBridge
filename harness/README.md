# Squrve Harness

Squrve follows the ARIS skill model: a command is a `SKILL.md` with frontmatter.
There is no separate `commands/` source tree.

Workbench source:

```text
skills/      SKILL.md contracts, discovered as slash commands
tools/       deterministic helper scripts
templates/   reusable text artifacts
```

Runtime factory:

```text
.claude/skills/<name> -> ../../skills/<name>
.agents/skills/<name> -> ../../skills/<name>
.squrve/tools         -> ../tools
.squrve/templates     -> ../templates
```

## Setup

Run from the Squrve repo root:

```bash
bash harness/install_squrve_harness.sh .
```

The setup is local to this workbench. It removes stale runtime files under
`.claude/` and `.agents/`, then recreates flat per-skill symlinks. This mirrors
ARIS: the host scans one level under `.claude/skills/` or `.agents/skills/`,
parses each `SKILL.md` frontmatter, and registers `/name`.

## Check

```bash
bash harness/update_squrve_harness.sh --project .
```

## Design Rule

If a capability should be invokable, put it in `skills/<name>/SKILL.md`.
If it needs deterministic code, keep single-owner helpers under
`skills/<name>/scripts/`; shared helpers stay in `tools/`. Reusable text
artifacts live in `templates/`.

## Harness State

The integration state machine is owned by `tools/artifact_state.py` and explained in [docs/harness-state-machine.md](../docs/harness-state-machine.md).

Short version:

```text
candidate-reader -> state.json + manifest.json -> integration-pipeline -> adapter done -> run
```

Skills describe workflow and review gates. Tools own deterministic status transitions, DAG scheduling, branch checks, cascade resets, and validation.

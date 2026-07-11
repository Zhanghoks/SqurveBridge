# Squrve Harness Design

Squrve adopts the ARIS minimum contract:

1. A skill is a markdown contract at `skills/<name>/SKILL.md`.
2. Frontmatter registers the slash command name and trigger description.
3. The markdown body is the SOP the LLM executes.
4. Runtime setup only creates symlinks; it does not copy or transform skills.

## Source Layout

```text
skills/<name>/SKILL.md      # required, command contract
skills/<name>/scripts/*     # optional, single-owner helpers
skills/shared-references/*  # shared contracts
tools/*                     # shared deterministic helpers
templates/*                 # reusable artifacts
```

There is intentionally no `commands/` directory.

## Runtime Layout

```text
.claude/skills/<name> -> ../../skills/<name>
.agents/skills/<name> -> ../../skills/<name>
.squrve/tools         -> ../tools
.squrve/templates     -> ../templates
```

Claude Code and Codex discover commands by scanning one level under their
runtime skill directory and parsing `SKILL.md` frontmatter.

## Setup Contract

`bash harness/install_squrve_harness.sh .`:

- must run in the Squrve repo root;
- creates flat per-skill symlinks for Claude and Codex;
- includes `shared-references` as a support symlink;
- removes stale runtime-local files under `.claude/` and `.agents/`;
- links shared resources under `.squrve/`;
- writes `.squrve/installed-harness.txt`.

## ARIS Philosophy Applied

- Markdown is the interface.
- Bash only bridges source files into host-discoverable locations.
- Python helpers are deterministic tools, not the workflow runtime.
- Single-owner helpers belong under `skills/<name>/scripts/`.
- Shared helpers belong under `tools/`.
- Reusable output/input skeletons belong under `templates/`.

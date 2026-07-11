#!/usr/bin/env bash
# sync-from-claude.sh — compatibility wrapper for the Squrve skill harness.
#
# Squrve no longer mirrors Claude-side files into Codex-side files. Both agents
# read the same SKILL.md sources via flat symlinks under .claude/skills and
# .agents/skills.

set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

bash harness/install_squrve_harness.sh . "$@"
bash harness/update_squrve_harness.sh --project .

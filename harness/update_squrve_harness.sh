#!/usr/bin/env bash
# update_squrve_harness.sh — diagnostic check for the Squrve workbench harness.

set -euo pipefail

PROJECT_PATH="."

usage() {
  cat <<'EOF'
update_squrve_harness.sh — check Squrve workbench symlinks

Usage:
  bash harness/update_squrve_harness.sh [--project .]
EOF
  exit 0
}

while [ $# -gt 0 ]; do
  case "$1" in
    --project) PROJECT_PATH="${2:?--project requires path}"; shift 2 ;;
    -h|--help) usage ;;
    --*) echo "error: unsupported option: $1" >&2; exit 2 ;;
    *) echo "error: unexpected positional: $1" >&2; exit 2 ;;
  esac
done

PROJECT_PATH="$(cd "$PROJECT_PATH" && pwd)"
[ -d "$PROJECT_PATH/skills" ] || { echo "error: not a Squrve repo: $PROJECT_PATH" >&2; exit 1; }

list_skills() {
  local d name
  for d in "$PROJECT_PATH"/skills/*; do
    [ -d "$d" ] || continue
    name="$(basename "$d")"
    if [ "$name" = "shared-references" ] || [ -f "$d/SKILL.md" ]; then
      printf '%s\n' "$name"
    fi
  done | sort
}

check_platform() {
  local platform rel_dir ok=0 bad=0 missing=0 extra=0 name target expected existing base
  platform="$1"
  case "$platform" in
    claude) rel_dir=".claude/skills" ;;
    codex) rel_dir=".agents/skills" ;;
  esac

  echo "$platform: $rel_dir"
  while IFS= read -r name; do
    target="$PROJECT_PATH/$rel_dir/$name"
    expected="../../skills/$name"
    if [ ! -e "$target" ] && [ ! -L "$target" ]; then
      echo "  missing: $name"
      missing=$((missing + 1))
    elif [ ! -L "$target" ]; then
      echo "  not-symlink: $name"
      bad=$((bad + 1))
    elif [ "$(readlink "$target")" != "$expected" ]; then
      echo "  wrong-target: $name -> $(readlink "$target")"
      bad=$((bad + 1))
    else
      ok=$((ok + 1))
    fi
  done < "$SKILL_LIST"

  if [ -d "$PROJECT_PATH/$rel_dir" ]; then
    for existing in "$PROJECT_PATH/$rel_dir"/*; do
      [ -e "$existing" ] || [ -L "$existing" ] || continue
      base="$(basename "$existing")"
      if ! grep -qxF "$base" "$SKILL_LIST"; then
        echo "  extra: $base"
        extra=$((extra + 1))
      fi
    done
  fi
  echo "  ok=$ok missing=$missing bad=$bad extra=$extra"
  return $((missing + bad + extra))
}

SKILL_LIST="$(mktemp -t squrve-skill-list.XXXX)"
trap 'rm -f "$SKILL_LIST"' EXIT
list_skills > "$SKILL_LIST"

echo "Squrve workbench harness check"
echo "  Repo: $PROJECT_PATH"
echo "  Skill/support entries: $(wc -l < "$SKILL_LIST" | tr -d ' ')"
echo ""

status=0
check_platform claude || status=1
check_platform codex || status=1

for res in tools templates; do
  if [ -d "$PROJECT_PATH/$res" ]; then
    link="$PROJECT_PATH/.squrve/$res"
    if [ -L "$link" ] && [ "$(readlink "$link")" = "../$res" ]; then
      echo "resource: .squrve/$res ok"
    else
      echo "resource: .squrve/$res missing-or-wrong"
      status=1
    fi
  fi
done

exit "$status"

#!/usr/bin/env bash
# install_squrve_harness.sh — SqurveBridge workbench skill harness.
#
# Squrve is a complete workbench. This script runs inside the Squrve repo and
# creates ARIS-style flat skill symlinks:
#   .claude/skills/<name> -> ../../skills/<name>
#   .agents/skills/<name> -> ../../skills/<name>
#
# It also exposes repo helpers as workbench resources:
#   .squrve/tools     -> ../tools
#   .squrve/templates -> ../templates
#
# Usage:
#   bash harness/install_squrve_harness.sh [.] [--dry-run] [--quiet] [--reconcile] [--clear-stale-lock]

set -euo pipefail

MANIFEST_VERSION="1"
SQURVE_DIR_NAME=".squrve"
MANIFEST_NAME="installed-harness.txt"
MANIFEST_PREV_NAME="installed-harness.txt.prev"
LOCK_DIR_NAME=".install.lock.d"
SAFE_NAME_REGEX='^[A-Za-z0-9][A-Za-z0-9._-]*$'
PLATFORMS="claude codex"

PROJECT_PATH=""
ACTION="auto"
DRY_RUN=false
QUIET=false
CLEAR_STALE_LOCK=false

usage() {
  sed -n '2,16p' "$0" | sed 's/^# \?//'
  exit 0
}

while [ $# -gt 0 ]; do
  case "$1" in
    --reconcile) ACTION="reconcile"; shift ;;
    --uninstall) echo "error: --uninstall is not supported for the Squrve workbench" >&2; exit 2 ;;
    --dry-run) DRY_RUN=true; shift ;;
    --quiet) QUIET=true; shift ;;
    --no-doc) shift ;; # kept for compatibility; docs are not mutated
    --clear-stale-lock) CLEAR_STALE_LOCK=true; shift ;;
    -h|--help) usage ;;
    --*) echo "error: unsupported option: $1" >&2; exit 2 ;;
    *)
      if [ -z "$PROJECT_PATH" ]; then PROJECT_PATH="$1"
      else echo "error: unexpected positional: $1" >&2; exit 2; fi
      shift
      ;;
  esac
done

log() { $QUIET && return 0; echo "$@"; }
warn() { echo "warning: $*" >&2; }
die() { echo "error: $*" >&2; exit 1; }
is_safe_name() { echo "$1" | grep -qE "$SAFE_NAME_REGEX"; }
is_symlink() { [ -L "$1" ]; }

read_link_target() {
  if command -v greadlink >/dev/null 2>&1; then greadlink "$1"
  else readlink "$1"; fi
}

abs_path() { ( cd "$1" 2>/dev/null && pwd ) || return 1; }

repo_root() {
  local sd parent
  sd="$(cd "$(dirname "$0")" && pwd)"
  parent="$(cd "$sd/.." && pwd)"
  [ -d "$parent/skills" ] && [ -d "$parent/tools" ] || die "script is not inside a Squrve repo"
  printf '%s' "$parent"
}

platform_skills_dir() {
  case "$1" in
    claude) printf '.claude/skills' ;;
    codex) printf '.agents/skills' ;;
  esac
}

acquire_lock() {
  mkdir -p "$SQURVE_STATE_DIR"
  if mkdir "$LOCK_DIR" 2>/dev/null; then
    printf '%s\n' "$$" > "$LOCK_DIR/owner.pid"
    trap release_lock EXIT INT TERM
    return 0
  fi
  if $CLEAR_STALE_LOCK; then
    warn "removing stale lock: $LOCK_DIR"
    rm -rf "$LOCK_DIR"
    mkdir "$LOCK_DIR" || die "cannot acquire lock after stale clear"
    printf '%s\n' "$$" > "$LOCK_DIR/owner.pid"
    trap release_lock EXIT INT TERM
    return 0
  fi
  die "another harness setup is running (lock: $LOCK_DIR)"
}

release_lock() {
  [ -d "$LOCK_DIR" ] || return 0
  [ "$(cat "$LOCK_DIR/owner.pid" 2>/dev/null || true)" = "$$" ] && rm -rf "$LOCK_DIR"
}

list_skills() {
  local d name
  for d in "$SQURVE_REPO"/skills/*; do
    [ -d "$d" ] || continue
    name="$(basename "$d")"
    is_safe_name "$name" || { warn "skip unsafe skill name: $name"; continue; }
    if [ "$name" = "shared-references" ]; then
      printf 'support\t%s\tskills/%s\n' "$name" "$name"
      continue
    fi
    [ -f "$d/SKILL.md" ] || continue
    printf 'skill\t%s\tskills/%s\n' "$name" "$name"
  done | sort -t "$(printf '\t')" -k2,2
}

ensure_runtime_dirs() {
  local p dir entry
  for p in .claude .agents; do
    if [ -e "$PROJECT_PATH/$p" ] && ! [ -d "$PROJECT_PATH/$p" ]; then
      $DRY_RUN && log "  (dry-run) replace $p with directory" || rm -f "$PROJECT_PATH/$p"
    fi
    $DRY_RUN || mkdir -p "$PROJECT_PATH/$p"
    for entry in "$PROJECT_PATH/$p"/* "$PROJECT_PATH/$p"/.[!.]* "$PROJECT_PATH/$p"/..?*; do
      [ -e "$entry" ] || [ -L "$entry" ] || continue
      [ "$(basename "$entry")" = "skills" ] && continue
      if $DRY_RUN; then log "  (dry-run) remove $p/$(basename "$entry")"
      else rm -rf "$entry"; log "  - removed $p/$(basename "$entry")"; fi
    done
  done
  for dir in .claude/skills .agents/skills; do
    if [ -L "$PROJECT_PATH/$dir" ] || { [ -e "$PROJECT_PATH/$dir" ] && ! [ -d "$PROJECT_PATH/$dir" ]; }; then
      $DRY_RUN && log "  (dry-run) replace $dir with directory" || rm -rf "$PROJECT_PATH/$dir"
    fi
    $DRY_RUN || mkdir -p "$PROJECT_PATH/$dir"
  done
}

sync_platform_skills() {
  local platform rel_dir target_dir kind name source_rel target expected cur
  platform="$1"
  rel_dir="$(platform_skills_dir "$platform")"
  target_dir="$PROJECT_PATH/$rel_dir"

  while IFS="$(printf '\t')" read -r kind name source_rel; do
    [ -n "$name" ] || continue
    target="$target_dir/$name"
    expected="../../$source_rel"
    if [ -L "$target" ]; then
      cur="$(read_link_target "$target")"
      if [ "$cur" = "$expected" ]; then
        continue
      fi
      $DRY_RUN && log "  (dry-run) relink $rel_dir/$name -> $expected" || { rm -f "$target"; ln -s "$expected" "$target"; log "  ↻ $rel_dir/$name"; }
    elif [ -e "$target" ]; then
      die "$rel_dir/$name exists and is not a symlink"
    else
      $DRY_RUN && log "  (dry-run) link $rel_dir/$name -> $expected" || { ln -s "$expected" "$target"; log "  + $rel_dir/$name"; }
    fi
  done < "$INVENTORY_FILE"

  local existing base keep
  for existing in "$target_dir"/*; do
    [ -e "$existing" ] || [ -L "$existing" ] || continue
    base="$(basename "$existing")"
    keep=false
    awk -F "$(printf '\t')" -v n="$base" '$2==n {found=1} END{exit found?0:1}' "$INVENTORY_FILE" && keep=true
    $keep && continue
    if [ -L "$existing" ]; then
      $DRY_RUN && log "  (dry-run) remove stale $rel_dir/$base" || { rm -f "$existing"; log "  - $rel_dir/$base"; }
    else
      die "$rel_dir/$base is local-only real path"
    fi
  done
}

ensure_resource_links() {
  local name target expected
  for name in tools templates; do
    [ -d "$PROJECT_PATH/$name" ] || continue
    target="$PROJECT_PATH/.squrve/$name"
    expected="../$name"
    if [ -L "$target" ] && [ "$(read_link_target "$target")" = "$expected" ]; then
      continue
    fi
    if [ -e "$target" ] || [ -L "$target" ]; then
      $DRY_RUN && log "  (dry-run) replace .squrve/$name" || rm -rf "$target"
    fi
    $DRY_RUN && log "  (dry-run) link .squrve/$name -> $expected" || { ln -s "$expected" "$target"; log "  + .squrve/$name -> $expected"; }
  done
}

write_manifest() {
  local tmp kind name source_rel platform rel_dir
  tmp="$MANIFEST_PATH.tmp.$$"
  {
    printf 'version\t%s\n' "$MANIFEST_VERSION"
    printf 'repo_root\t%s\n' "$SQURVE_REPO"
    printf 'generated\t%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
    printf 'kind\tname\tsource_rel\ttarget_rel\tmode\n'
    while IFS="$(printf '\t')" read -r kind name source_rel; do
      for platform in $PLATFORMS; do
        rel_dir="$(platform_skills_dir "$platform")"
        printf '%s\t%s\t%s\t%s/%s\tsymlink\n' "$kind" "$name" "$source_rel" "$rel_dir" "$name"
      done
    done < "$INVENTORY_FILE"
    [ -d "$PROJECT_PATH/tools" ] && printf 'resource\ttools\ttools\t.squrve/tools\tsymlink\n'
    [ -d "$PROJECT_PATH/templates" ] && printf 'resource\ttemplates\ttemplates\t.squrve/templates\tsymlink\n'
  } > "$tmp"
  if $DRY_RUN; then rm -f "$tmp"; return 0; fi
  [ -f "$MANIFEST_PATH" ] && cp -p "$MANIFEST_PATH" "$MANIFEST_PREV"
  mv -f "$tmp" "$MANIFEST_PATH"
}

PROJECT_PATH="${PROJECT_PATH:-$(pwd)}"
[ -d "$PROJECT_PATH" ] || die "project path does not exist: $PROJECT_PATH"
PROJECT_PATH="$(abs_path "$PROJECT_PATH")"
SQURVE_REPO="$(repo_root)"
[ "$PROJECT_PATH" = "$SQURVE_REPO" ] || die "Squrve harness is workbench-local; run from repo root with: bash harness/install_squrve_harness.sh ."

SQURVE_STATE_DIR="$PROJECT_PATH/$SQURVE_DIR_NAME"
MANIFEST_PATH="$SQURVE_STATE_DIR/$MANIFEST_NAME"
MANIFEST_PREV="$SQURVE_STATE_DIR/$MANIFEST_PREV_NAME"
LOCK_DIR="$SQURVE_STATE_DIR/$LOCK_DIR_NAME"

log "Squrve workbench harness"
log "  Repo:   $SQURVE_REPO"
log "  Action: $ACTION$($DRY_RUN && printf ' (dry-run)')"

acquire_lock

INVENTORY_FILE="$(mktemp -t squrve-skills.XXXX)"
list_skills > "$INVENTORY_FILE"
[ -s "$INVENTORY_FILE" ] || die "no skills found"

ensure_runtime_dirs
for platform in $PLATFORMS; do
  sync_platform_skills "$platform"
done
ensure_resource_links
write_manifest

count="$(wc -l < "$INVENTORY_FILE" | tr -d ' ')"
rm -f "$INVENTORY_FILE"

if $DRY_RUN; then
  log "(dry-run) $count skill/support entries checked"
else
  log "  ✓ harness ready: $count skill/support entries x 2 platforms"
fi

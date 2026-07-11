"""Rollout utilities for Meta-Evo MCTS."""

from __future__ import annotations

import json
import os
import shutil
import shlex
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from reproduce.metrics.evolution_pkg.state_machine import classify_scope_c
from reproduce.metrics.mcts.expand import Action


def apply_action(repo_root: str | Path, action: Action, *, allow_scope_c: bool = False) -> dict:
    repo_root = Path(repo_root)
    gate = classify_scope_c(action)
    if gate and not allow_scope_c:
        raise PermissionError(f"Scope C action requires human gate approval: {gate}")
    applied = []
    for patch in action.patches:
        rel_path = Path(patch["path"])
        target = (repo_root / rel_path).resolve()
        if repo_root.resolve() not in target.parents and target != repo_root.resolve():
            raise ValueError(f"Patch path escapes repo root: {rel_path}")
        old = patch["old_string"]
        new = patch["new_string"]
        content = target.read_text(encoding="utf-8")
        if old not in content:
            raise ValueError(f"old_string not found in {rel_path}")
        target.write_text(content.replace(old, new, 1), encoding="utf-8")
        applied.append(str(rel_path))
    return {"action_id": action.action_id, "applied": len(applied), "files": applied}


def score_from_scores(scores: dict, metric_path: str) -> float | None:
    if metric_path in {"ex", "em", "sf1", "sc", "ves"}:
        metric_path = f"{metric_path}.avg"
    current: Any = scores
    parts = metric_path.split(".")
    if parts and parts[0] != "aggregate":
        parts = ["aggregate", *parts]
    for part in parts:
        if not isinstance(current, dict) or part not in current:
            return None
        current = current[part]
    return current if isinstance(current, (int, float)) else None


def rollout_verdict(
        *,
        baseline: float | None,
        current: float | None,
        dry_threshold: float = 0.01,
        regression_threshold: float = 0.02,
) -> dict:
    if baseline is None or current is None:
        return {"verdict": "STOP", "delta": None, "reason": "missing metric"}
    delta = current - baseline
    if delta <= -regression_threshold:
        verdict = "REGRESSION"
    elif delta < dry_threshold:
        verdict = "DRY"
    else:
        verdict = "CONTINUE"
    return {"verdict": verdict, "delta": delta, "baseline": baseline, "current": current}


def run_command(command: list[str], cwd: str | Path, env: dict[str, str] | None = None) -> subprocess.CompletedProcess:
    merged_env = os.environ.copy()
    if env:
        merged_env.update(env)
    return subprocess.run(command, cwd=str(cwd), text=True, capture_output=True, check=False, env=merged_env)


def split_env_prefix(command: str | list[str]) -> tuple[dict[str, str], list[str]]:
    parts = shlex.split(command) if isinstance(command, str) else list(command)
    env = {}
    while parts and _is_env_assignment(parts[0]):
        key, value = parts.pop(0).split("=", 1)
        env[key] = value
    return env, parts


def _is_env_assignment(value: str) -> bool:
    if "=" not in value or value.startswith("="):
        return False
    key = value.split("=", 1)[0]
    return key.replace("_", "").isalnum() and not key[0].isdigit()


def load_scores(path: str | Path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def create_worktree(repo_root: str | Path, base_ref: str = "HEAD") -> Path:
    repo_root = Path(repo_root).resolve()
    target = Path(tempfile.mkdtemp(prefix="squrve-mcts-"))
    result = run_command(["git", "worktree", "add", "--detach", str(target), base_ref], cwd=repo_root)
    if result.returncode != 0:
        raise RuntimeError(result.stderr or result.stdout)
    return target


def remove_worktree(repo_root: str | Path, worktree: str | Path) -> None:
    result = run_command(["git", "worktree", "remove", "--force", str(worktree)], cwd=repo_root)
    if result.returncode != 0:
        raise RuntimeError(result.stderr or result.stdout)


def run_action_rollout(
        *,
        repo_root: str | Path,
        action: Action,
        smoke_command: str | list[str],
        scores_path: str | Path,
        metric: str,
        baseline_score: float | None,
        base_ref: str = "HEAD",
        env: dict[str, str] | None = None,
        copy_scores_to: str | Path | None = None,
        allow_scope_c: bool = False,
) -> dict:
    worktree = create_worktree(repo_root, base_ref=base_ref)
    try:
        apply_result = apply_action(worktree, action, allow_scope_c=allow_scope_c)
        inline_env, command = split_env_prefix(smoke_command)
        run_result = run_command(command, cwd=worktree, env={**inline_env, **(env or {})})
        if run_result.returncode != 0:
            return {
                "action_id": action.action_id,
                "score": None,
                "verdict": {"verdict": "STOP", "reason": run_result.stderr or run_result.stdout},
                "apply": apply_result,
            }
        source_scores_path = worktree / scores_path
        scores = load_scores(source_scores_path)
        if copy_scores_to:
            target = Path(copy_scores_to)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source_scores_path, target)
        score = score_from_scores(scores, metric)
        return {
            "action_id": action.action_id,
            "score": score,
            "scores": scores,
            "verdict": rollout_verdict(baseline=baseline_score, current=score),
            "apply": apply_result,
        }
    finally:
        remove_worktree(repo_root, worktree)

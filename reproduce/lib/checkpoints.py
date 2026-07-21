"""Run-local checkpoint path resolution for SqurveBridge reproduce runs."""

from __future__ import annotations

import json
import os
from pathlib import Path

from reproduce.lib.paths import PROJECT_ROOT


def state_filename(iteration: int) -> str:
    if iteration < 1:
        raise ValueError("checkpoint iteration must be >= 1")
    return "state.json" if iteration == 1 else f"state-{iteration}.json"


def resolve_checkpoint_state_path(
        checkpoint_dir: str | Path,
        resume_from: str | Path | None,
        iteration: int = 1,
) -> Path:
    """Resolve all iteration states inside a single run-local checkpoint root."""
    checkpoint_root = Path(checkpoint_dir)
    if resume_from is not None:
        candidate = Path(resume_from).expanduser().resolve()
        checkpoint_root = candidate if candidate.is_dir() else candidate.parent
    return checkpoint_root / state_filename(iteration)


def select_resume_checkpoint(
        identifier: str,
        resume_from: str | Path | None,
        *,
        project_root: str | Path = PROJECT_ROOT,
) -> Path:
    """Select an explicit state file or the newest run-local state for an identifier."""
    if resume_from is not None:
        candidate = Path(resume_from).expanduser()
        if not candidate.is_absolute():
            candidate = (Path.cwd() / candidate).resolve()
        if candidate.is_dir():
            candidate = candidate / "state.json"
        if not candidate.is_file():
            raise FileNotFoundError(f"checkpoint state does not exist: {candidate}")
        _require_checkpoint_identifier(candidate, identifier)
        return candidate

    runs_root = Path(project_root) / "workspace" / "runs"
    # Allow SQURVE_WORKSPACE_DIR override without importing demo at module load in tests.
    configured = os.environ.get("SQURVE_WORKSPACE_DIR", "").strip()
    if configured:
        runs_root = Path(configured).expanduser().resolve() / "runs"
    candidates = sorted(
        (
            path
            for path in runs_root.glob("*/checkpoints/state.json")
            if _checkpoint_matches_identifier(path, identifier)
        ),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    if not candidates:
        raise FileNotFoundError(f"no resumable checkpoint run: {identifier}")
    return candidates[0]


def _checkpoint_metadata(state_path: Path) -> dict:
    try:
        data = json.loads(state_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"checkpoint state is unreadable: {state_path}") from exc
    if not isinstance(data, dict) or not isinstance(data.get("run_id"), str):
        raise ValueError(f"checkpoint state has no run_id metadata: {state_path}")
    return data


def _checkpoint_matches_identifier(state_path: Path, identifier: str) -> bool:
    try:
        state_run_id = _checkpoint_metadata(state_path)["run_id"]
    except ValueError:
        return False
    return state_run_id == identifier or state_run_id.startswith(f"{identifier}-")


def _require_checkpoint_identifier(state_path: Path, identifier: str) -> None:
    if not _checkpoint_matches_identifier(state_path, identifier):
        state_run_id = _checkpoint_metadata(state_path)["run_id"]
        raise ValueError(
            f"checkpoint belongs to {state_run_id!r}, expected {identifier!r}: {state_path}"
        )


def checkpoint_run_id(state_path: str | Path) -> str:
    """Extract <run-id> from workspace/runs/<run-id>/checkpoints/state*.json."""
    path = Path(state_path).expanduser().resolve()
    if path.parent.name != "checkpoints" or path.parent.parent.parent.name != "runs":
        raise ValueError(f"checkpoint is outside the run-local layout: {path}")
    return path.parent.parent.name

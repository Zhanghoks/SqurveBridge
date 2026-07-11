"""Reproduce path helpers.

Layout:
  reproduce/configs/<dataset>/<method>.json
Run identifier (artifacts / saved datasets): <dataset>-<method>
"""

from __future__ import annotations

from pathlib import Path

REPRODUCE_ROOT = Path(__file__).resolve().parent.parent
PROJECT_ROOT = REPRODUCE_ROOT.parent


def run_identifier(dataset: str, method: str) -> str:
    return f"{dataset}-{method}"


def config_filename(dataset: str, method: str) -> str:
    return f"configs/{dataset}/{method}.json"


def config_repo_path(dataset: str, method: str) -> Path:
    return REPRODUCE_ROOT / "configs" / dataset / f"{method}.json"


CHECKPOINT_ROOT = PROJECT_ROOT / "files" / "checkpoints"


def checkpoint_dir(dataset: str, method: str) -> Path:
    """Root checkpoint directory for a given dataset-method run."""
    return CHECKPOINT_ROOT / f"{dataset}-{method}"


def checkpoint_state_path(dataset: str, method: str, iteration: int = 1) -> Path:
    """Path to state.json, or state-{n}.json for iteration > 1."""
    root = checkpoint_dir(dataset, method)
    if iteration > 1:
        return root / f"state-{iteration}.json"
    return root / "state.json"


def checkpoint_datasets_dir(dataset: str, method: str) -> Path:
    """Directory holding incremental dataset snapshots."""
    return checkpoint_dir(dataset, method) / "datasets"

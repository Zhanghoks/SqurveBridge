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

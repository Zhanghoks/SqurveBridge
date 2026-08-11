"""Single import point for evaluation-facing filesystem roots.

Workspace-tree paths delegate to ``demo.workspace`` (the runtime authority for
``SQURVE_WORKSPACE_DIR``). Repo-side roots that the evaluation system reads or
validates are defined here so that no other module hardcodes them.

Three distinct roots exist and must not be conflated:

- ``workspace/artifacts/``: evaluation score bundles and the eval store
  (runner-owned, gitignored).
- ``files/``: stage datasets and SQL outputs declared by reproduce configs.
- ``artifacts/<slug>/``: integration-harness state for candidate onboarding
  (owned by ``tools/artifact_state.py``).
"""

from __future__ import annotations

from pathlib import Path

from demo.workspace import (
    WORKSPACE_ENV,
    artifacts_dir,
    eval_store_path,
    project_root,
    runs_dir,
    workspace_root,
)

__all__ = [
    "WORKSPACE_ENV",
    "allowed_config_output_roots",
    "artifacts_dir",
    "eval_store_path",
    "evidence_root",
    "files_root",
    "integration_artifacts_root",
    "project_root",
    "runs_dir",
    "workspace_root",
]


def files_root() -> Path:
    """Root for stage datasets and SQL outputs referenced by configs."""
    return project_root() / "files"


def evidence_root() -> Path:
    """Published, checksummed score bundles."""
    return project_root() / "evidence" / "reported-results"


def integration_artifacts_root() -> Path:
    """Integration-harness state written by tools/artifact_state.py."""
    return project_root() / "artifacts"


def allowed_config_output_roots() -> tuple[Path, ...]:
    """Roots a reproduce config may target for stage outputs."""
    return (files_root(),)

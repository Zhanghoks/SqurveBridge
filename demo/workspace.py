"""Unified runtime workspace root for Demo, reproduce, and HF Space.

Layout (all under ``SQURVE_WORKSPACE_DIR``, default ``<repo>/workspace``)::

    workspace/
      sessions/
        evaluations/   # Demo evaluation jobs + score-bundles
        runtime/       # start.sh pid/log files
        pi-agent/      # embedded Pi agentDir
      runs/            # reproduce intermediate outputs + checkpoints
      artifacts/       # CLI score bundles, eval-store.sqlite, evolve
      uploads/         # user-uploaded databases and temp demo data

Published evidence under ``evidence/`` and benchmark packages stay outside
this tree. Nothing under workspace/ is committed except ``README.md``.
"""

from __future__ import annotations

import os
from pathlib import Path

WORKSPACE_ENV = "SQURVE_WORKSPACE_DIR"

_PROJECT_ROOT = Path(__file__).resolve().parent.parent


def project_root() -> Path:
    return _PROJECT_ROOT


def workspace_root(environment: dict[str, str] | None = None) -> Path:
    """Resolve the workspace root from env or ``<repo>/workspace``."""
    values = os.environ if environment is None else environment
    configured = str(values.get(WORKSPACE_ENV) or "").strip()
    if configured:
        return Path(configured).expanduser().resolve()
    return (_PROJECT_ROOT / "workspace").resolve()


def sessions_dir(environment: dict[str, str] | None = None) -> Path:
    return workspace_root(environment) / "sessions"


def evaluations_dir(environment: dict[str, str] | None = None) -> Path:
    return sessions_dir(environment) / "evaluations"


def runtime_dir(environment: dict[str, str] | None = None) -> Path:
    return sessions_dir(environment) / "runtime"


def pi_agent_dir(environment: dict[str, str] | None = None) -> Path:
    return sessions_dir(environment) / "pi-agent"


def runs_dir(environment: dict[str, str] | None = None) -> Path:
    return workspace_root(environment) / "runs"


def run_dir(run_id: str, environment: dict[str, str] | None = None) -> Path:
    return runs_dir(environment) / run_id


def artifacts_dir(environment: dict[str, str] | None = None) -> Path:
    return workspace_root(environment) / "artifacts"


def eval_store_path(environment: dict[str, str] | None = None) -> Path:
    return artifacts_dir(environment) / "eval-store.sqlite"


def uploads_dir(environment: dict[str, str] | None = None) -> Path:
    return workspace_root(environment) / "uploads"


def uploaded_db_dir(environment: dict[str, str] | None = None) -> Path:
    return uploads_dir(environment) / "uploaded_db"


def temp_data_dir(environment: dict[str, str] | None = None) -> Path:
    return uploads_dir(environment) / "temp_demo_data"


def ensure_layout(environment: dict[str, str] | None = None) -> Path:
    """Create the standard workspace subdirectories and return the root."""
    root = workspace_root(environment)
    for path in (
        evaluations_dir(environment),
        runtime_dir(environment),
        pi_agent_dir(environment),
        runs_dir(environment),
        artifacts_dir(environment),
        uploaded_db_dir(environment),
        temp_data_dir(environment),
    ):
        path.mkdir(parents=True, exist_ok=True)
    return root

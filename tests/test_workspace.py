"""Workspace layout helpers."""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from demo import workspace


class WorkspaceLayoutTests(unittest.TestCase):
    def test_default_root_is_repo_workspace(self):
        with patch_env({}):
            root = workspace.workspace_root({})
        self.assertEqual(root, (workspace.project_root() / "workspace").resolve())

    def test_env_override_and_layout(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            configured = Path(temp_dir) / "data" / "workspace"
            env = {"SQURVE_WORKSPACE_DIR": str(configured)}
            root = workspace.ensure_layout(env)
            self.assertEqual(root, configured.resolve())
            self.assertTrue(workspace.evaluations_dir(env).is_dir())
            self.assertTrue(workspace.runs_dir(env).is_dir())
            self.assertTrue(workspace.artifacts_dir(env).is_dir())
            self.assertTrue(workspace.uploaded_db_dir(env).is_dir())
            self.assertEqual(
                workspace.eval_store_path(env),
                configured.resolve() / "artifacts" / "eval-store.sqlite",
            )


class _EnvPatch:
    def __init__(self, values: dict[str, str]):
        self.values = values
        self._previous = None

    def __enter__(self):
        self._previous = os.environ.get(workspace.WORKSPACE_ENV)
        if workspace.WORKSPACE_ENV in self.values:
            os.environ[workspace.WORKSPACE_ENV] = self.values[workspace.WORKSPACE_ENV]
        else:
            os.environ.pop(workspace.WORKSPACE_ENV, None)
        return self

    def __exit__(self, *args):
        if self._previous is None:
            os.environ.pop(workspace.WORKSPACE_ENV, None)
        else:
            os.environ[workspace.WORKSPACE_ENV] = self._previous


def patch_env(values: dict[str, str]) -> _EnvPatch:
    return _EnvPatch(values)


if __name__ == "__main__":
    unittest.main()

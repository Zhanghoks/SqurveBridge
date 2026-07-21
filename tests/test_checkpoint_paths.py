# Checkpoint path tests use the unified workspace/runs layout.

import os
import json
import tempfile
import time
import unittest
from pathlib import Path

from reproduce.lib.checkpoints import (
    checkpoint_run_id,
    resolve_checkpoint_state_path,
    select_resume_checkpoint,
    state_filename,
)


class CheckpointPathTests(unittest.TestCase):
    @staticmethod
    def _write_state(path: Path, identifier: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps({"run_id": f"{identifier}-20260713-120000-1"}),
            encoding="utf-8",
        )

    def test_iteration_states_share_one_run_local_directory(self):
        root = Path("workspace/runs/spider-c3sql-20260712/checkpoints")

        self.assertEqual(resolve_checkpoint_state_path(root, None, 1), root / "state.json")
        self.assertEqual(resolve_checkpoint_state_path(root, None, 2), root / "state-2.json")
        self.assertEqual(state_filename(3), "state-3.json")

    def test_explicit_resume_reuses_original_run_for_every_iteration(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            run_dir = Path(temp_dir) / "workspace" / "runs" / "spider-c3sql-old" / "checkpoints"
            state = run_dir / "state.json"
            self._write_state(state, "spider-c3sql")

            selected = select_resume_checkpoint("spider-c3sql", state)

            self.assertEqual(selected, state)
            self.assertEqual(checkpoint_run_id(selected), "spider-c3sql-old")
            self.assertEqual(
                resolve_checkpoint_state_path(run_dir, selected, 2),
                run_dir.resolve() / "state-2.json",
            )

    def test_default_resume_selects_newest_matching_run(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            older = root / "workspace" / "runs" / "spider-c3sql-older" / "checkpoints" / "state.json"
            newer = root / "workspace" / "runs" / "spider-c3sql-newer" / "checkpoints" / "state.json"
            self._write_state(older, "spider-c3sql")
            self._write_state(newer, "spider-c3sql")
            now = time.time()
            os.utime(older, (now - 10, now - 10))
            os.utime(newer, (now, now))

            with patch_workspace(root):
                selected = select_resume_checkpoint("spider-c3sql", None, project_root=root)

            self.assertEqual(selected, newer.resolve())

    def test_explicit_resume_rejects_another_method_checkpoint(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            state = Path(temp_dir) / "workspace" / "runs" / "bird-esql-run" / "checkpoints" / "state.json"
            self._write_state(state, "bird-e-sql")

            with self.assertRaisesRegex(ValueError, "expected 'spider-c3sql'"):
                select_resume_checkpoint("spider-c3sql", state)

    def test_default_resume_supports_custom_run_directory_name(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            custom = root / "workspace" / "runs" / "reviewer-demo-42" / "checkpoints" / "state.json"
            unrelated = root / "workspace" / "runs" / "spider-c3sql-looking-but-wrong" / "checkpoints" / "state.json"
            self._write_state(custom, "spider-c3sql")
            self._write_state(unrelated, "bird-e-sql")
            now = time.time()
            os.utime(custom, (now - 10, now - 10))
            os.utime(unrelated, (now, now))

            with patch_workspace(root):
                selected = select_resume_checkpoint("spider-c3sql", None, project_root=root)

            self.assertEqual(selected, custom.resolve())

    def test_parallel_method_runs_keep_distinct_checkpoint_roots(self):
        first = resolve_checkpoint_state_path("workspace/runs/spider-c3sql-001/checkpoints", None)
        second = resolve_checkpoint_state_path("workspace/runs/spider-c3sql-002/checkpoints", None)

        self.assertNotEqual(first, second)

    def test_rejects_checkpoint_outside_run_layout(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "workspace" / "checkpoints" / "spider-c3sql" / "state.json"
            self._write_state(path, "spider-c3sql")

            with self.assertRaises(ValueError):
                checkpoint_run_id(path)

    def test_missing_resume_target_fails_loudly(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            with patch_workspace(temp_dir):
                with self.assertRaises(FileNotFoundError):
                    select_resume_checkpoint("spider-c3sql", None, project_root=temp_dir)


class _WorkspaceEnv:
    def __init__(self, root: str | Path):
        self.root = Path(root)
        self._previous = None

    def __enter__(self):
        self._previous = os.environ.get("SQURVE_WORKSPACE_DIR")
        os.environ["SQURVE_WORKSPACE_DIR"] = str(self.root / "workspace")
        return self

    def __exit__(self, *args):
        if self._previous is None:
            os.environ.pop("SQURVE_WORKSPACE_DIR", None)
        else:
            os.environ["SQURVE_WORKSPACE_DIR"] = self._previous


def patch_workspace(root: str | Path) -> _WorkspaceEnv:
    return _WorkspaceEnv(root)


if __name__ == "__main__":
    unittest.main()

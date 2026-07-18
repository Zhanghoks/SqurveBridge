import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from demo import api_server


class EvaluationResumeTests(unittest.TestCase):
    def setUp(self):
        self.temp_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_directory.name)
        self.run_dir = self.root / "tmp" / "demo-runs"
        self.job = {
            "job_id": "resumejob1",
            "dataset": "spider",
            "method": "c3sql",
            "sample_limit": 3,
            "sample_mode": "slice",
            "sample_seed": 42,
            "status": "running",
            "resume_count": 0,
            "max_resume_attempts": 2,
        }
        self.patches = (
            patch.object(api_server, "_project_root", self.root),
            patch.object(api_server, "_run_dir", self.run_dir),
            patch.object(api_server, "_resume_backoff_seconds", 0),
            patch.object(api_server, "_max_resume_attempts", 2),
        )
        for item in self.patches:
            item.start()
        api_server._jobs = {self.job["job_id"]: dict(self.job)}
        api_server._processes = {self.job["job_id"]: Mock()}

    def tearDown(self):
        for item in reversed(self.patches):
            item.stop()
        self.temp_directory.cleanup()

    def _write_checkpoint(self):
        checkpoint = (
            self.root
            / "files"
            / "runs"
            / "spider-c3sql-resumejob1"
            / "checkpoints"
            / "state.json"
        )
        checkpoint.parent.mkdir(parents=True)
        checkpoint.write_text('{"run_id":"spider-c3sql-resumejob1"}', encoding="utf-8")
        return checkpoint

    def test_failed_process_schedules_a_bounded_checkpoint_resume(self):
        self._write_checkpoint()
        process = Mock()
        process.wait.return_value = 1
        thread = Mock()

        with patch.object(api_server.threading, "Thread", return_value=thread):
            api_server._monitor_job(
                self.job["job_id"],
                process,
                io.StringIO(),
                self.run_dir / self.job["job_id"] / "score-bundle" / "scores.json",
            )

        restored = api_server._jobs[self.job["job_id"]]
        self.assertEqual(restored["status"], "resuming")
        self.assertEqual(restored["last_return_code"], 1)
        self.assertTrue((self.run_dir / self.job["job_id"] / "job.json").is_file())
        thread.start.assert_called_once()

    def test_failure_without_checkpoint_stays_failed(self):
        process = Mock()
        process.wait.return_value = 1

        api_server._monitor_job(
            self.job["job_id"],
            process,
            io.StringIO(),
            self.run_dir / self.job["job_id"] / "score-bundle" / "scores.json",
        )

        self.assertEqual(api_server._jobs[self.job["job_id"]]["status"], "failed")

    def test_restart_loads_job_metadata_and_schedules_resume(self):
        self._write_checkpoint()
        job_path = self.run_dir / self.job["job_id"] / "job.json"
        job_path.parent.mkdir(parents=True)
        job_path.write_text(json.dumps(self.job), encoding="utf-8")
        api_server._jobs = {}
        api_server._jobs_restored = False
        thread = Mock()

        with patch.object(api_server.threading, "Thread", return_value=thread):
            api_server._restore_evaluation_jobs_once()

        self.assertEqual(api_server._jobs[self.job["job_id"]]["status"], "resuming")
        thread.start.assert_called_once()

    def test_cancelled_resume_is_not_spawned(self):
        api_server._jobs[self.job["job_id"]]["status"] = "cancelled"
        with patch.object(api_server.subprocess, "Popen") as popen:
            spawned = api_server._spawn_evaluation_job(
                self.job["job_id"],
                resume=True,
                expected_status="resuming",
            )
        self.assertFalse(spawned)
        popen.assert_not_called()

    def test_restored_pid_must_match_the_evaluation_command(self):
        running = Mock(returncode=0, stdout="python unrelated_service.py")
        with patch.object(api_server, "_pid_is_running", return_value=True), patch.object(
            api_server.subprocess, "run", return_value=running
        ), patch.object(api_server.Path, "is_file", return_value=False):
            self.assertFalse(api_server._pid_matches_job(123, self.job))

    def test_spawn_failure_closes_log_and_persists_failed_state(self):
        api_server._jobs[self.job["job_id"]]["status"] = "starting"
        with patch.object(api_server.subprocess, "Popen", side_effect=OSError("cannot spawn")):
            spawned = api_server._spawn_evaluation_job(
                self.job["job_id"],
                resume=False,
                expected_status="starting",
            )
        self.assertFalse(spawned)
        restored = api_server._jobs[self.job["job_id"]]
        self.assertEqual(restored["status"], "failed")
        self.assertIn("could not be started", restored["launch_error"])
        self.assertTrue((self.run_dir / self.job["job_id"] / "job.json").is_file())


if __name__ == "__main__":
    unittest.main()

import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from demo import api_server


class EvaluationResumeTests(unittest.TestCase):
    def setUp(self):
        self.temp_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_directory.name)
        self.workspace = self.root / "workspace"
        self.run_dir = self.workspace / "sessions" / "evaluations"
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
            patch.dict(os.environ, {"SQURVE_WORKSPACE_DIR": str(self.workspace)}),
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
            self.workspace
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

    def test_cancel_terminates_process_group_and_marks_cancelled(self):
        process = Mock()
        process.poll.return_value = None
        process.pid = 4242
        api_server._processes[self.job["job_id"]] = process
        api_server._jobs[self.job["job_id"]]["status"] = "running"
        api_server._jobs[self.job["job_id"]]["pid"] = 4242
        client = api_server.app.test_client()

        with patch.object(api_server, "_terminate_job_process") as terminate:
            response = client.post(f"/api/evaluations/{self.job['job_id']}/cancel")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["status"], "cancelled")
        self.assertEqual(api_server._jobs[self.job["job_id"]]["status"], "cancelled")
        self.assertNotIn(self.job["job_id"], api_server._processes)
        terminate.assert_called_once()

    def test_manual_resume_spawns_reproduce_resume_from_checkpoint(self):
        self._write_checkpoint()
        job_dir = self.run_dir / self.job["job_id"]
        job_dir.mkdir(parents=True, exist_ok=True)
        api_server._jobs[self.job["job_id"]]["status"] = "cancelled"
        api_server._jobs[self.job["job_id"]]["log_path"] = str(
            (job_dir / "run.log").relative_to(self.root)
        )
        api_server._processes.pop(self.job["job_id"], None)
        client = api_server.app.test_client()
        process = Mock()
        process.pid = 9090

        with patch.object(api_server, "_evaluation_llm_preflight"), patch.object(
            api_server.subprocess, "Popen", return_value=process
        ) as popen, patch.object(api_server.threading, "Thread") as thread_cls:
            thread_cls.return_value = Mock()
            response = client.post(f"/api/evaluations/{self.job['job_id']}/resume")

        self.assertEqual(response.status_code, 202)
        payload = response.get_json()
        self.assertEqual(payload["status"], "running")
        self.assertTrue(payload["checkpoint_present"])
        self.assertEqual(payload["resume_mode"], "manual")
        self.assertEqual(payload["resume_count"], 1)
        command = popen.call_args.args[0]
        self.assertIn("reproduce/run.py", command)
        self.assertIn("--resume-from", command)
        self.assertTrue(any(str(part).endswith("state.json") for part in command))

    def test_manual_resume_without_checkpoint_is_rejected(self):
        api_server._jobs[self.job["job_id"]]["status"] = "failed"
        api_server._processes.pop(self.job["job_id"], None)
        client = api_server.app.test_client()
        response = client.post(f"/api/evaluations/{self.job['job_id']}/resume")
        self.assertEqual(response.status_code, 409)
        self.assertIn("checkpoint", response.get_json()["message"].lower())

    def test_public_job_exposes_resumable_flag(self):
        self._write_checkpoint()
        api_server._jobs[self.job["job_id"]]["status"] = "failed"
        public = api_server._public_job(api_server._jobs[self.job["job_id"]])
        self.assertTrue(public["checkpoint_present"])
        self.assertTrue(public["resumable"])
        self.assertNotIn("log_path", public)
        self.assertNotIn("scores_path", public)

    def test_public_job_hides_filesystem_paths(self):
        job = dict(api_server._jobs[self.job["job_id"]])
        job["log_path"] = str(self.root / "workspace" / "sessions" / "evaluations" / "x" / "run.log")
        job["scores_path"] = str(self.root / "workspace" / "sessions" / "evaluations" / "x" / "scores.json")
        public = api_server._public_job(job)
        self.assertNotIn("log_path", public)
        self.assertNotIn("scores_path", public)
        dumped = json.dumps(public)
        self.assertNotIn(str(self.root), dumped)
    def test_public_job_exposes_score_bundle_artifact(self):
        scores_path = self.run_dir / self.job["job_id"] / "score-bundle" / "scores.json"
        scores_path.parent.mkdir(parents=True)
        scores_path.write_text(json.dumps({
            "run_id": "spider-c3sql-resumejob1",
            "method": "c3sql",
            "dataset": "spider",
            "split": "dev",
            "sample_count": 3,
            "timestamp": "2026-07-19T00:00:00Z",
            "aggregate": {
                "ex": {"avg": 0.9, "valid": 3, "total": 3},
                "em": {"avg": 0.8, "valid": 3, "total": 3},
                "token": {"total_tokens": 1000, "avg_per_sample": 333},
            },
            "per_sample": [{"instance_id": "dev_0"}, {"instance_id": "dev_1"}, {"instance_id": "dev_2"}],
            "stage_metrics": {},
            "workflow_trace": {"workflows": [], "aggregate": {}},
        }), encoding="utf-8")
        api_server._jobs[self.job["job_id"]].update({
            "status": "completed",
            "scores_path": str(scores_path),
        })

        public = api_server._public_job(api_server._jobs[self.job["job_id"]])
        self.assertEqual(public["result"]["metrics"]["ex"], 0.9)
        self.assertEqual(public["artifact"]["method"], "c3sql")
        self.assertEqual(
            public["artifact"]["artifact_ref"],
            "session:spider-c3sql-resumejob1/scores.json",
        )

    def test_session_endpoint_lists_jobs(self):
        client = api_server.app.test_client()
        response = client.get("/api/session")
        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertIn("jobs", payload)
        self.assertEqual(payload["jobs"][0]["job_id"], self.job["job_id"])

    def test_run_progress_counts_finished_samples_not_stage_entries(self):
        log = "\n".join([
            "开始处理样本 dev_0",
            "样本 dev_0 @ c3sql_reduce1",
            "样本 dev_0 @ c3sql_parse1",
            "样本 dev_0 @ c3sql_generate1",
            "样本 dev_0 处理完成 (12.0s)",
            "开始处理样本 dev_1",
            "样本 dev_1 @ c3sql_generate1",
            "样本 20 条  |  pass@1",
        ])
        # Without the report header line used by the summarizer, only finished samples count.
        progress = api_server._summarize_run_progress(log, {"sample_limit": 20, "status": "running"})
        self.assertEqual(progress["completed"], 1)
        self.assertEqual(progress["started"], 2)
        self.assertEqual(progress["percent"], 5)

        finished_log = log + "\n========================================================================\n  评估结果  spider-c3sql\n  样本 20 条  |  pass@1  |  generate_num=1\n"
        done = api_server._summarize_run_progress(
            finished_log,
            {"sample_limit": 20, "status": "completed"},
        )
        self.assertEqual(done["percent"], 100)
        self.assertEqual(done["completed"], 20)
        self.assertEqual(done["current_stage"], "评估完成")

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

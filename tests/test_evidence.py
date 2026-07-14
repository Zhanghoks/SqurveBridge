import argparse
import json
import math
import tempfile
import unittest
from pathlib import Path

from tools import evidence


class EvidenceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tempdir.name)
        self.metadata = self._json(
            "metadata.json",
            {
                "method": "c3sql",
                "benchmark": "spider",
                "split": "dev",
                "sample_count": 1,
                "provider": "test-provider",
                "model": "test-model",
                "code_commit": "0" * 40,
                "evaluator_version": "test-v1",
                "source_alignment": "demo",
            },
        )
        self.config = self._json(
            "config.json",
            {
                "api_key": {"provider": "your_api_key_here"},
                "dataset": {"data_source": "spider:dev:1"},
            },
        )
        self.scores = self._json(
            "scores.json",
            {
                "run_id": "private-run",
                "ex": 1.0,
                "per_sample": [{"question": "must not be copied", "gold_sql": "SELECT 1"}],
            },
        )
        self.report = self.root / "report.md"
        self.report.write_text("# Public report\n\nAggregate EX: 1.0\n", encoding="utf-8")
        self.diagnostics = self.root / "diagnostics.jsonl"
        self.diagnostics.write_text(
            json.dumps(
                {
                    "instance_id": "sample-1",
                    "metrics": {"ex": 1.0},
                    "stage_status": {"generate": "completed"},
                    "token_usage": {"prompt": 10, "completion": 5},
                    "latency_ms": 12,
                }
            )
            + "\n",
            encoding="utf-8",
        )

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    def _json(self, name: str, payload: object) -> Path:
        path = self.root / name
        path.write_text(json.dumps(payload), encoding="utf-8")
        return path

    def _args(self, run_id: str = "public-run") -> argparse.Namespace:
        return argparse.Namespace(
            run_id=run_id,
            metadata=self.metadata,
            config=self.config,
            scores=self.scores,
            report=self.report,
            diagnostics=self.diagnostics,
            output_root=self.root / "published",
        )

    def test_export_and_verify_sanitized_bundle(self) -> None:
        bundle = evidence.export_bundle(self._args())
        manifest = evidence.verify_bundle(bundle)

        self.assertEqual(manifest["run_id"], "public-run")
        exported_config = json.loads((bundle / "config.json").read_text(encoding="utf-8"))
        exported_scores = json.loads((bundle / "scores.json").read_text(encoding="utf-8"))
        self.assertNotIn("api_key", exported_config)
        self.assertNotIn("per_sample", exported_scores)
        self.assertEqual(
            {path.name for path in bundle.iterdir()}, evidence.ALLOWED_BUNDLE_FILES
        )

    def test_nested_sample_records_and_paths_are_removed(self) -> None:
        self.scores = self._json(
            "scores.json",
            {
                "run_id": "private-run",
                "config_path": "/Users/example/private/config.json",
                "workflow_trace": {
                    "aggregate": {"completed": 1},
                    "per_sample": [{"question": "private"}],
                },
            },
        )
        bundle = evidence.export_bundle(self._args())
        exported = json.loads((bundle / "scores.json").read_text(encoding="utf-8"))

        self.assertNotIn("config_path", exported)
        self.assertEqual(exported["workflow_trace"], {"aggregate": {"completed": 1}})

    def test_unknown_diagnostic_field_fails_closed(self) -> None:
        self.diagnostics.write_text(
            '{"instance_id":"sample-1","question":"private"}\n', encoding="utf-8"
        )
        with self.assertRaises(evidence.EvidenceError):
            evidence.export_bundle(self._args())

    def test_absolute_path_fails_closed(self) -> None:
        self.report.write_text("private path: /Users/example/run.json\n", encoding="utf-8")
        with self.assertRaises(evidence.EvidenceError):
            evidence.export_bundle(self._args())

    def test_secret_fails_closed_without_echoing_value(self) -> None:
        secret = "sk-" + "A" * 40
        self.report.write_text(f"provider token: {secret}\n", encoding="utf-8")
        with self.assertRaises(evidence.EvidenceError) as context:
            evidence.export_bundle(self._args())
        self.assertNotIn(secret, str(context.exception))

    def test_non_placeholder_config_credential_fails_closed(self) -> None:
        self.config = self._json(
            "config.json", {"api_key": {"provider": "real-private-value-123456"}}
        )
        with self.assertRaisesRegex(evidence.EvidenceError, "non-placeholder credential"):
            evidence.export_bundle(self._args())

    def test_sql_text_in_report_fails_closed(self) -> None:
        self.report.write_text("Example: SELECT name FROM private_table\n", encoding="utf-8")
        with self.assertRaisesRegex(evidence.EvidenceError, "SQL text"):
            evidence.export_bundle(self._args())

    def test_checksum_tampering_is_rejected(self) -> None:
        bundle = evidence.export_bundle(self._args())
        (bundle / "report.md").write_text("changed\n", encoding="utf-8")
        with self.assertRaisesRegex(evidence.EvidenceError, "checksum mismatch"):
            evidence.verify_bundle(bundle)

    def test_unknown_bundle_file_is_rejected(self) -> None:
        bundle = evidence.export_bundle(self._args())
        (bundle / "raw-response.json").write_text("{}\n", encoding="utf-8")
        with self.assertRaisesRegex(evidence.EvidenceError, "bundle contents invalid"):
            evidence.verify_bundle(bundle)

    def test_non_finite_metric_is_rejected(self) -> None:
        self.diagnostics.write_text(
            json.dumps({"instance_id": "sample-1", "metrics": {"ex": math.nan}}) + "\n",
            encoding="utf-8",
        )
        with self.assertRaisesRegex(evidence.EvidenceError, "non-finite"):
            evidence.export_bundle(self._args())

    def test_existing_destination_is_not_overwritten(self) -> None:
        evidence.export_bundle(self._args())
        with self.assertRaisesRegex(evidence.EvidenceError, "already exists"):
            evidence.export_bundle(self._args())


if __name__ == "__main__":
    unittest.main()

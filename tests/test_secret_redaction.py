"""Ensure resolved API keys never land in persisted runtime or score-bundle configs."""

from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from reproduce.lib.env_config import REDACTED_PLACEHOLDER, redact_config_secrets
from reproduce.metrics.persistence import persist_scores_bundle
from reproduce.runner import run as runner

# Deliberately non-sk-shaped literals so security_scan does not flag this fixture file.
_FAKE_DEEPSEEK = "test-secret-deepseek-must-not-persist"
_FAKE_QWEN = "test-secret-qwen-must-not-persist"
_FAKE_UNKNOWN = "test-secret-unknown-provider"
_FAKE_RUNTIME = "test-secret-runtime-write"
_FAKE_BUNDLE = "test-secret-bundle-write"


class SecretRedactionTests(unittest.TestCase):
    def test_redact_replaces_plaintext_with_env_ref(self):
        config = {
            "api_key": {
                "deepseek": _FAKE_DEEPSEEK,
                "qwen": "${ENV:QWEN_API_KEY}",
                "zhipu": "your_api_key_here",
            },
            "llm": {"use": "deepseek"},
        }
        redacted = redact_config_secrets(config)
        self.assertEqual(redacted["api_key"]["deepseek"], "${ENV:DEEPSEEK_API_KEY}")
        self.assertEqual(redacted["api_key"]["qwen"], "${ENV:QWEN_API_KEY}")
        self.assertEqual(redacted["api_key"]["zhipu"], "your_api_key_here")
        # In-memory original must stay untouched for runtime use.
        self.assertEqual(config["api_key"]["deepseek"], _FAKE_DEEPSEEK)

    def test_redact_unknown_provider_uses_placeholder(self):
        config = {"api_key": {"custom-vendor": _FAKE_UNKNOWN}}
        redacted = redact_config_secrets(config)
        self.assertEqual(redacted["api_key"]["custom-vendor"], REDACTED_PLACEHOLDER)

    def test_write_runtime_config_never_persists_plaintext(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            run_id = "spider-c3sql-secret-test"
            config = {"api_key": {"deepseek": _FAKE_RUNTIME}, "llm": {"use": "deepseek"}}
            with patch.dict(os.environ, {"SQURVE_WORKSPACE_DIR": str(root / "workspace")}):
                path = runner._write_runtime_config(config, run_id)
                text = path.read_text(encoding="utf-8")
            self.assertNotIn(_FAKE_RUNTIME, text)
            persisted = json.loads(text)
            self.assertEqual(persisted["api_key"]["deepseek"], "${ENV:DEEPSEEK_API_KEY}")
            self.assertTrue(str(path).endswith(f"runs/{run_id}/config.json"))

    def test_persist_scores_bundle_never_persists_plaintext(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "score-bundle"
            config = {"api_key": {"qwen": _FAKE_BUNDLE}, "llm": {"use": "qwen"}}
            with patch(
                "reproduce.metrics.persistence.persist_eval_store",
                return_value=output / "eval-store.sqlite",
            ):
                paths = persist_scores_bundle(
                    output_dir=output,
                    scores={"run_id": "test", "aggregate": {}},
                    config=config,
                )
            text = paths["config"].read_text(encoding="utf-8")
            self.assertNotIn(_FAKE_BUNDLE, text)
            persisted = json.loads(text)
            self.assertEqual(persisted["api_key"]["qwen"], "${ENV:QWEN_API_KEY}")


if __name__ == "__main__":
    unittest.main()

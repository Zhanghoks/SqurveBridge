"""Local /api/provider accepts freely chosen model IDs."""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock


class ProviderCustomModelTests(unittest.TestCase):
    def test_validate_model_id_accepts_custom_values(self):
        from demo import api_server

        self.assertEqual(api_server._validate_model_id("  qwen3-max  "), "qwen3-max")
        with self.assertRaises(ValueError):
            api_server._validate_model_id("")
        with self.assertRaises(ValueError):
            api_server._validate_model_id("bad\nmodel")

    def test_apply_provider_config_accepts_custom_model(self):
        from demo import api_server

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            env_path = root / ".env"
            with mock.patch.object(api_server, "_project_root", root), mock.patch.object(
                api_server,
                "_router_config",
                return_value={"llm": {"use": "qwen", "model_name": "qwen-turbo"}, "api_key": {}},
            ), mock.patch.dict(
                os.environ,
                {"QWEN_API_KEY": "sk-test-key"},
                clear=False,
            ):
                api_server._runtime_llm.update(provider=None, model=None)
                status = api_server._apply_provider_config(
                    "qwen",
                    "qwen3-custom-latest",
                    api_key=None,
                    persist=True,
                )
                self.assertEqual(status["provider"], "qwen")
                self.assertEqual(status["model"], "qwen3-custom-latest")
                self.assertTrue(status["configured"])
                body = env_path.read_text(encoding="utf-8")
                self.assertIn("SQURVE_LLM_PROVIDER=qwen", body)
                self.assertIn("SQURVE_LLM_MODEL=qwen3-custom-latest", body)

    def test_llm_provider_catalog_keeps_official_models_only(self):
        from demo import api_server

        with mock.patch.object(
            api_server,
            "_provider_status",
            return_value={
                "provider": "qwen",
                "model": "qwen3-custom-latest",
                "configured": True,
                "ready": True,
                "verified": True,
            },
        ), mock.patch.object(api_server, "deployment_target", return_value="local"), mock.patch.object(
            api_server,
            "resolve_api_key",
            return_value="sk-test",
        ), mock.patch.object(api_server, "load_dotenv"):
            catalog = {item["id"]: item for item in api_server._llm_provider_catalog()}
            qwen = catalog["qwen"]
            self.assertEqual(qwen["models"], list(api_server._provider_models["qwen"]))
            self.assertNotIn("qwen3-custom-latest", qwen["models"])
            self.assertEqual(qwen["default_model"], api_server._provider_models["qwen"][0])


if __name__ == "__main__":
    unittest.main()

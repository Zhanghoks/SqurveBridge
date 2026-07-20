import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from demo import api_server
from reproduce.lib.env_config import (
    apply_runtime_llm_overrides,
    api_key_ready,
    prepare_runtime_llm_config,
)

_LLM_ENV_KEYS = (
    "SQURVE_LLM_PROVIDER",
    "SQURVE_LLM_MODEL",
    "QWEN_API_KEY",
    "DEEPSEEK_API_KEY",
)


def _cleared_llm_environ(**extra: str):
    """Patch os.environ with LLM-related keys removed, then apply *extra*.

    Also stubs ``load_dotenv`` so the real repo-root ``.env`` cannot re-inject
    provider settings into the cleared process environment.
    """
    cleaned = {key: value for key, value in os.environ.items() if key not in _LLM_ENV_KEYS}
    cleaned.update(extra)
    return (
        patch.dict(os.environ, cleaned, clear=True),
        patch("reproduce.lib.env_config.load_dotenv", return_value=False),
    )


class RuntimeLlmOverrideTests(unittest.TestCase):
    def test_apply_runtime_llm_overrides_switches_provider_and_model(self):
        config = {
            "api_key": {"qwen": "${ENV:QWEN_API_KEY}"},
            "llm": {"use": "qwen", "model_name": "qwen-turbo"},
        }
        env_patch, dotenv_patch = _cleared_llm_environ(
            SQURVE_LLM_PROVIDER="deepseek",
            SQURVE_LLM_MODEL="deepseek-chat",
            DEEPSEEK_API_KEY="sk-test-deepseek",
        )
        with env_patch, dotenv_patch:
            prepared = prepare_runtime_llm_config(config)

        self.assertEqual(prepared["llm"]["use"], "deepseek")
        self.assertEqual(prepared["llm"]["model_name"], "deepseek-chat")
        self.assertEqual(prepared["api_key"]["deepseek"], "sk-test-deepseek")
        self.assertTrue(api_key_ready(prepared)[0])

    def test_without_runtime_env_keeps_template_provider(self):
        config = {
            "api_key": {"qwen": "${ENV:QWEN_API_KEY}"},
            "llm": {"use": "qwen", "model_name": "qwen-turbo"},
        }
        env_patch, dotenv_patch = _cleared_llm_environ()
        with env_patch, dotenv_patch:
            overridden = apply_runtime_llm_overrides(config)

        self.assertEqual(overridden["llm"]["use"], "qwen")
        self.assertEqual(overridden["llm"]["model_name"], "qwen-turbo")

    def test_unsupported_provider_raises(self):
        env_patch, dotenv_patch = _cleared_llm_environ(SQURVE_LLM_PROVIDER="not-a-provider")
        with env_patch, dotenv_patch:
            with self.assertRaises(ValueError):
                apply_runtime_llm_overrides({"llm": {"use": "qwen"}})


class EvaluationLlmPreflightTests(unittest.TestCase):
    def setUp(self):
        self.temp_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_directory.name)
        self.config_dir = self.root / "reproduce" / "configs" / "spider"
        self.config_dir.mkdir(parents=True)
        self.config_path = self.config_dir / "c3sql.json"
        self.config_path.write_text(
            json.dumps(
                {
                    "api_key": {"qwen": "${ENV:QWEN_API_KEY}"},
                    "llm": {"use": "qwen", "model_name": "qwen-turbo"},
                }
            ),
            encoding="utf-8",
        )
        self.patches = (
            patch.object(api_server, "_project_root", self.root),
            patch("demo.api_server.config_repo_path", return_value=self.config_path),
        )
        for item in self.patches:
            item.start()

    def tearDown(self):
        for item in reversed(self.patches):
            item.stop()
        self.temp_directory.cleanup()

    def test_preflight_fails_when_template_qwen_key_missing_and_no_override(self):
        env_patch, dotenv_patch = _cleared_llm_environ()
        with env_patch, dotenv_patch:
            with self.assertRaises(ValueError) as ctx:
                api_server._evaluation_llm_preflight("spider", "c3sql")
        self.assertIn("qwen", str(ctx.exception).lower())

    def test_preflight_passes_when_demo_deepseek_override_has_key(self):
        env_patch, dotenv_patch = _cleared_llm_environ(
            SQURVE_LLM_PROVIDER="deepseek",
            SQURVE_LLM_MODEL="deepseek-chat",
            DEEPSEEK_API_KEY="sk-test-deepseek",
        )
        with env_patch, dotenv_patch:
            api_server._evaluation_llm_preflight("spider", "c3sql")


if __name__ == "__main__":
    unittest.main()

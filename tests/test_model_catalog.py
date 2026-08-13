"""Regressions for the provider → model ID catalog backing Configure LLM."""

from __future__ import annotations

import json
import subprocess
import sys
import unittest
from pathlib import Path

_project_root = Path(__file__).resolve().parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from demo import model_catalog  # noqa: E402


def _completed(stdout: str, returncode: int = 0) -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess(args=[], returncode=returncode, stdout=stdout, stderr="")


class ModelCatalogTest(unittest.TestCase):
    def tearDown(self) -> None:
        model_catalog.reset_cache()

    def test_every_default_model_exists_in_its_catalog(self):
        catalog = model_catalog.build_catalog(model_catalog.read_sdk_models(_project_root))
        for provider, default in model_catalog.DEFAULT_MODELS.items():
            self.assertIn(default, catalog[provider], f"{provider} lost its default model")
            self.assertEqual(catalog[provider][0], default)

    def test_sdk_provider_ids_map_onto_demo_providers(self):
        for provider in model_catalog.SDK_PROVIDER_IDS:
            self.assertIn(provider, model_catalog.PROVIDER_ORDER)
        for provider in model_catalog.CURATED_MODELS:
            self.assertIn(provider, model_catalog.PROVIDER_ORDER)
        # Every provider is sourced exactly once, from the SDK or by hand.
        self.assertEqual(
            set(model_catalog.SDK_PROVIDER_IDS) | set(model_catalog.CURATED_MODELS),
            set(model_catalog.PROVIDER_ORDER),
        )
        self.assertFalse(set(model_catalog.SDK_PROVIDER_IDS) & set(model_catalog.CURATED_MODELS))

    def test_build_catalog_uses_sdk_models_for_shared_endpoints(self):
        catalog = model_catalog.build_catalog({"deepseek": ["deepseek-v4-flash", "deepseek-v4-pro"]})
        self.assertEqual(catalog["deepseek"], ["deepseek-v4-flash", "deepseek-v4-pro"])
        # Curated providers ignore anything the SDK reports for them.
        self.assertEqual(
            sorted(catalog["qwen"]),
            sorted(model_catalog.CURATED_MODELS["qwen"]),
        )
        self.assertEqual(catalog["qwen"][0], model_catalog.DEFAULT_MODELS["qwen"])

    def test_build_catalog_puts_the_default_model_first(self):
        catalog = model_catalog.build_catalog({"openai": ["gpt-4", "gpt-5-mini", "gpt-4.1-mini"]})
        self.assertEqual(catalog["openai"][0], "gpt-5-mini")
        self.assertEqual(sorted(catalog["openai"]), sorted(["gpt-4", "gpt-5-mini", "gpt-4.1-mini"]))

    def test_build_catalog_keeps_sdk_order_when_the_default_is_gone(self):
        catalog = model_catalog.build_catalog({"openai": ["gpt-4", "gpt-4.1-mini"]})
        self.assertEqual(catalog["openai"], ["gpt-4", "gpt-4.1-mini"])

    def test_build_catalog_falls_back_when_the_sdk_reports_nothing(self):
        catalog = model_catalog.build_catalog({})
        for provider in model_catalog.SDK_PROVIDER_IDS:
            self.assertEqual(
                sorted(catalog[provider]),
                sorted(model_catalog.FALLBACK_SDK_MODELS[provider]),
            )
        self.assertTrue(all(catalog[provider] for provider in model_catalog.PROVIDER_ORDER))

    def test_read_sdk_models_keys_results_by_demo_provider(self):
        payload = json.dumps({"anthropic": ["claude-haiku-4-5"], "google": ["gemini-2.5-flash"]})
        resolved = model_catalog.read_sdk_models(
            _project_root,
            runner=lambda *args, **kwargs: _completed(payload),
        )
        self.assertEqual(resolved["claude"], ["claude-haiku-4-5"])
        self.assertEqual(resolved["gemini"], ["gemini-2.5-flash"])

    def test_read_sdk_models_tolerates_a_broken_node_run(self):
        for runner in (
            lambda *args, **kwargs: _completed("", returncode=1),
            lambda *args, **kwargs: _completed("not json"),
            lambda *args, **kwargs: _completed("[]"),
        ):
            self.assertEqual(model_catalog.read_sdk_models(_project_root, runner=runner), {})

        def explode(*args, **kwargs):
            raise OSError("node is missing")

        self.assertEqual(model_catalog.read_sdk_models(_project_root, runner=explode), {})

    def test_read_sdk_models_never_reads_credentials(self):
        captured: dict[str, object] = {}

        def runner(command, **kwargs):
            captured["command"] = command
            return _completed(json.dumps({"deepseek": ["deepseek-v4-flash"]}))

        model_catalog.read_sdk_models(_project_root, runner=runner)
        command = captured["command"]
        self.assertTrue(str(command[1]).endswith("pi_model_catalog.mjs"))
        self.assertEqual(sorted(command[2:]), sorted(set(model_catalog.SDK_PROVIDER_IDS.values())))


if __name__ == "__main__":
    unittest.main()

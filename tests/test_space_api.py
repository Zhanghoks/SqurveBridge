import os
import unittest
from unittest.mock import patch


class SpaceApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from demo.api_server import app

        app.config.update(TESTING=True)
        cls.client = app.test_client()

    def test_capabilities_identify_the_same_app_as_hf_hosted(self):
        with patch.dict(os.environ, {"SQURVE_DEPLOYMENT_TARGET": "hf-space"}, clear=False):
            response = self.client.get("/api/capabilities")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json["deployment"]["target"], "hf-space")
        self.assertTrue(response.json["deployment"]["features"]["live_sql"])

    def test_hosted_space_rejects_local_only_mutations(self):
        with patch.dict(os.environ, {"SQURVE_DEPLOYMENT_TARGET": "hf-space"}, clear=False):
            for method, path in (
                ("post", "/api/provider"),
                ("post", "/api/databases/upload"),
                ("post", "/api/evaluations"),
                ("post", "/api/comparisons"),
                ("get", "/api/terminals"),
            ):
                response = getattr(self.client, method)(path, json={})
                self.assertEqual(response.status_code, 403, path)
                self.assertEqual(response.json["reason"], "local_only")

    def test_hosted_space_exposes_only_the_server_selected_provider_and_model(self):
        environment = {
            "SQURVE_DEPLOYMENT_TARGET": "hf-space",
            "SQURVE_LLM_PROVIDER": "qwen",
            "SQURVE_LLM_MODEL": "qwen-plus",
        }
        with patch.dict(os.environ, environment, clear=False):
            response = self.client.get("/api/capabilities")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json["llm_providers"]), 1)
        self.assertEqual(response.json["llm_providers"][0]["id"], "qwen")
        self.assertEqual(response.json["llm_providers"][0]["models"], ["qwen-plus"])
        self.assertEqual(response.json["llm_providers"][0]["default_model"], "qwen-plus")

    def test_hosted_space_retains_core_llm_routes(self):
        with patch.dict(os.environ, {"SQURVE_DEPLOYMENT_TARGET": "hf-space"}, clear=False):
            self.assertNotEqual(self.client.post("/api/query", json={}).status_code, 403)
            self.assertNotEqual(self.client.post("/api/execute", json={}).status_code, 403)
            self.assertEqual(self.client.get("/api/archive").status_code, 200)


if __name__ == "__main__":
    unittest.main()

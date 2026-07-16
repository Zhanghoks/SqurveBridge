import os
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from demo.session_auth import SessionCredentialRegistry


class SpaceApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from demo import api_server

        api_server.app.config.update(TESTING=True)
        cls.api_server = api_server

    def setUp(self):
        self.api_server._sql_credentials = SessionCredentialRegistry()
        self.client = self.api_server.app.test_client()

    def test_capabilities_identify_the_same_app_as_hf_hosted(self):
        with patch.dict(os.environ, {"SQURVE_DEPLOYMENT_TARGET": "hf-space"}, clear=False):
            response = self.client.get("/api/capabilities")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json["deployment"]["target"], "hf-space")
        self.assertTrue(response.json["deployment"]["features"]["live_sql"])
        self.assertTrue(response.json["deployment"]["features"]["agent_chat"])
        self.assertTrue(response.json["deployment"]["features"]["session_sql_auth"])

    def test_hosted_space_rejects_local_only_mutations(self):
        with patch.dict(os.environ, {"SQURVE_DEPLOYMENT_TARGET": "hf-space"}, clear=False):
            for method, path in (
                ("post", "/api/provider"),
                ("post", "/api/databases/upload"),
                ("post", "/api/evaluations"),
                ("post", "/api/comparisons"),
            ):
                response = getattr(self.client, method)(path, json={})
                self.assertEqual(response.status_code, 403, path)
                self.assertEqual(response.json["reason"], "local_only")

    def test_hosted_space_exposes_the_squrve_provider_catalog_for_byok(self):
        environment = {
            "SQURVE_DEPLOYMENT_TARGET": "hf-space",
            "SQURVE_LLM_PROVIDER": "qwen",
            "SQURVE_LLM_MODEL": "qwen-plus",
        }
        with patch.dict(os.environ, environment, clear=False):
            response = self.client.get("/api/capabilities")
        self.assertEqual(response.status_code, 200)
        providers = {item["id"]: item for item in response.json["llm_providers"]}
        self.assertEqual(set(providers), set(self.api_server._provider_models))
        self.assertIn("qwen-plus", providers["qwen"]["models"])
        self.assertNotIn("env_var", providers["qwen"])

    def test_hosted_sql_auth_is_cookie_scoped_and_secret_free(self):
        payload = {"provider": "qwen", "model": "qwen-plus", "api_key": "sql-secret-a"}
        first = self.api_server.app.test_client()
        second = self.api_server.app.test_client()
        environment = {"SQURVE_DEPLOYMENT_TARGET": "hf-space"}

        with patch.dict(os.environ, environment, clear=False), patch.object(
            self.api_server, "_validate_sql_credential", return_value=None
        ):
            saved = first.put("/api/sql-auth", json=payload)
            first_status = first.get("/api/sql-auth")
            second_status = second.get("/api/sql-auth")

        self.assertEqual(saved.status_code, 200)
        self.assertIn("Secure", saved.headers["Set-Cookie"])
        self.assertIn("HttpOnly", saved.headers["Set-Cookie"])
        self.assertIn("SameSite=Lax", saved.headers["Set-Cookie"])
        self.assertTrue(first_status.json["configured"])
        self.assertEqual(first_status.json["provider"], "qwen")
        self.assertFalse(second_status.json["configured"])
        self.assertNotIn("sql-secret-a", first_status.get_data(as_text=True))
        self.assertNotIn("sql-secret-a", saved.get_data(as_text=True))

    def test_testing_a_sql_key_does_not_activate_it(self):
        payload = {"provider": "qwen", "model": "qwen-plus", "api_key": "test-only-secret"}
        with patch.dict(os.environ, {"SQURVE_DEPLOYMENT_TARGET": "hf-space"}, clear=False), patch.object(
            self.api_server, "_validate_sql_credential", return_value=None
        ):
            tested = self.client.post("/api/sql-auth/test", json=payload)
            status = self.client.get("/api/sql-auth")

        self.assertEqual(tested.status_code, 200)
        self.assertEqual(tested.json["validated"], True)
        self.assertFalse(status.json["configured"])

    def test_disconnecting_sql_auth_removes_the_session_credential(self):
        payload = {"provider": "qwen", "model": "qwen-plus", "api_key": "disconnect-secret"}
        with patch.dict(os.environ, {"SQURVE_DEPLOYMENT_TARGET": "hf-space"}, clear=False), patch.object(
            self.api_server, "_validate_sql_credential", return_value=None
        ):
            self.client.put("/api/sql-auth", json=payload)
            disconnected = self.client.delete("/api/sql-auth")
            status = self.client.get("/api/sql-auth")

        self.assertEqual(disconnected.status_code, 200)
        self.assertFalse(status.json["configured"])
        self.assertIn("Max-Age=0", disconnected.headers["Set-Cookie"])
        self.assertNotIn("disconnect-secret", disconnected.get_data(as_text=True))

    def test_sql_session_timeout_and_capacity_eviction_remove_access(self):
        now = [100.0]
        self.api_server._sql_credentials = SessionCredentialRegistry(
            max_sessions=1, idle_timeout=30, clock=lambda: now[0]
        )
        first = self.api_server.app.test_client()
        second = self.api_server.app.test_client()
        environment = {"SQURVE_DEPLOYMENT_TARGET": "hf-space"}
        with patch.dict(os.environ, environment, clear=False), patch.object(
            self.api_server, "_validate_sql_credential", return_value=None
        ):
            first.put("/api/sql-auth", json={"provider": "qwen", "model": "qwen-plus", "api_key": "evicted-sql-secret"})
            second.put("/api/sql-auth", json={"provider": "deepseek", "model": "deepseek-chat", "api_key": "active-sql-secret"})
            self.assertFalse(first.get("/api/sql-auth").json["configured"])
            self.assertTrue(second.get("/api/sql-auth").json["configured"])
            now[0] += 31
            expired = second.get("/api/sql-auth")

        self.assertFalse(expired.json["configured"])
        self.assertNotIn("evicted-sql-secret", expired.get_data(as_text=True))
        self.assertNotIn("active-sql-secret", expired.get_data(as_text=True))

    def test_hosted_sql_auth_rejects_cross_origin_mutation(self):
        payload = {"provider": "qwen", "model": "qwen-plus", "api_key": "cross-origin-secret"}
        with patch.dict(os.environ, {"SQURVE_DEPLOYMENT_TARGET": "hf-space"}, clear=False):
            response = self.client.put(
                "/api/sql-auth",
                json=payload,
                headers={"Origin": "https://attacker.example"},
            )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json["code"], "origin_forbidden")
        self.assertNotIn("cross-origin-secret", response.get_data(as_text=True))

    def test_hosted_sql_auth_accepts_the_forwarded_space_origin(self):
        payload = {"provider": "qwen", "model": "qwen-plus", "api_key": "forwarded-secret"}
        headers = {
            "Origin": "https://demo.hf.space",
            "X-Forwarded-Host": "demo.hf.space",
            "X-Forwarded-Proto": "https",
        }
        with patch.dict(os.environ, {"SQURVE_DEPLOYMENT_TARGET": "hf-space"}, clear=False), patch.object(
            self.api_server, "_validate_sql_credential", return_value=None
        ):
            response = self.client.put("/api/sql-auth", json=payload, headers=headers)

        self.assertEqual(response.status_code, 200)
        self.assertNotIn("forwarded-secret", response.get_data(as_text=True))

    def test_hosted_sql_auth_redacts_rejected_credentials(self):
        payload = {"provider": "qwen", "model": "qwen-plus", "api_key": "rejected-secret"}
        error = self.api_server.SqlAuthError("credential_rejected")
        with patch.dict(os.environ, {"SQURVE_DEPLOYMENT_TARGET": "hf-space"}, clear=False), patch.object(
            self.api_server, "_validate_sql_credential", side_effect=error
        ):
            response = self.client.put("/api/sql-auth", json=payload)

        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json["code"], "credential_rejected")
        self.assertNotIn("rejected-secret", response.get_data(as_text=True))

    def test_hosted_query_requires_and_uses_only_the_session_credential(self):
        database = {"id": "demo", "db_path": "/tmp/demo.sqlite", "schema_path": "/tmp/schema.json"}
        fake_demo = Mock()
        fake_demo.generate_sql.return_value = {"status": "success", "sql": "SELECT 1"}
        captured = []

        def session_demo(credential):
            captured.append(credential)
            return fake_demo

        with patch.dict(os.environ, {"SQURVE_DEPLOYMENT_TARGET": "hf-space"}, clear=False), patch.object(
            self.api_server, "_find_database", return_value=database
        ), patch.object(self.api_server, "_validate_sql_credential", return_value=None), patch.object(
            self.api_server, "_session_demo", side_effect=session_demo
        ):
            missing = self.client.post("/api/query", json={"question": "Count rows", "db_id": "demo"})
            self.client.put(
                "/api/sql-auth",
                json={"provider": "qwen", "model": "qwen-plus", "api_key": "session-sql-secret"},
            )
            generated = self.client.post(
                "/api/query",
                json={
                    "question": "Count rows",
                    "db_id": "demo",
                    "provider": "deepseek",
                    "model": "deepseek-chat",
                },
            )

        self.assertEqual(missing.status_code, 401)
        self.assertEqual(missing.json["code"], "auth_required")
        self.assertEqual(generated.status_code, 200)
        self.assertEqual(generated.json["run_config"]["llm"], {"provider": "qwen", "model": "qwen-plus"})
        self.assertEqual(captured[-1].api_key, "session-sql-secret")
        self.assertNotIn("session-sql-secret", generated.get_data(as_text=True))

    def test_squrve_demo_direct_key_bypasses_environment_resolution(self):
        from demo import gradio_demo

        config = {
            "api_key": {},
            "llm": {"use": "qwen", "model_name": "qwen-plus"},
            "dataset": {},
            "database": {},
            "task": {"task_meta": []},
        }
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "config.json"
            config_path.write_text(json.dumps(config), encoding="utf-8")
            with patch.object(gradio_demo, "resolve_config_api_keys") as resolve, patch.object(
                gradio_demo, "Engine", return_value=Mock()
            ), patch.object(gradio_demo.Router, "init_config") as init_config:
                gradio_demo.SqurveDemo(
                    config_path=str(config_path),
                    provider="qwen",
                    model_name="qwen-plus",
                    api_key="test-direct-secret",
                )

        resolve.assert_not_called()
        routed_config = init_config.call_args.args[0]
        self.assertEqual(routed_config["api_key"]["qwen"], "test-direct-secret")

    def test_hosted_space_retains_core_llm_routes(self):
        with patch.dict(os.environ, {"SQURVE_DEPLOYMENT_TARGET": "hf-space"}, clear=False):
            self.assertNotEqual(self.client.post("/api/query", json={}).status_code, 403)
            self.assertNotEqual(self.client.post("/api/execute", json={}).status_code, 403)
            self.assertEqual(self.client.get("/api/archive").status_code, 200)

    def test_comparison_results_expose_only_sanitized_sample_diagnostics(self):
        forbidden = {
            "question": "private benchmark question",
            "gold_sql": "SELECT private_gold",
            "pred_sql": "SELECT private_prediction",
        }
        scores = {
            "run_id": "safe-run",
            "method": "c3sql",
            "dataset": "spider",
            "split": "dev",
            "scope": "sample",
            "sample_count": 1,
            "aggregate": {
                "ex": {"avg": 0.0},
                "nested": forbidden,
            },
            "stage_metrics": {"generate": {"ex": 0.0, "nested": forbidden}},
            "workflow_trace": {
                "workflows": [{"stage": "generate", "nested": forbidden}],
                "aggregate": {"elapsed_s": 0.9, "nested": forbidden},
            },
            "by_hardness": {"hard": {"ex": 0.0, "nested": forbidden}},
            "by_sql_feature": {"group_by": {"ex": 0.0, "nested": forbidden}},
            "by_scenario": {"join": {"ex": 0.0, "nested": forbidden}},
            "qvt": {"summary": {"score": 0.0, "nested": forbidden}},
            "weakness_profile": {
                "summary": "schema linking",
                "nested": forbidden,
            },
            "evolution_record": {
                "baseline": {"artifact": "scores.json", "nested": forbidden},
                "candidate_change": {"status": "recorded"},
            },
            "per_sample": [{
                "instance_id": "dev_1",
                "db_id": "concert_singer",
                "hardness": "hard",
                "ex": 0,
                "error_root": "execution_error",
                "error_sub": "missing_column",
                "sl_recall": 0.5,
                "act_elapsed_s": 0.9,
                **forbidden,
            }],
        }

        def comparison(*_args, **_kwargs):
            run = self.api_server._serialize_comparison_run(scores)
            return self.api_server._comparison_payload([run], ["c3sql"])

        with patch.object(self.api_server, "_artifact_comparison", side_effect=comparison):
            response = self.client.get("/api/comparisons/latest/results")

        self.assertEqual(response.status_code, 200)
        run = response.json["runs"][0]
        self.assertEqual(run["by_hardness"], {"hard": {"ex": 0.0, "nested": {}}})
        self.assertEqual(run["weakness_profile"]["summary"], "schema linking")
        self.assertEqual(
            run["evolution_record"]["candidate_change"]["status"],
            "recorded",
        )
        self.assertEqual(run["samples"], [{
            "instance_id": "dev_1",
            "db_id": "concert_singer",
            "hardness": "hard",
            "ex": 0,
            "error_root": "execution_error",
            "error_sub": "missing_column",
            "sl_recall": 0.5,
            "act_elapsed_s": 0.9,
        }])
        serialized = response.get_data(as_text=True)
        for forbidden in ("question", "gold_sql", "pred_sql", "private benchmark question"):
            self.assertNotIn(forbidden, serialized)

    def test_localhost_7860_provider_request_reaches_business_validation(self):
        with patch.dict(os.environ, {"SQURVE_DEPLOYMENT_TARGET": "local"}, clear=False):
            response = self.client.post(
                "/api/provider",
                json={},
                headers={"Origin": "http://localhost:7860"},
            )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json["message"], "provider is required")

    def test_hosted_policy_still_rejects_local_routes_from_port_7860(self):
        headers = {"Origin": "http://localhost:7860"}
        with patch.dict(os.environ, {"SQURVE_DEPLOYMENT_TARGET": "hf-space"}, clear=False):
            provider = self.client.post("/api/provider", json={}, headers=headers)
        self.assertEqual(provider.status_code, 403)
        self.assertEqual(provider.json["reason"], "local_only")

    def test_removed_coding_agent_terminal_api_is_not_exposed(self):
        for target in ("local", "hf-space"):
            with self.subTest(target=target):
                with patch.dict(os.environ, {"SQURVE_DEPLOYMENT_TARGET": target}, clear=False):
                    response = self.client.get("/api/terminals")
                self.assertEqual(response.status_code, 404)
                self.assertEqual(response.json, {"message": "API route not found."})


if __name__ == "__main__":
    unittest.main()

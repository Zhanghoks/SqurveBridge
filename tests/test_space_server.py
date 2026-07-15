import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


class SpaceServerTests(unittest.TestCase):
    def test_serves_the_existing_vite_build_and_api(self):
        from demo import space_server

        with tempfile.TemporaryDirectory() as directory:
            dist = Path(directory)
            (dist / "assets").mkdir()
            (dist / "index.html").write_text("<title>SqurveBridge</title>", encoding="utf-8")
            (dist / "assets" / "app.js").write_text("window.demo=true", encoding="utf-8")
            with patch.object(space_server, "DIST_DIR", dist):
                client = space_server.app.test_client()
                for path in ("/", "/studio"):
                    with client.get(path) as response:
                        self.assertEqual(response.status_code, 200)
                with client.get("/assets/app.js") as response:
                    self.assertEqual(response.status_code, 200)
                    self.assertEqual(response.data, b"window.demo=true")
                    self.assertEqual(response.mimetype, "text/javascript")
                with client.get("/api/health") as response:
                    self.assertEqual(response.json["status"], "ok")

    def test_unknown_api_paths_are_json_404_for_get_post_and_put(self):
        from demo import space_server

        with patch.dict(os.environ, {"SQURVE_DEPLOYMENT_TARGET": "local"}, clear=False):
            client = space_server.app.test_client()
            for path in ("/api", "/api/not-a-route"):
                for method in ("GET", "POST", "PUT"):
                    with self.subTest(path=path, method=method):
                        response = client.open(path, method=method)
                        self.assertEqual(response.status_code, 404)
                        self.assertEqual(response.mimetype, "application/json")
                        self.assertEqual(response.json, {"message": "API route not found."})

    def test_hosted_policy_does_not_mask_unknown_api_routes(self):
        from demo import space_server

        with patch.dict(os.environ, {"SQURVE_DEPLOYMENT_TARGET": "hf-space"}, clear=False):
            client = space_server.app.test_client()
            for method in ("GET", "POST", "PUT"):
                with self.subTest(method=method):
                    response = client.open("/api/terminals/not-a-route", method=method)
                    self.assertEqual(response.status_code, 404)
                    self.assertEqual(response.mimetype, "application/json")
                    self.assertEqual(response.json, {"message": "API route not found."})

    def test_known_api_routes_keep_their_method_semantics(self):
        from demo import space_server

        with patch.dict(os.environ, {"SQURVE_DEPLOYMENT_TARGET": "local"}, clear=False):
            client = space_server.app.test_client()
            self.assertEqual(client.get("/api/health").status_code, 200)
            self.assertEqual(client.post("/api/health").status_code, 405)
            self.assertEqual(client.put("/api/health").status_code, 405)
            self.assertEqual(client.post("/api/provider", json={}).status_code, 400)
            self.assertEqual(client.get("/api/provider").status_code, 405)
            self.assertEqual(client.put("/api/provider").status_code, 405)

    def test_traversal_targets_are_indistinguishable_from_spa_routes(self):
        from demo import space_server

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            dist = root / "dist"
            dist.mkdir()
            index = b"<title>SqurveBridge</title>"
            secret = b"do-not-expose-this-content"
            (dist / "index.html").write_bytes(index)
            (root / "secret.js").write_bytes(secret)
            with patch.object(space_server, "DIST_DIR", dist):
                client = space_server.app.test_client()
                for parent in ("..", "%2e%2e"):
                    with self.subTest(parent=parent):
                        with (
                            client.get(f"/{parent}/secret.js") as existing,
                            client.get(f"/{parent}/missing.js") as missing,
                        ):
                            self.assertEqual(existing.status_code, 200)
                            self.assertEqual(existing.data, index)
                            self.assertEqual(existing.mimetype, "text/html")
                            self.assertEqual(
                                (existing.status_code, existing.content_type, existing.data),
                                (missing.status_code, missing.content_type, missing.data),
                            )
                            self.assertNotIn(secret, existing.data)
                            self.assertNotIn(secret, missing.data)

    def test_import_is_safe_after_the_api_app_has_served_a_request(self):
        project_root = Path(__file__).resolve().parents[1]
        script = """
from demo.api_server import app as api_app
assert api_app.test_client().get('/api/health').status_code == 200
from demo import space_server
assert space_server.app is not api_app
assert space_server.app.test_client().get('/api/health').status_code == 200
"""
        result = subprocess.run(
            [sys.executable, "-c", script],
            cwd=project_root,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()

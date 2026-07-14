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
                for path in ("/", "/studio", "/assets/app.js"):
                    with client.get(path) as response:
                        self.assertEqual(response.status_code, 200)
                with client.get("/api/health") as response:
                    self.assertEqual(response.json["status"], "ok")
                with client.get("/api/not-a-route") as response:
                    self.assertEqual(response.status_code, 404)
                    self.assertEqual(response.json, {"message": "API route not found."})


if __name__ == "__main__":
    unittest.main()

import importlib
import unittest
from pathlib import Path

from flask import Flask


class FakeSock:
    def __init__(self):
        self.handlers = {}

    def route(self, path):
        def decorator(function):
            self.handlers[path] = function
            return function

        return decorator


class FakeSession:
    next_id = 0

    def __init__(self, settings):
        self.settings = settings
        type(self).next_id += 1
        self.session_id = f"session{type(self).next_id}"
        self.running = True
        self.prompts = []

    def public_state(self):
        return {
            "session_id": self.session_id,
            "backend": "pi",
            "profile": self.settings.profile,
            "running": self.running,
        }

    def send_prompt(self, prompt):
        self.prompts.append(prompt)

    def read(self, cursor):
        return ([{"type": "ready", "backend": "pi"}], 1)

    def wait_read(self, cursor, timeout=.25):
        return self.read(cursor)

    def stop(self):
        self.running = False


class DisconnectingWebSocket:
    def __init__(self):
        self.messages = []

    def send(self, message):
        self.messages.append(message)

    def receive(self, timeout=None):
        raise ConnectionError("browser disconnected")

    def close(self):
        pass


class PiApiTests(unittest.TestCase):
    def api_module(self):
        try:
            return importlib.import_module("demo.pi_api")
        except ModuleNotFoundError:
            self.fail("demo.pi_api must expose the Pi chat API")

    def make_client(self, environment=None):
        module = self.api_module()
        app = Flask(__name__)
        sock = FakeSock()
        registry = module.register_pi_routes(
            app,
            sock,
            Path("/workspace"),
            environment=environment or {},
            session_factory=FakeSession,
        )
        return app.test_client(), registry, sock

    def test_catalog_exposes_pi_and_project_skills(self):
        client, _, _ = self.make_client({"SQURVE_DEPLOYMENT_TARGET": "hf-space"})
        response = client.get("/api/agent")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json["backend"], "pi")
        self.assertEqual(response.json["profile"], "hosted-readonly")
        self.assertEqual(response.json["skills"], [])

    def test_catalog_discovers_all_skills_from_the_project(self):
        module = self.api_module()
        with self.subTest("real project root"):
            app = Flask(__name__)
            sock = FakeSock()
            root = Path(__file__).resolve().parents[1]
            module.register_pi_routes(
                app,
                sock,
                root,
                environment={},
                session_factory=FakeSession,
            )
            response = app.test_client().get("/api/agent")
        self.assertEqual(
            set(response.json["skills"]),
            module.discover_pi_skills(root),
        )

    def test_session_accepts_chat_messages_and_returns_events(self):
        client, registry, sock = self.make_client()
        started = client.post("/api/agent/sessions", json={})
        self.assertEqual(started.status_code, 201)
        session_id = started.json["session_id"]
        sent = client.post(f"/api/agent/sessions/{session_id}/messages", json={"message": "/run smoke"})
        self.assertEqual(sent.status_code, 202)
        self.assertEqual(registry.get(session_id).prompts, ["/run smoke"])
        events = client.get(f"/api/agent/sessions/{session_id}/events?cursor=0")
        self.assertEqual(events.json["events"][0]["type"], "ready")
        self.assertIn("/api/agent/sessions/<session_id>/ws", sock.handlers)

    def test_stop_closes_the_pi_session(self):
        client, registry, _ = self.make_client()
        session_id = client.post("/api/agent/sessions", json={}).json["session_id"]
        response = client.post(f"/api/agent/sessions/{session_id}/stop")
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(registry.get(session_id))

    def test_websocket_disconnect_stops_and_removes_session(self):
        client, registry, sock = self.make_client()
        session_id = client.post("/api/agent/sessions", json={}).json["session_id"]
        session = registry.get(session_id)

        sock.handlers["/api/agent/sessions/<session_id>/ws"](
            DisconnectingWebSocket(), session_id
        )

        self.assertFalse(session.running)
        self.assertIsNone(registry.get(session_id))

    def test_hosted_space_limits_agent_sessions_below_http_thread_capacity(self):
        client, _, _ = self.make_client({"SQURVE_DEPLOYMENT_TARGET": "hf-space"})
        self.assertEqual(client.post("/api/agent/sessions", json={}).status_code, 201)
        self.assertEqual(client.post("/api/agent/sessions", json={}).status_code, 201)
        blocked = client.post("/api/agent/sessions", json={})
        self.assertEqual(blocked.status_code, 409)
        self.assertIn("limit", blocked.json["message"])


if __name__ == "__main__":
    unittest.main()

import importlib
import io
import json
import threading
import unittest
from pathlib import Path


class PiBackendTests(unittest.TestCase):
    def backend(self):
        try:
            return importlib.import_module("demo.pi_backend")
        except ModuleNotFoundError:
            self.fail("demo.pi_backend must provide the embedded Pi backend")

    def test_hosted_profile_is_read_only(self):
        backend = self.backend()
        settings = backend.PiBackendSettings.from_environment(
            {
                "SQURVE_DEPLOYMENT_TARGET": "hf-space",
                "SQURVE_LLM_PROVIDER": "deepseek",
                "SQURVE_LLM_MODEL": "deepseek-chat",
            },
            Path("/workspace"),
        )
        self.assertEqual(settings.profile, "hosted-readonly")
        self.assertEqual(settings.tools, ("read", "grep", "find", "ls"))
        self.assertIsNone(settings.provider)
        self.assertIsNone(settings.model)

    def test_local_profile_uses_full_pi_coding_tools(self):
        backend = self.backend()
        settings = backend.PiBackendSettings.from_environment(
            {"SQURVE_DEPLOYMENT_TARGET": "local"},
            Path("/workspace"),
        )
        self.assertEqual(settings.profile, "local-full")
        self.assertEqual(
            settings.tools,
            ("read", "bash", "edit", "write", "grep", "find", "ls"),
        )

    def test_skill_shortcut_uses_pi_skill_command(self):
        backend = self.backend()
        self.assertEqual(
            backend.normalize_pi_prompt("/candidate-reader https://example.test/repo"),
            "/skill:candidate-reader https://example.test/repo",
        )
        self.assertEqual(backend.normalize_pi_prompt("/skill:run smoke"), "/skill:run smoke")
        self.assertEqual(backend.normalize_pi_prompt("Explain this run"), "Explain this run")

    def test_protocol_reader_accepts_split_json_lines(self):
        backend = self.backend()
        reader = backend.PiEventDecoder()
        self.assertEqual(reader.feed('{"type":"ready"}\n{"type":"message'), [{"type": "ready"}])
        self.assertEqual(reader.feed('_update","delta":"ok"}\n'), [{"type": "message_update", "delta": "ok"}])

    def test_bridge_command_points_inside_squrvebridge(self):
        backend = self.backend()
        settings = backend.PiBackendSettings.from_environment({}, Path("/workspace"))
        command = settings.command()
        self.assertEqual(command[0], "node")
        self.assertEqual(command[1], "/workspace/demo/pi_agent_bridge.mjs")
        payload = json.loads(command[command.index("--tools") + 1])
        self.assertEqual(payload, list(settings.tools))

    def test_hosted_child_environment_exposes_no_provider_keys(self):
        backend = self.backend()
        settings = backend.PiBackendSettings.from_environment(
            {
                "SQURVE_DEPLOYMENT_TARGET": "hf-space",
                "PI_AGENT_PROVIDER": "qwen",
                "PI_AGENT_MODEL": "qwen-plus",
                "PATH": "/usr/bin",
                "HOME": "workspace-home",
                "QWEN_API_KEY": "active-key",
                "OPENAI_API_KEY": "other-provider-key",
                "HF_TOKEN": "hub-secret",
            },
            Path("/workspace"),
        )
        child = settings.child_environment()
        self.assertEqual(child["PATH"], "/usr/bin")
        self.assertNotIn("QWEN_API_KEY", child)
        self.assertNotIn("OPENAI_API_KEY", child)
        self.assertNotIn("HF_TOKEN", child)

    def test_session_accepts_only_typed_client_commands_without_public_secret_echo(self):
        backend = self.backend()
        session = backend.PiAgentSession.__new__(backend.PiAgentSession)
        session.settings = backend.PiBackendSettings.from_environment(
            {"SQURVE_DEPLOYMENT_TARGET": "hf-space"},
            Path("/workspace"),
        )
        session.session_id = "session-safe"
        session._closed = False

        class InputProcess:
            def __init__(self):
                self.stdin = io.StringIO()

            def poll(self):
                return None

        session.process = InputProcess()
        session.send_command({
            "type": "auth_prompt_response",
            "request_id": "auth-1",
            "value": "pi-command-secret",
        })
        written = json.loads(session.process.stdin.getvalue())
        self.assertEqual(written["value"], "pi-command-secret")
        self.assertNotIn("pi-command-secret", json.dumps(session.public_state()))
        with self.assertRaisesRegex(ValueError, "Unsupported Pi client command"):
            session.send_command({"type": "unknown", "value": "must-not-echo"})

    def test_hosted_stderr_is_not_forwarded_to_browser_events(self):
        backend = self.backend()
        session = backend.PiAgentSession.__new__(backend.PiAgentSession)
        session.settings = backend.PiBackendSettings.from_environment(
            {"SQURVE_DEPLOYMENT_TARGET": "hf-space"},
            Path("/workspace"),
        )
        session._condition = threading.Condition(threading.RLock())
        session._events = []
        session._event_base = 0
        session.process = type("Process", (), {"stderr": io.StringIO("provider pi-stderr-secret\n")})()

        session._read_stderr()

        self.assertNotIn("pi-stderr-secret", json.dumps(session._events))

    def test_qwen_model_config_uses_environment_secret(self):
        config_path = Path(__file__).resolve().parents[1] / "config" / "pi_models.json"
        self.assertTrue(config_path.is_file(), "config/pi_models.json must configure Pi providers")
        config = json.loads(config_path.read_text(encoding="utf-8"))
        qwen = config["providers"]["qwen"]
        self.assertEqual(qwen["apiKey"], "$QWEN_API_KEY")
        self.assertTrue(qwen["baseUrl"].startswith("https://"))
        self.assertIn("qwen-plus", [model["id"] for model in qwen["models"]])

    def test_discovers_every_project_skill_from_the_skill_root(self):
        backend = self.backend()
        root = Path(__file__).resolve().parents[1]
        discovered = backend.discover_pi_skills(root)
        self.assertEqual(
            len(discovered),
            len(list((root / "skills").glob("*/SKILL.md"))),
        )
        self.assertIn("meta-evo", discovered)
        self.assertNotIn("Meta-Evo", discovered)
        self.assertGreater(len(discovered), len(backend.PI_SKILLS))

    def test_event_cursor_remains_absolute_after_buffer_trimming(self):
        backend = self.backend()
        session = backend.PiAgentSession.__new__(backend.PiAgentSession)
        session._condition = threading.Condition(threading.RLock())
        session._events = []
        session._event_base = 0
        session._closed = False
        for number in range(5001):
            session._append({"number": number})

        events, cursor = session.read(0)
        self.assertEqual(events[0], {"number": 1001})
        self.assertEqual(cursor, 5001)
        session._append({"number": 5001})
        self.assertEqual(session.read(cursor), ([{"number": 5001}], 5002))

    def test_session_streams_events_and_sends_normalized_prompts(self):
        backend = self.backend()

        class FakeProcess:
            def __init__(self):
                self.stdin = io.StringIO()
                self.stdout = io.StringIO('{"type":"ready","skills":["run"]}\n')
                self.stderr = io.StringIO()
                self.returncode = None

            def poll(self):
                return self.returncode

            def wait(self, timeout=None):
                self.returncode = 0
                return 0

            def terminate(self):
                self.returncode = 0

            def kill(self):
                self.returncode = -9

        created = []

        def process_factory(command, **kwargs):
            created.append((command, kwargs))
            return FakeProcess()

        settings = backend.PiBackendSettings.from_environment({}, Path("/workspace"))
        session = backend.PiAgentSession(settings, process_factory=process_factory)
        events, cursor = session.wait_read(0, timeout=1)
        self.assertEqual(events[0]["type"], "ready")
        self.assertGreater(cursor, 0)
        session.send_prompt("/run smoke")
        written = json.loads(session.process.stdin.getvalue().strip())
        self.assertEqual(written, {"type": "prompt", "message": "/skill:run smoke"})
        self.assertEqual(created[0][0], settings.command())
        self.assertFalse(created[0][1]["shell"])
        session.stop()


if __name__ == "__main__":
    unittest.main()

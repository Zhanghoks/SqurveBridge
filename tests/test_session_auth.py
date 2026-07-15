import unittest

from demo.session_auth import (
    SessionCredentialRegistry,
    SqlCredential,
    new_session_id,
    session_log_id,
)


class FakeClock:
    def __init__(self) -> None:
        self.value = 100.0

    def __call__(self) -> float:
        return self.value

    def advance(self, seconds: float) -> None:
        self.value += seconds


class SessionCredentialRegistryTests(unittest.TestCase):
    def test_credentials_are_isolated_and_expire_after_idle_timeout(self):
        clock = FakeClock()
        registry = SessionCredentialRegistry(max_sessions=2, idle_timeout=1800, clock=clock)
        registry.put("browser-a", SqlCredential("qwen", "qwen-plus", "key-a"))
        registry.put("browser-b", SqlCredential("deepseek", "deepseek-chat", "key-b"))

        self.assertEqual(registry.get("browser-a").api_key, "key-a")
        self.assertEqual(registry.get("browser-b").api_key, "key-b")

        clock.advance(1801)
        self.assertIsNone(registry.get("browser-a"))
        self.assertIsNone(registry.get("browser-b"))

    def test_capacity_evicts_the_least_recently_used_session(self):
        clock = FakeClock()
        registry = SessionCredentialRegistry(max_sessions=2, clock=clock)
        registry.put("a", SqlCredential("qwen", "qwen-plus", "key-a"))
        clock.advance(1)
        registry.put("b", SqlCredential("qwen", "qwen-plus", "key-b"))
        clock.advance(1)
        self.assertIsNotNone(registry.get("a"))
        clock.advance(1)
        registry.put("c", SqlCredential("qwen", "qwen-plus", "key-c"))

        self.assertIsNotNone(registry.get("a"))
        self.assertIsNone(registry.get("b"))
        self.assertIsNotNone(registry.get("c"))

    def test_status_and_delete_never_return_the_secret(self):
        registry = SessionCredentialRegistry()
        registry.put(
            "browser-a",
            SqlCredential("qwen", "qwen-plus", "secret-sentinel", validated_at=123.0),
        )

        self.assertEqual(
            registry.status("browser-a"),
            {
                "configured": True,
                "provider": "qwen",
                "model": "qwen-plus",
                "validated_at": 123.0,
            },
        )
        self.assertNotIn("secret-sentinel", repr(registry.status("browser-a")))
        self.assertTrue(registry.delete("browser-a"))
        self.assertFalse(registry.delete("browser-a"))
        self.assertEqual(registry.status("browser-a"), {"configured": False})

    def test_session_identifiers_are_opaque_and_log_ids_are_one_way(self):
        first = new_session_id()
        second = new_session_id()

        self.assertNotEqual(first, second)
        self.assertGreaterEqual(len(first), 32)
        self.assertEqual(session_log_id(first), session_log_id(first))
        self.assertNotEqual(session_log_id(first), session_log_id(second))
        self.assertNotIn(first, session_log_id(first))


if __name__ == "__main__":
    unittest.main()

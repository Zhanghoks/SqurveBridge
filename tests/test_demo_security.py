import unittest

from demo.security import AGENT_TERMINAL_ENV, agent_terminals_enabled


class DemoSecurityTests(unittest.TestCase):
    def test_agent_terminal_catalog_is_disabled_by_default(self) -> None:
        self.assertFalse(agent_terminals_enabled({}))

    def test_agent_terminal_start_requires_explicit_opt_in(self) -> None:
        self.assertTrue(agent_terminals_enabled({AGENT_TERMINAL_ENV: "1"}))
        self.assertTrue(agent_terminals_enabled({AGENT_TERMINAL_ENV: "true"}))
        self.assertFalse(agent_terminals_enabled({AGENT_TERMINAL_ENV: "0"}))


if __name__ == "__main__":
    unittest.main()

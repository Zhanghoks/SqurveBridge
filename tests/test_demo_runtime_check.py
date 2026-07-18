import contextlib
import io
import unittest
from unittest.mock import patch

from demo import runtime_check


class DemoRuntimeCheckTests(unittest.TestCase):
    def test_reports_the_missing_config_runtime_dependency(self):
        found = {"flask", "flask_sock", "numpy", "pandas", "torch"}

        self.assertEqual(
            runtime_check.missing_modules(find_spec=lambda name: object() if name in found else None),
            ["llama_index"],
        )

    def test_main_fails_with_install_guidance_for_an_incomplete_environment(self):
        stderr = io.StringIO()
        with (
            patch.object(runtime_check, "missing_modules", return_value=["llama_index"]),
            contextlib.redirect_stderr(stderr),
        ):
            result = runtime_check.main()

        self.assertEqual(result, 1)
        self.assertIn("llama_index", stderr.getvalue())
        self.assertIn("requirements.txt", stderr.getvalue())
        self.assertIn("demo/requirements.txt", stderr.getvalue())

    def test_main_passes_for_a_complete_environment(self):
        with patch.object(runtime_check, "missing_modules", return_value=[]):
            self.assertEqual(runtime_check.main(), 0)


if __name__ == "__main__":
    unittest.main()

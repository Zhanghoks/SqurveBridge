import tempfile
import unittest
from pathlib import Path

from tools import release_check


class ReleaseCheckTests(unittest.TestCase):
    def test_build_checks_separates_pointer_and_full_archive_validation(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            pointer_checks = release_check.build_checks(
                root, full=False, history=False, tests=False
            )
            full_checks = release_check.build_checks(root, full=True, history=True, tests=False)

        pointer_commands = [check.command for check in pointer_checks]
        full_commands = [check.command for check in full_checks]
        self.assertTrue(any("verify-pointers" in command for command in pointer_commands))
        self.assertFalse(any("verify-archives" in command for command in pointer_commands))
        self.assertTrue(any("verify-archives" in command for command in full_commands))
        self.assertTrue(any("--history" in command for command in full_commands))

    def test_document_links_are_resolved_relative_to_each_document(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / "docs").mkdir()
            (root / "target.md").write_text("ok\n", encoding="utf-8")
            (root / "README.md").write_text("[target](target.md)\n", encoding="utf-8")
            (root / "docs" / "guide.md").write_text(
                "[target](../target.md)\n[missing](missing.md)\n", encoding="utf-8"
            )

            errors = release_check.validate_document_links(root)

        self.assertEqual(errors, ["docs/guide.md -> missing.md"])

    def test_metadata_validation_requires_release_files_and_citation_fields(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            errors = release_check.validate_release_metadata(root)

        self.assertIn("missing required release file: README.md", errors)
        self.assertIn("missing required release file: CITATION.cff", errors)


if __name__ == "__main__":
    unittest.main()

import json
import tempfile
import unittest
from pathlib import Path

from tools import anonymity_scan


ROOT = Path(__file__).resolve().parent.parent


class AnonymityScanTests(unittest.TestCase):
    def test_scan_path_reports_category_without_denylist_value(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            target = root / "README.md"
            marker = "private" + "-marker"
            target.write_text(f"Do not publish {marker}.\n", encoding="utf-8")

            findings = anonymity_scan.scan_path(target, root, (marker,))
            rendered = "\n".join(finding.render(root) for finding in findings)

        self.assertIn("denylist term", rendered)
        self.assertNotIn(marker, rendered)

    def test_placeholder_identity_is_allowed(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            target = root / "notes.txt"
            target.write_text(
                "Contact maintainer@example.com from /Users/example/project.\n",
                encoding="utf-8",
            )

            findings = anonymity_scan.scan_path(target, root)

        self.assertEqual(findings, [])

    def test_real_home_path_and_personal_email_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            target = root / "notes.txt"
            home = "/Users/" + "private-user" + "/project"
            email = "author" + "@" + "private.invalid"
            target.write_text(f"{home}\n{email}\n", encoding="utf-8")

            categories = {
                finding.category for finding in anonymity_scan.scan_path(target, root)
            }

        self.assertEqual(categories, {"absolute user path", "personal email"})

    def test_vendored_pi_authorship_is_not_treated_as_project_identity(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            upstream = root / "pi" / "README.md"
            upstream.parent.mkdir()
            upstream_email = "maintainer" + "@" + "upstream.invalid"
            upstream.write_text(
                f"Upstream author: {upstream_email}\n",
                encoding="utf-8",
            )
            project = root / "notes.txt"
            project_email = "maintainer" + "@" + "project.invalid"
            project.write_text(
                f"Project author: {project_email}\n",
                encoding="utf-8",
            )

            findings = anonymity_scan.scan_paths([upstream, project], root)

        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].path, project)

    def test_public_document_manuscript_language_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            target = root / "README.md"
            target.write_text("## Paper at a Glance\n", encoding="utf-8")

            findings = anonymity_scan.scan_path(target, root)

        self.assertEqual(findings[0].category, "submission narrative")

    def test_sensitive_public_path_is_rejected_without_reading_content(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            target = root / "rebuttal" / "notes.md"
            target.parent.mkdir()
            target.write_text("content\n", encoding="utf-8")

            findings = anonymity_scan.scan_path(target, root)

        self.assertEqual(findings[0].category, "private submission path")

    def test_load_denylist_ignores_comments_and_blank_lines(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / ".anonymity-denylist"
            path.write_text("# local only\n\nfirst\n second \n", encoding="utf-8")

            terms = anonymity_scan.load_denylist(path)

        self.assertEqual(terms, ("first", "second"))


class AnonymityRepositoryTests(unittest.TestCase):
    def test_release_metadata_is_anonymous(self) -> None:
        citation = (ROOT / "CITATION.cff").read_text(encoding="utf-8")
        pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
        package = json.loads(
            (ROOT / "demo-app/package.json").read_text(encoding="utf-8")
        )

        self.assertIn('name: "Anonymous Authors"', citation)
        self.assertIn('{ name = "Anonymous Authors" }', pyproject)
        self.assertNotIn("repository", package)


if __name__ == "__main__":
    unittest.main()

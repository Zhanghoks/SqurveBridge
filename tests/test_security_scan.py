import tempfile
import unittest
import zipfile
from pathlib import Path

from tools import security_scan


class SecurityScanTests(unittest.TestCase):
    def test_placeholder_credentials_are_allowed(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            path = root / ".env.example"
            path.write_text("OPENAI_API_KEY=your-api-key-here\n", encoding="utf-8")

            self.assertEqual(security_scan.scan_path(path, root), [])

    def test_realistic_token_is_reported_without_leaking_value(self) -> None:
        token = "sk-" + "A" * 48
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            path = root / "config.py"
            path.write_text(f'OPENAI_API_KEY = "{token}"\n', encoding="utf-8")

            findings = security_scan.scan_path(path, root)

        self.assertTrue(findings)
        self.assertNotIn(token, "\n".join(finding.render() for finding in findings))

    def test_private_key_filename_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            path = root / "deploy.pem"
            path.write_text("not-a-real-key\n", encoding="utf-8")

            findings = security_scan.scan_path(path, root)

        self.assertTrue(findings)

    def test_vendored_pi_ignores_fixture_heuristics_but_scans_real_tokens(self) -> None:
        token = "sk-" + "C" * 48
        fixture_value = "upstream-" + "fixture-value"
        credential_name = "api_" + "key"
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            store = root / "pi" / "src" / "credential-store.ts"
            store.parent.mkdir(parents=True)
            store.write_text(
                f'const {credential_name} = "{fixture_value}"\n',
                encoding="utf-8",
            )
            leak = root / "pi" / "src" / "leak.ts"
            leak.write_text(f'const value = "{token}"\n', encoding="utf-8")

            findings = security_scan.scan_paths([store, leak], root)

        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].path, "pi/src/leak.ts")
        self.assertEqual(findings[0].category, "openai-style-token")

    def test_archive_path_traversal_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            path = root / "benchmark.zip"
            with zipfile.ZipFile(path, "w") as archive:
                archive.writestr("../outside.txt", "unsafe")

            findings = security_scan.scan_zip_path(path, root)

        self.assertIn("unsafe-archive-path", {finding.category for finding in findings})

    def test_archive_secret_is_reported_without_leaking_value(self) -> None:
        token = "sk-" + "B" * 48
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            path = root / "benchmark.zip"
            with zipfile.ZipFile(path, "w") as archive:
                archive.writestr("spider/config.txt", f'api_key = "{token}"\n')

            findings = security_scan.scan_zip_path(path, root)

        rendered = "\n".join(finding.render() for finding in findings)
        self.assertIn("openai-style-token", rendered)
        self.assertNotIn(token, rendered)

    def test_archive_symlink_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            path = root / "benchmark.zip"
            member = zipfile.ZipInfo("spider/link")
            member.create_system = 3
            member.external_attr = (0o120777 << 16)
            with zipfile.ZipFile(path, "w") as archive:
                archive.writestr(member, "target")

            findings = security_scan.scan_zip_path(path, root)

        self.assertIn("archive-symlink", {finding.category for finding in findings})

    def test_git_lfs_pointer_is_not_treated_as_a_broken_zip(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            path = root / "benchmark.zip"
            path.write_text(
                "version https://git-lfs.github.com/spec/v1\n"
                "oid sha256:" + "a" * 64 + "\n"
                "size 123456\n",
                encoding="utf-8",
            )

            findings = security_scan.scan_zip_path(path, root)

        self.assertEqual(findings, [])


if __name__ == "__main__":
    unittest.main()

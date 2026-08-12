"""Smoke tests for the Claude Code / Codex symlink harness installer.

The installer resolves the repository root from its own location, so the
tests copy it into a disposable mini-repo and run it there; the real
checkout is never touched.
"""

from __future__ import annotations

import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INSTALLER = ROOT / "harness" / "install_squrve_harness.sh"


def _make_mini_repo(base: Path, skills: tuple[str, ...] = ("candidate-reader", "run")) -> Path:
    # macOS tempdirs live behind the /var -> /private/var symlink; the
    # installer compares physical paths, so anchor the mini-repo physically.
    repo = base.resolve() / "mini-repo"
    (repo / "harness").mkdir(parents=True)
    shutil.copy2(INSTALLER, repo / "harness" / INSTALLER.name)
    for name in skills:
        skill_dir = repo / "skills" / name
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text(f"name: {name}\n", encoding="utf-8")
    (repo / "skills" / "shared-references").mkdir()
    (repo / "skills" / "shared-references" / "README.md").write_text("shared\n", encoding="utf-8")
    (repo / "tools").mkdir()
    (repo / "templates").mkdir()
    return repo


def _run_installer(repo: Path, *flags: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["bash", str(repo / "harness" / INSTALLER.name), ".", "--quiet", *flags],
        cwd=repo,
        capture_output=True,
        text=True,
    )


class HarnessInstallTests(unittest.TestCase):
    def test_one_command_provisions_claude_and_codex_symlinks(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = _make_mini_repo(Path(tmp))
            result = _run_installer(repo)
            self.assertEqual(result.returncode, 0, result.stderr)

            for platform_dir in (".claude/skills", ".agents/skills"):
                for name in ("candidate-reader", "run", "shared-references"):
                    link = repo / platform_dir / name
                    self.assertTrue(link.is_symlink(), f"{link} must be a symlink")
                    self.assertEqual(link.readlink().as_posix(), f"../../skills/{name}")
                    self.assertTrue(link.resolve().is_dir(), f"{link} must resolve")

            for resource in ("tools", "templates"):
                link = repo / ".squrve" / resource
                self.assertTrue(link.is_symlink())
                self.assertTrue(link.resolve().is_dir())

            manifest = repo / ".squrve" / "installed-harness.txt"
            self.assertTrue(manifest.is_file())
            self.assertIn("candidate-reader", manifest.read_text(encoding="utf-8"))

    def test_dry_run_touches_nothing(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = _make_mini_repo(Path(tmp))
            result = _run_installer(repo, "--dry-run")
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertFalse((repo / ".claude" / "skills" / "run").exists())
            self.assertFalse((repo / ".squrve" / "installed-harness.txt").exists())

    def test_reinstall_is_idempotent_and_prunes_stale_links(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = _make_mini_repo(Path(tmp))
            self.assertEqual(_run_installer(repo).returncode, 0)

            first = sorted(p.name for p in (repo / ".claude" / "skills").iterdir())
            result = _run_installer(repo)
            self.assertEqual(result.returncode, 0, result.stderr)
            second = sorted(p.name for p in (repo / ".claude" / "skills").iterdir())
            self.assertEqual(first, second)

            shutil.rmtree(repo / "skills" / "run")
            result = _run_installer(repo, "--reconcile")
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertFalse((repo / ".claude" / "skills" / "run").exists())
            self.assertFalse((repo / ".agents" / "skills" / "run").exists())
            self.assertTrue((repo / ".claude" / "skills" / "candidate-reader").is_symlink())

    def test_refuses_to_run_outside_the_repo_root(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = _make_mini_repo(Path(tmp))
            elsewhere = Path(tmp) / "elsewhere"
            elsewhere.mkdir()
            result = subprocess.run(
                ["bash", str(repo / "harness" / INSTALLER.name), str(elsewhere), "--quiet"],
                cwd=tmp,
                capture_output=True,
                text=True,
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("workbench-local", result.stderr)

    def test_real_checkout_symlinks_resolve_if_installed(self):
        """If the developer has run the installer here, links must not dangle."""
        for platform_dir in (ROOT / ".claude" / "skills", ROOT / ".agents" / "skills"):
            if not platform_dir.is_dir():
                continue
            for link in platform_dir.iterdir():
                if link.is_symlink():
                    self.assertTrue(
                        link.resolve().exists(),
                        f"dangling harness symlink: {link}",
                    )


if __name__ == "__main__":
    unittest.main()

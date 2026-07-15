import tempfile
import unittest
from pathlib import Path

from tools.build_hf_space import build_space
from tools.security_scan import scan_paths


RUNTIME_DIRECTORIES = (
    "core",
    "demo",
    "demo-app",
    "pi",
    "skills",
    "templates",
    "reproduce",
    "config",
    "benchmarks/spider",
    "evidence/reported-results",
    "tools",
)
RUNTIME_FILES = ("LICENSE", "pyproject.toml", "requirements.txt")


def _write_minimal_runtime(root: Path) -> None:
    for relative in RUNTIME_DIRECTORIES:
        directory = root / relative
        directory.mkdir(parents=True, exist_ok=True)
        (directory / "runtime.txt").write_text(relative, encoding="utf-8")

    for relative in RUNTIME_FILES:
        (root / relative).write_text(relative, encoding="utf-8")

    deploy = root / "deploy" / "huggingface"
    deploy.mkdir(parents=True)
    (deploy / "Dockerfile").write_text("FROM scratch\n", encoding="utf-8")
    (deploy / "README.space.md").write_text("# Space\n", encoding="utf-8")
    (deploy / "Dockerfile.dockerignore").write_text("node_modules\n", encoding="utf-8")


def _require_full_runtime(root: Path) -> None:
    benchmark = root / "benchmarks" / "spider"
    if not benchmark.is_dir():
        raise unittest.SkipTest(
            "full Hugging Face bundle checks require the installed Spider benchmark"
        )


class HuggingFaceBundleContractTests(unittest.TestCase):
    def test_missing_benchmark_skips_only_full_bundle_checks(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(unittest.SkipTest, "Spider benchmark"):
                _require_full_runtime(Path(directory))

    def test_space_builds_and_runs_the_embedded_pi_source(self) -> None:
        root = Path(__file__).resolve().parents[1]
        dockerfile = (root / "deploy/huggingface/Dockerfile").read_text(encoding="utf-8")
        build_script = (root / "demo/build_embedded_pi.sh").read_text(encoding="utf-8")
        self.assertIn("FROM node:22-bookworm-slim AS pi-builder", dockerfile)
        self.assertIn("bash demo/build_embedded_pi.sh", dockerfile)
        self.assertIn("COPY --from=pi-builder /build/pi /app/pi", dockerfile)
        self.assertIn("node --version", dockerfile)
        self.assertIn("SQURVE_LLM_PROVIDER=qwen", dockerfile)
        self.assertIn("SQURVE_LLM_MODEL=qwen-plus", dockerfile)
        self.assertIn("npm ci --ignore-scripts", build_script)
        self.assertNotIn("npm run build", build_script)
        self.assertIn("packages/coding-agent/tsconfig.build.json", build_script)

    def test_space_dependency_range_keeps_transformers_hub_compatible(self) -> None:
        root = Path(__file__).resolve().parents[1]
        requirements = (root / "requirements.txt").read_text(encoding="utf-8")
        self.assertIn("gradio>=4.0.0,<5.0.0", requirements)

    def test_gradio_dependency_constraints_are_compatible(self) -> None:
        root = Path(__file__).resolve().parents[1]
        requirements = (root / "requirements.txt").read_text(encoding="utf-8")
        self.assertIn("MarkupSafe==2.1.5", requirements)
        self.assertNotIn("MarkupSafe==3.0.2", requirements)
        self.assertIn("pillow==10.4.0", requirements)
        self.assertNotIn("pillow==11.2.1", requirements)
        self.assertIn("tomlkit==0.12.0", requirements)
        self.assertNotIn("tomlkit==0.13.3", requirements)

    def test_runtime_reuses_the_node_images_uid_1000_user(self) -> None:
        root = Path(__file__).resolve().parents[1]
        dockerfile = (root / "deploy/huggingface/Dockerfile").read_text(
            encoding="utf-8"
        )
        self.assertNotIn("useradd --create-home --uid 1000", dockerfile)
        self.assertIn("chown -R node:node /app", dockerfile)
        self.assertIn("USER node", dockerfile)

    def test_small_bundle_rebuild_is_deterministic_and_removes_stale_output(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "root"
            output = Path(directory) / "space"
            root.mkdir()
            _write_minimal_runtime(root)

            (root / "core" / "__pycache__").mkdir()
            (root / "core" / "__pycache__" / "cached.pyc").write_bytes(b"cache")
            (root / "demo-app" / "node_modules").mkdir()
            (root / "demo-app" / "node_modules" / "package.js").write_text(
                "generated", encoding="utf-8"
            )
            (root / "demo-app" / "dist").mkdir()
            (root / "demo-app" / "dist" / "bundle.js").write_text(
                "generated", encoding="utf-8"
            )
            (root / "demo" / ".DS_Store").write_bytes(b"metadata")

            first_manifest = build_space(root, output)
            (output / "stale.txt").write_text("stale", encoding="utf-8")
            second_manifest = build_space(root, output)

            self.assertEqual(first_manifest, second_manifest)
            self.assertFalse((output / "stale.txt").exists())
            self.assertFalse((output / "core" / "__pycache__").exists())
            self.assertFalse((output / "demo-app" / "node_modules").exists())
            self.assertFalse((output / "demo-app" / "dist").exists())
            self.assertFalse((output / "demo" / ".DS_Store").exists())


class HuggingFaceBundleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.root = Path(__file__).resolve().parents[1]
        _require_full_runtime(cls.root)
        cls._temporary_directory = tempfile.TemporaryDirectory()
        cls.output = Path(cls._temporary_directory.name) / "space"
        cls.files = build_space(cls.root, cls.output)
        cls.staged_files = sorted(
            (path for path in cls.output.rglob("*") if path.is_file()),
            key=lambda path: path.relative_to(cls.output).as_posix(),
        )

    @classmethod
    def tearDownClass(cls) -> None:
        cls._temporary_directory.cleanup()

    def test_bundle_contains_runtime_and_exact_space_overlays(self) -> None:
        expected_paths = (
            "core/engine.py",
            "demo/space_server.py",
            "demo-app/src/main.jsx",
            "pi/packages/coding-agent/package.json",
            "pi/packages/ai/src/auth/credential-store.ts",
            "skills/run/SKILL.md",
            "reproduce/run.py",
            "config/sys_config.json",
            "tools/security_scan.py",
            "evidence/reported-results",
            "LICENSE",
            "pyproject.toml",
            "requirements.txt",
            "Dockerfile",
            "README.md",
            ".dockerignore",
            "deploy/huggingface/Dockerfile.dockerignore",
        )
        for relative in expected_paths:
            with self.subTest(relative=relative):
                self.assertTrue((self.output / relative).exists())

        overlays = {
            "Dockerfile": "deploy/huggingface/Dockerfile",
            "README.md": "deploy/huggingface/README.space.md",
            ".dockerignore": "deploy/huggingface/Dockerfile.dockerignore",
        }
        for bundled, source in overlays.items():
            with self.subTest(bundled=bundled):
                self.assertEqual(
                    (self.output / bundled).read_bytes(),
                    (self.root / source).read_bytes(),
                )

    def test_bundle_uses_an_explicit_allowlist_and_excludes_generated_files(self) -> None:
        self.assertEqual(
            {path.name for path in self.output.iterdir()},
            {
                ".dockerignore",
                "Dockerfile",
                "LICENSE",
                "README.md",
                "benchmarks",
                "config",
                "core",
                "demo",
                "demo-app",
                "deploy",
                "evidence",
                "pi",
                "pyproject.toml",
                "reproduce",
                "requirements.txt",
                "skills",
                "templates",
                "tools",
            },
        )

        forbidden_paths = (
            ".env",
            ".git",
            ".agents",
            ".claude",
            ".superpowers",
            "docs/superpowers",
            "tmp",
            "artifacts",
            "paper",
            "benchmarks/packages",
            "demo-app/node_modules",
            "demo-app/dist",
        )
        for relative in forbidden_paths:
            with self.subTest(relative=relative):
                self.assertFalse((self.output / relative).exists())

        forbidden_parts = {
            "__pycache__",
            ".pytest_cache",
            ".mypy_cache",
            ".ruff_cache",
            ".cache",
            "node_modules",
            "dist",
        }
        for relative in self.files:
            path = Path(relative)
            with self.subTest(relative=relative):
                self.assertTrue(forbidden_parts.isdisjoint(path.parts))
                self.assertNotEqual(path.name, ".DS_Store")
                self.assertNotEqual(path.name.lower(), "thumbs.db")
                self.assertFalse(path.name.startswith("._"))
                self.assertNotIn(path.suffix.lower(), {".pyc", ".pyo"})

    def test_bundle_preserves_every_spider_runtime_database(self) -> None:
        source_database_root = self.root / "benchmarks" / "spider" / "database"
        bundled_database_root = self.output / "benchmarks" / "spider" / "database"
        source_databases = sorted(
            path.relative_to(source_database_root).as_posix()
            for path in source_database_root.rglob("*.sqlite")
        )
        bundled_databases = sorted(
            path.relative_to(bundled_database_root).as_posix()
            for path in bundled_database_root.rglob("*.sqlite")
        )

        self.assertGreater(len(source_databases), 0)
        self.assertEqual(bundled_databases, source_databases)

    def test_manifest_is_sorted_complete_and_security_clean(self) -> None:
        staged_manifest = [
            path.relative_to(self.output).as_posix() for path in self.staged_files
        ]
        self.assertEqual(self.files, sorted(set(self.files)))
        self.assertEqual(self.files, staged_manifest)
        self.assertEqual(scan_paths(self.staged_files, self.output), [])

        sensitive_basenames = {
            ".env",
            "credentials.json",
            "service-account.json",
            "service_account.json",
        }
        sensitive_suffixes = {".key", ".pem", ".p12", ".pfx"}
        for path in self.staged_files:
            relative = path.relative_to(self.output).as_posix()
            with self.subTest(path=relative):
                self.assertNotIn(path.name.lower(), sensitive_basenames)
                self.assertNotIn(path.suffix.lower(), sensitive_suffixes)
                if relative != "pi/packages/ai/src/auth/credential-store.ts":
                    self.assertNotIn("credential", path.name.lower())

if __name__ == "__main__":
    unittest.main()

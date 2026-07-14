import tempfile
import unittest
from pathlib import Path

from core.benchmark_requirements import require_benchmark_directory, require_benchmark_file


class BenchmarkFailureTests(unittest.TestCase):
    def test_missing_dataset_fails_with_install_command(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            with self.assertRaisesRegex(
                FileNotFoundError,
                r"python tools/benchmarks\.py install spider",
            ):
                require_benchmark_file(Path(tmpdir) / "spider/dev/dataset.json", "spider", "dataset")

    def test_missing_schema_fails_with_install_command(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            with self.assertRaisesRegex(
                FileNotFoundError,
                r"python tools/benchmarks\.py install spider",
            ):
                require_benchmark_file(Path(tmpdir) / "spider/dev/schema.json", "spider", "schema")

    def test_missing_database_directory_fails_loudly(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            with self.assertRaises(FileNotFoundError):
                require_benchmark_directory(Path(tmpdir) / "spider/database", "spider", "database directory")


if __name__ == "__main__":
    unittest.main()

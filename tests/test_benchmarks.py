from __future__ import annotations

import hashlib
import json
import sqlite3
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest import mock

from tools import benchmarks


class BenchmarkArchiveTests(unittest.TestCase):
    def test_deterministic_build_excludes_local_noise(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "benchmarks" / "sample"
            source.mkdir(parents=True)
            (source / "dataset.json").write_text("[]\n", encoding="utf-8")
            (source / ".DS_Store").write_bytes(b"local")
            (source / "database.sqlite-wal").write_bytes(b"local")
            first = root / "first.zip"
            second = root / "second.zip"
            with mock.patch.object(benchmarks, "BENCHMARK_ROOT", root / "benchmarks"):
                benchmarks._write_deterministic_zip("sample", first)
                benchmarks._write_deterministic_zip("sample", second)
            self.assertEqual(hashlib.sha256(first.read_bytes()).digest(), hashlib.sha256(second.read_bytes()).digest())
            with zipfile.ZipFile(first) as archive:
                self.assertEqual(archive.namelist(), ["sample/dataset.json"])

    def test_archive_inspection_rejects_path_traversal(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            archive_path = Path(directory) / "bad.zip"
            with zipfile.ZipFile(archive_path, "w") as archive:
                archive.writestr("sample/../escaped.txt", "bad")
            entry = {
                "top_level": "sample",
                "sha256": benchmarks._sha256(archive_path),
                "archive_size": archive_path.stat().st_size,
                "uncompressed_size": 3,
                "member_count": 1,
                "allowed_suffixes": [".txt"],
                "required_files": [],
            }
            with self.assertRaisesRegex(benchmarks.BenchmarkError, "unsafe archive member"):
                benchmarks._inspect_archive(archive_path, entry, content_hash=True)

    def test_archive_inspection_rejects_credential_like_member(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            archive_path = Path(directory) / "bad.zip"
            with zipfile.ZipFile(archive_path, "w") as archive:
                archive.writestr("sample/private.pem", "not-a-real-key")
            entry = {
                "top_level": "sample",
                "sha256": benchmarks._sha256(archive_path),
                "archive_size": archive_path.stat().st_size,
                "uncompressed_size": 14,
                "member_count": 1,
                "allowed_suffixes": [".pem"],
                "required_files": [],
            }
            with self.assertRaisesRegex(benchmarks.BenchmarkError, "credential-like"):
                benchmarks._inspect_archive(archive_path, entry, content_hash=True)

    def test_lfs_pointer_parser(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            pointer = Path(directory) / "sample.zip"
            pointer.write_text(
                "version https://git-lfs.github.com/spec/v1\n"
                f"oid sha256:{'a' * 64}\n"
                "size 123\n",
                encoding="utf-8",
            )
            self.assertEqual(benchmarks._is_lfs_pointer(pointer), ("a" * 64, 123))

    def test_verify_tree_checks_dataset_and_sqlite(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "sample"
            split = root / "dev"
            database = split / "database"
            database.mkdir(parents=True)
            (split / "dataset.json").write_text(json.dumps([{"id": 1}]), encoding="utf-8")
            (split / "schema.json").write_text("[]", encoding="utf-8")
            with sqlite3.connect(database / "sample.sqlite") as connection:
                connection.execute("CREATE TABLE example (id INTEGER)")
            entry = {
                "required_files": ["sample/dev/dataset.json", "sample/dev/schema.json"],
                "dataset_counts": {"dev": 1},
                "sqlite_count": 1,
            }
            result = benchmarks._verify_tree("sample", root, entry)
            self.assertEqual(result, {"dataset_counts": {"dev": 1}, "sqlite_count": 1})

    def test_manifest_has_only_approved_archive_paths(self) -> None:
        manifest = benchmarks._load_manifest()
        self.assertEqual(set(manifest["benchmarks"]), {"bird", "bull-en", "ehrsql-2024", "spider"})
        archives = {entry["archive"] for entry in manifest["benchmarks"].values()}
        self.assertEqual(archives, {
            "benchmarks/packages/bird.zip",
            "benchmarks/packages/bull-en.zip",
            "benchmarks/packages/ehrsql-2024.zip",
            "benchmarks/packages/spider.zip",
        })


if __name__ == "__main__":
    unittest.main()

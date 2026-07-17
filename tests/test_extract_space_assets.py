from __future__ import annotations

import tempfile
import unittest
import zipfile
from pathlib import Path

from tools.extract_space_assets import ARCHIVES, extract_space_assets


class SpaceAssetExtractionTests(unittest.TestCase):
    def test_extracts_only_sqlite_and_selected_schema(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            archives = root / "archives"
            output = root / "output"
            archives.mkdir()
            for archive_name in ARCHIVES:
                benchmark = archive_name.removesuffix(".zip")
                schema_split = "valid" if benchmark == "ehrsql-2024" else "dev"
                with zipfile.ZipFile(archives / archive_name, "w") as archive:
                    archive.writestr(f"{benchmark}/database/sample.sqlite", b"SQLite format 3\x00")
                    archive.writestr(f"{benchmark}/{schema_split}/schema.json", "[]")
                    archive.writestr(f"{benchmark}/{schema_split}/dataset.json", "[{\"sql\": \"SELECT 1\"}]")

            self.assertEqual(extract_space_assets(archives, output), 8)
            self.assertFalse(any(output.rglob("dataset.json")))
            self.assertEqual(len(list(output.rglob("*.sqlite"))), 4)

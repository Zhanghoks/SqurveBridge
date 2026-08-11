import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


SPIDER_DOCUMENT = [
    {
        "db_id": "concert_singer",
        "table_names_original": ["stadium", "singer"],
        "column_names_original": [
            [-1, "*"],
            [0, "Stadium_ID"],
            [0, "Name"],
            [1, "Singer_ID"],
            [1, "Name"],
            [1, "Stadium_ID"],
        ],
        "column_types": ["text", "number", "text", "number", "text", "number"],
        "primary_keys": [1, 3],
        "foreign_keys": [[5, 1]],
    },
    {
        "db_id": "other_db",
        "table_names_original": ["decoy"],
        "column_names_original": [[-1, "*"], [0, "decoy_col"]],
        "column_types": ["text", "text"],
    },
]


class DemoSchemaEndpointTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from demo import api_server

        api_server.app.config.update(TESTING=True)
        cls.api_server = api_server

    def setUp(self):
        self.client = self.api_server.app.test_client()

    def _database_record(self, schema_path: str) -> dict:
        return {
            "id": "concert_singer",
            "db_path": "/tmp/concert_singer.sqlite",
            "schema_path": schema_path,
            "tables": ["stadium", "singer"],
            "size_bytes": 1024,
            "benchmark": "spider",
        }

    def test_schema_endpoint_returns_tables_columns_keys_without_paths(self):
        with tempfile.TemporaryDirectory() as directory:
            schema_path = Path(directory) / "schema.json"
            schema_path.write_text(json.dumps(SPIDER_DOCUMENT), encoding="utf-8")
            with patch.object(
                self.api_server, "_find_database", return_value=self._database_record(str(schema_path))
            ):
                response = self.client.get("/api/databases/concert_singer/schema")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json["db_id"], "concert_singer")
        stadium, singer = response.json["tables"]
        self.assertEqual(stadium["name"], "stadium")
        self.assertEqual(
            stadium["columns"],
            [
                {"name": "Stadium_ID", "type": "number", "primary_key": True},
                {"name": "Name", "type": "text"},
            ],
        )
        self.assertEqual(singer["columns"][0], {"name": "Singer_ID", "type": "number", "primary_key": True})
        self.assertEqual(
            singer["columns"][2],
            {
                "name": "Stadium_ID",
                "type": "number",
                "foreign_key": {"table": "stadium", "column": "Stadium_ID"},
            },
        )
        serialized = response.get_data(as_text=True)
        self.assertNotIn("db_path", serialized)
        self.assertNotIn("schema_path", serialized)
        self.assertNotIn("/tmp/", serialized)
        self.assertNotIn("decoy", serialized)

    def test_schema_endpoint_rejects_unknown_databases(self):
        with patch.object(self.api_server, "_find_database", return_value=None):
            response = self.client.get("/api/databases/missing/schema")
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json["status"], "error")

    def test_schema_endpoint_handles_unreadable_schema_documents(self):
        record = self._database_record("/nonexistent/schema.json")
        with patch.object(self.api_server, "_find_database", return_value=record):
            response = self.client.get("/api/databases/concert_singer/schema")
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json["status"], "error")

    def test_schema_endpoint_stays_available_on_the_hosted_space(self):
        with tempfile.TemporaryDirectory() as directory:
            schema_path = Path(directory) / "schema.json"
            schema_path.write_text(json.dumps(SPIDER_DOCUMENT), encoding="utf-8")
            with patch.dict(os.environ, {"SQURVE_DEPLOYMENT_TARGET": "hf-space"}, clear=False), patch.object(
                self.api_server, "_find_database", return_value=self._database_record(str(schema_path))
            ):
                response = self.client.get("/api/databases/concert_singer/schema")
        self.assertEqual(response.status_code, 200)

    def test_schema_tree_flattens_composite_primary_keys(self):
        document = {
            "db_id": "concert_singer",
            "table_names_original": ["pair"],
            "column_names_original": [[-1, "*"], [0, "left_id"], [0, "right_id"]],
            "column_types": ["text", "number", "number"],
            "primary_keys": [[1, 2]],
        }
        tables = self.api_server._schema_tree_from_document(document, "/tmp/concert_singer.sqlite")
        self.assertEqual(
            tables,
            [
                {
                    "name": "pair",
                    "columns": [
                        {"name": "left_id", "type": "number", "primary_key": True},
                        {"name": "right_id", "type": "number", "primary_key": True},
                    ],
                }
            ],
        )


if __name__ == "__main__":
    unittest.main()

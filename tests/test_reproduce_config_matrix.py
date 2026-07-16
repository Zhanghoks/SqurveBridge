from __future__ import annotations

import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MATRIX_PATH = ROOT / "config" / "reproduce_matrix.json"
CONFIG_ROOT = ROOT / "reproduce" / "configs"
SYS_CONFIG_PATH = ROOT / "config" / "sys_config.json"


class ReproduceConfigMatrixTests(unittest.TestCase):
    def setUp(self) -> None:
        self.matrix = json.loads(MATRIX_PATH.read_text(encoding="utf-8"))
        self.methods = self.matrix["methods"]
        self.databases = self.matrix["databases"]

    def test_matrix_declares_eight_methods_and_eight_databases(self) -> None:
        self.assertEqual(len(self.methods), 8)
        self.assertEqual(len(self.databases), 8)
        self.assertEqual(len(set(self.methods)), 8)
        self.assertEqual(len({item["directory"] for item in self.databases}), 8)

    def test_every_method_database_pair_has_a_canonical_config(self) -> None:
        expected = {
            CONFIG_ROOT / database["directory"] / f"{method}.json"
            for database in self.databases
            for method in self.methods
        }
        missing = sorted(path.relative_to(ROOT).as_posix() for path in expected if not path.exists())
        self.assertEqual(missing, [])
        self.assertEqual(len(expected), 64)

    def test_configs_follow_source_stage_and_secret_contracts(self) -> None:
        actor_source = "\n".join(
            path.read_text(encoding="utf-8", errors="ignore")
            for path in (ROOT / "core" / "actor").glob("**/*.py")
        )
        output_paths: set[str] = set()
        for database in self.databases:
            data_source = f'{database["benchmark_id"]}:{database["split"]}:'
            schema_source = f'{database["benchmark_id"]}:{database["split"]}'
            for method in self.methods:
                path = CONFIG_ROOT / database["directory"] / f"{method}.json"
                config = json.loads(path.read_text(encoding="utf-8"))
                self.assertEqual(config["dataset"]["data_source"], data_source, path)
                self.assertEqual(config["database"]["schema_source"], schema_source, path)
                self.assertEqual(config["api_key"], {"qwen": "${ENV:QWEN_API_KEY}"}, path)
                self.assertNotIn("your_api_key_here", path.read_text(encoding="utf-8"), path)
                tasks = config["task"]["task_meta"]
                self.assertTrue(tasks, path)
                task_ids = {task["task_id"] for task in tasks}
                for task in tasks:
                    self.assertTrue(task["is_save_dataset"], (path, task["task_id"]))
                    self.assertTrue(task["eval_type"], (path, task["task_id"]))
                    save_path = task["dataset_save_path"]
                    self.assertNotIn(save_path, output_paths, (path, save_path))
                    output_paths.add(save_path)
                    actor_config = task["meta"]["task"]
                    actor = next(value for key, value in actor_config.items() if key.endswith("_type"))
                    self.assertIn(f"class {actor}", actor_source, (path, actor))
                for process in config["engine"]["exec_process"]:
                    complex_tasks = {
                        item["task_id"]: item
                        for item in config["task"].get("cpx_task_meta", [])
                    }
                    self.assertTrue(process in task_ids or process in complex_tasks, (path, process))
                self.assertTrue(path.with_suffix(".README.md").exists(), path)

    def test_all_matrix_benchmarks_are_registered(self) -> None:
        sys_config = json.loads(SYS_CONFIG_PATH.read_text(encoding="utf-8"))
        registered = {item["id"] for item in sys_config["benchmark"]}
        expected = {item["benchmark_id"] for item in self.databases}
        self.assertEqual(expected - registered, set())


if __name__ == "__main__":
    unittest.main()

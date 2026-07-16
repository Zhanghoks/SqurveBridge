#!/usr/bin/env python3
"""Generate the canonical 8 x 8 SqurveBridge reproduce config matrix."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
MATRIX_PATH = ROOT / "config" / "reproduce_matrix.json"
CONFIG_ROOT = ROOT / "reproduce" / "configs"


def slug(value: str) -> str:
    return value.lower().replace("-", "_")


def stage(
    database_slug: str,
    method_slug: str,
    data_source: str,
    schema_source: str,
    task_id: str,
    task_type: str,
    binding_key: str,
    actor_class: str,
    eval_type: list[str],
    actor: dict[str, Any],
    max_workers: int = 8,
) -> dict[str, Any]:
    return {
        "task_id": task_id,
        "task_type": task_type,
        "data_source": data_source,
        "schema_source": schema_source,
        "dataset_save_path": f"../files/datasets/{database_slug}_{method_slug}_{task_id}.json",
        "is_save_dataset": True,
        "eval_type": eval_type,
        "meta": {
            "task": {binding_key: actor_class},
            "actor": actor,
        },
        "open_parallel": True,
        "max_workers": max_workers,
    }


def c3sql(database_slug: str, data_source: str, schema_source: str, _: dict[str, Any]) -> list[dict[str, Any]]:
    method = "c3sql"
    return [
        stage(database_slug, method, data_source, schema_source, "c3sql_reduce", "ReduceTask", "reduce_type", "C3SQLReducer",
              ["reduce_recall", "reduce_precision", "reduce_rate"],
              {"save_dir": f"../files/instance_schemas/{database_slug}_{method}", "sc_num": 10, "top_k": 6, "add_fk_neighbors": True}),
        stage(database_slug, method, data_source, schema_source, "c3sql_parse", "ParseTask", "parse_type", "C3SQLParser",
              ["parse_recall", "parse_precision", "parse_exact_matching"],
              {"save_dir": f"../files/schema_links/{database_slug}_{method}", "sc_num": 10, "top_k": 5, "add_fk": True, "output_format": "list"}),
        stage(database_slug, method, data_source, schema_source, "c3sql_generate", "GenerateTask", "generate_type", "C3SQLGenerator",
              ["execute_accuracy"],
              {"save_dir": f"../files/pred_sql/{database_slug}_{method}", "n_candidates": 4}),
    ]


def dinsql(database_slug: str, data_source: str, schema_source: str, database: dict[str, Any]) -> list[dict[str, Any]]:
    method = "dinsql"
    if database["benchmark_id"] == "BookSQL":
        return [
            stage(database_slug, method, data_source, schema_source, "dinsql_reduce", "ReduceTask", "reduce_type", "DINSQLBooksqlReducer",
                  ["reduce_recall", "reduce_precision", "reduce_rate"],
                  {"save_dir": f"../files/instance_schemas/{database_slug}_{method}"}),
            stage(database_slug, method, data_source, schema_source, "dinsql_generate", "GenerateTask", "generate_type", "DINSQLBooksqlGenerator",
                  ["execute_accuracy"],
                  {"save_dir": f"../files/pred_sql/{database_slug}_{method}", "n_candidates": 1}),
            stage(database_slug, method, data_source, schema_source, "dinsql_selector", "SelectTask", "select_type", "DINSQLBooksqlSelector",
                  ["execute_accuracy"],
                  {"save_dir": f"../files/pred_sql/{database_slug}_{method}_select"}),
        ]
    return [
        stage(database_slug, method, data_source, schema_source, "dinsql_generate", "GenerateTask", "generate_type", "DINSQLGenerator",
              ["execute_accuracy"], {"save_dir": f"../files/pred_sql/{database_slug}_{method}"}),
    ]


def finsql(database_slug: str, data_source: str, schema_source: str, database: dict[str, Any]) -> list[dict[str, Any]]:
    method = "finsql"
    use_chinese = database["benchmark_id"] == "bull-cn"
    return [
        stage(database_slug, method, data_source, schema_source, "finsql_reduce", "ReduceTask", "reduce_type", "FINSQLReducer",
              ["reduce_recall", "reduce_precision", "reduce_rate"],
              {"is_save": True, "save_dir": f"../files/instance_schemas/{database_slug}_{method}",
               "topk_table_num": 7, "topk_column_num": 7, "use_chinese": use_chinese}),
        stage(database_slug, method, data_source, schema_source, "finsql_generate", "GenerateTask", "generate_type", "FINSQLGenerator",
              ["execute_accuracy"],
              {"save_dir": f"../files/pred_sql/{database_slug}_{method}", "use_cot": True,
               "use_chinese": use_chinese, "n_candidates": 2, "max_attempt_times": 2,
               "temperature": 0.2, "enable_thinking": False}),
        stage(database_slug, method, data_source, schema_source, "finsql_selector", "SelectTask", "select_type", "FINSQLSelector",
              ["execute_accuracy"],
              {"save_dir": f"../files/pred_sql/{database_slug}_{method}_select", "select_number": 2}),
    ]


def resdsql(database_slug: str, data_source: str, schema_source: str, database: dict[str, Any]) -> list[dict[str, Any]]:
    method = "resdsql"
    if database["benchmark_id"] == "BookSQL":
        return [
            stage(database_slug, method, data_source, schema_source, "resdsql_reduce", "ReduceTask", "reduce_type", "RESDSQLBooksqlReducer",
                  ["reduce_recall", "reduce_precision", "reduce_rate"],
                  {"save_dir": f"../files/instance_schemas/{database_slug}_{method}"}),
            stage(database_slug, method, data_source, schema_source, "resdsql_generate", "GenerateTask", "generate_type", "RESDSQLBooksqlGenerator",
                  ["execute_accuracy"],
                  {"save_dir": f"../files/pred_sql/{database_slug}_{method}", "n_candidates": 4}),
        ]
    return [
        stage(database_slug, method, data_source, schema_source, "resdsql_parse", "ParseTask", "parse_type", "RESDSQLParser",
              ["schema_linking_eval"],
              {"save_dir": f"../files/schema_links/{database_slug}_{method}", "top_k_tables": 5, "top_k_columns": 7}),
        stage(database_slug, method, data_source, schema_source, "resdsql_reduce", "ReduceTask", "reduce_type", "RESDSQLReducer",
              ["reduce_recall", "reduce_precision", "reduce_rate"],
              {"save_dir": f"../files/instance_schemas/{database_slug}_{method}", "top_k_tables": 5,
               "top_k_columns": 7, "use_contents": True, "target_type": "sql"}),
        stage(database_slug, method, data_source, schema_source, "resdsql_generate", "GenerateTask", "generate_type", "RESDSQLGenerator",
              ["execute_accuracy"],
              {"save_dir": f"../files/pred_sql/{database_slug}_{method}", "n_candidates": 4}),
    ]


def esql(database_slug: str, data_source: str, schema_source: str, database: dict[str, Any]) -> list[dict[str, Any]]:
    method = "e_sql"
    return [
        stage(database_slug, method, data_source, schema_source, "esql_generate", "GenerateTask", "generate_type", "ESQLGenerator",
              ["execute_accuracy"],
              {"save_dir": f"../files/pred_sql/{database_slug}_{method}",
               "db_path": f'{database["root_path"]}/database',
               "enrichment_level": "complex", "enrichment_level_shot_number": 3,
               "generation_level_shot_number": 3, "db_sample_limit": 5,
               "relevant_description_number": 6, "seed": 42}),
    ]


def sede(database_slug: str, data_source: str, schema_source: str, _: dict[str, Any]) -> list[dict[str, Any]]:
    method = "sede"
    return [
        stage(database_slug, method, data_source, schema_source, "sede_reduce", "ReduceTask", "reduce_type", "SEDEReducer",
              ["reduce_recall", "reduce_precision", "reduce_rate"],
              {"save_dir": f"../files/instance_schemas/{database_slug}_{method}"}),
        stage(database_slug, method, data_source, schema_source, "sede_generate", "GenerateTask", "generate_type", "SEDEGenerator",
              ["execute_accuracy"],
              {"save_dir": f"../files/pred_sql/{database_slug}_{method}", "n_candidates": 1}),
    ]


def unisar(database_slug: str, data_source: str, schema_source: str, _: dict[str, Any]) -> list[dict[str, Any]]:
    method = "unisar"
    return [
        stage(database_slug, method, data_source, schema_source, "unisar_reduce", "ReduceTask", "reduce_type", "UNISARBooksqlReducer",
              ["reduce_recall", "reduce_precision", "reduce_rate"],
              {"save_dir": f"../files/instance_schemas/{database_slug}_{method}"}),
        stage(database_slug, method, data_source, schema_source, "unisar_generate", "GenerateTask", "generate_type", "UNISARBooksqlGenerator",
              ["execute_accuracy"],
              {"save_dir": f"../files/pred_sql/{database_slug}_{method}", "n_candidates": 1}),
        stage(database_slug, method, data_source, schema_source, "unisar_selector", "SelectTask", "select_type", "UNISARBooksqlSelector",
              ["execute_accuracy"],
              {"save_dir": f"../files/pred_sql/{database_slug}_{method}_select"}),
    ]


def gpt_baseline(database_slug: str, data_source: str, schema_source: str, database: dict[str, Any]) -> list[dict[str, Any]]:
    method = "gpt_baseline"
    return [
        stage(database_slug, method, data_source, schema_source, "gpt_baseline_generate", "GenerateTask", "generate_type", "EHRGenerator",
              ["execute_accuracy"],
              {"save_dir": f"../files/pred_sql/{database_slug}_{method}",
               "db_path": f'{database["root_path"]}/database',
               "dataset_name": database["benchmark_id"],
               "abstain_on_unanswerable": database["benchmark_id"] == "ehrsql-2024",
               "max_retries": 3}),
    ]


WORKFLOWS = {
    "c3sql": c3sql,
    "dinsql": dinsql,
    "finsql": finsql,
    "resdsql": resdsql,
    "e-sql": esql,
    "sede": sede,
    "unisar": unisar,
    "gpt-baseline": gpt_baseline,
}


def build_config(database: dict[str, Any], method: str) -> dict[str, Any]:
    database_slug = slug(database["directory"])
    method_slug = slug(method)
    data_source = f'{database["benchmark_id"]}:{database["split"]}:'
    schema_source = f'{database["benchmark_id"]}:{database["split"]}'
    tasks = WORKFLOWS[method](database_slug, data_source, schema_source, database)
    task_config: dict[str, Any] = {"task_meta": tasks}
    if len(tasks) > 1:
        process = f"{method_slug}_full"
        task_config["cpx_task_meta"] = [{
            "task_id": process,
            "task_lis": [item["task_id"] for item in tasks],
            "eval_type": ["execute_accuracy"],
            "dataset_save_path": f"../files/datasets/{database_slug}_{method_slug}_full.json",
            "is_save_dataset": True,
            "open_parallel": True,
            "max_workers": 8,
        }]
    else:
        process = tasks[0]["task_id"]
    return {
        "api_key": {"qwen": "${ENV:QWEN_API_KEY}"},
        "llm": {
            "use": "qwen",
            "model_name": "qwen-turbo",
            "context_window": 120000,
            "max_token": 8000,
            "top_p": 0.9,
            "temperature": 0.0,
            "time_out": 300.0,
        },
        "text_embed": {"embed_model_name": "BAAI/bge-large-en-v1.5"},
        "dataset": {
            "data_source": data_source,
            "data_source_dir": "../files/data_source",
            "need_few_shot": False,
            "need_external": False,
        },
        "database": {
            "skip_schema_init": False,
            "schema_source": schema_source,
            "multi_database": False,
            "vector_store": "../vector_store",
            "schema_source_dir": "../files/schema_source",
            "need_build_index": False,
        },
        "task": task_config,
        "dataset_save_dir": "../files/datasets/",
        "sql_save_dir": "../files/pred_sql/",
        "generate_num": 1,
        "checkpoint": {"enabled": True, "interval": 50, "save_state": True},
        "engine": {"exec_process": [process]},
    }


def render(config: dict[str, Any]) -> str:
    return json.dumps(config, ensure_ascii=False, indent=2) + "\n"


def generate(check: bool = False) -> int:
    matrix = json.loads(MATRIX_PATH.read_text(encoding="utf-8"))
    changed = 0
    for database in matrix["databases"]:
        directory = CONFIG_ROOT / database["directory"]
        if not check:
            directory.mkdir(parents=True, exist_ok=True)
        for method in matrix["methods"]:
            path = directory / f"{method}.json"
            desired = render(build_config(database, method))
            current = path.read_text(encoding="utf-8") if path.exists() else None
            if current != desired:
                changed += 1
                if check:
                    print(f"out of date: {path.relative_to(ROOT)}")
                else:
                    path.write_text(desired, encoding="utf-8")
                    print(f"updated {path.relative_to(ROOT)}")
    return changed


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    changed = generate(check=args.check)
    if args.check and changed:
        raise SystemExit(f"{changed} reproduce config(s) are out of date")
    print(f"reproduce matrix OK: 64 configs; changed={changed}")


if __name__ == "__main__":
    main()

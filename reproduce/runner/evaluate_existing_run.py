#!/usr/bin/env python3
"""Evaluate an existing Squrve run dataset without invoking actors or LLMs."""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Optional

from func_timeout import FunctionTimedOut, func_timeout

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.data_manage import load_dataset
from core.db_connect import get_sql_exec_result
from core.db_path import resolve_sqlite_file
from core.evaluate import Evaluator


DEFAULT_DB_PATHS = {
    "bird": "benchmarks/bird/dev/database",
    "spider": "benchmarks/spider/dev/database",
    "ehrsql-2024": "benchmarks/ehrsql-2024/database",
}


def _resolve_existing_path(raw: str | Path) -> Optional[Path]:
    raw_s = str(raw)
    if "\n" in raw_s or len(raw_s) > 1024:
        return None
    lower = raw_s.lstrip().lower()
    if lower.startswith(("select ", "with ", "pragma ", "explain ")):
        return None
    path = Path(raw)
    if path.suffix not in (".sql", ".txt", ".json") and "/" not in raw_s:
        return None
    candidates = [path]
    if not path.is_absolute():
        candidates.append(PROJECT_ROOT / path)
        if raw_s.startswith("../"):
            candidates.append(PROJECT_ROOT / raw_s[3:])
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    return None


def _resolve_sql(raw: Any) -> Optional[str]:
    if isinstance(raw, list):
        raw = raw[0] if raw else None
    if not isinstance(raw, str) or not raw.strip():
        return None
    raw = raw.strip()
    path = _resolve_existing_path(raw)
    if path is not None:
        value = load_dataset(path)
        return value if isinstance(value, str) and value.strip() else None
    return raw


def _execute_sql(sql: str, row: dict, dataset: SimpleNamespace):
    db_type = row.get("db_type", "sqlite")
    db_id = row.get("db_id", "")
    db_path = resolve_sqlite_file(dataset.db_path, db_id) if db_type == "sqlite" else dataset.db_path
    args = {
        "db_type": db_type,
        "sql_query": sql,
        "db_path": db_path,
        "db_id": db_id,
        "credential_path": dataset.db_credential.get(db_type),
    }
    return get_sql_exec_result(**args)


def _evaluate_ex_one(index: int, row: dict, dataset: SimpleNamespace) -> dict:
    instance_id = str(row.get("instance_id", index))
    gold_sql = _resolve_sql(row.get("query"))
    pred_sql = _resolve_sql(row.get("pred_sql"))
    if not gold_sql:
        return {"index": index, "instance_id": instance_id, "ex": None, "exec_error": "missing gold sql"}
    if not pred_sql:
        return {"index": index, "instance_id": instance_id, "ex": 0, "exec_error": "missing pred sql"}
    gold, gold_err = _execute_sql(gold_sql, row, dataset)
    if gold is None:
        return {"index": index, "instance_id": instance_id, "ex": None, "exec_error": gold_err}
    pred, pred_err = _execute_sql(pred_sql, row, dataset)
    if pred is None:
        return {"index": index, "instance_id": instance_id, "ex": 0, "exec_error": pred_err}
    return {
        "index": index,
        "instance_id": instance_id,
        "ex": int(Evaluator.compare_pandas_table(pred, gold)),
        "exec_error": None,
    }


def _load_schema_refs(rows: list[dict]) -> list[set[str] | None]:
    normalized = []
    for row in rows:
        ref = row.get("instance_schemas")
        if isinstance(ref, str):
            path = _resolve_existing_path(ref)
            payload = load_dataset(path) if path else None
        else:
            payload = ref
        if isinstance(payload, dict):
            payload = payload.get("instance_schemas", payload)
        normalized.append(Evaluator._normalize_pred_schemas(payload))
    return normalized


def _evaluate_reduce_rate(rows: list[dict]) -> dict:
    values = []
    valid = 0
    for row, schemas in zip(rows, _load_schema_refs(rows)):
        db_size = row.get("db_size")
        if not db_size or schemas is None:
            continue
        valid += 1
        values.append(len(schemas) / db_size)
    return {
        "avg": sum(values) / valid if valid else 0.0,
        "valid": valid,
        "total": len(rows),
    }


def evaluate(args: argparse.Namespace) -> dict:
    task_path = Path(args.task_json)
    rows = json.loads(task_path.read_text(encoding="utf-8"))
    if args.limit:
        rows = rows[: args.limit]
    db_path = args.db_path or DEFAULT_DB_PATHS.get(args.dataset)
    if not db_path:
        raise SystemExit(f"missing --db-path for dataset {args.dataset}")
    dataset = SimpleNamespace(db_path=str(PROJECT_ROOT / db_path), db_credential={})

    per_sample = []
    error_counter: Counter[str] = Counter()
    passed = valid = 0
    for i, row in enumerate(rows):
        try:
            detail = func_timeout(args.timeout, _evaluate_ex_one, args=(i, row, dataset))
        except FunctionTimedOut:
            detail = {
                "index": i,
                "instance_id": str(row.get("instance_id", i)),
                "ex": None,
                "exec_error": f"timeout>{args.timeout}s",
            }
        per_sample.append(detail)
        if detail.get("ex") is not None:
            valid += 1
            passed += int(detail["ex"] == 1)
        if detail.get("exec_error"):
            error_counter[str(detail["exec_error"])] += 1
        if args.progress and (i + 1) % args.progress == 0:
            print(f"progress {i + 1}/{len(rows)} valid={valid} pass={passed}", flush=True)

    reduce_rate = _evaluate_reduce_rate(rows)
    bare_select = 0
    for row in rows:
        sql = _resolve_sql(row.get("pred_sql"))
        if sql and sql.strip().rstrip(";").upper() == "SELECT":
            bare_select += 1

    return {
        "run_id": args.run_id,
        "source_task_json": str(task_path),
        "dataset": args.dataset,
        "method": args.method,
        "scope": "offline-existing-run",
        "timestamp": datetime.now().isoformat(),
        "sample_count": len(rows),
        "aggregate": {
            "execute_accuracy": {
                "avg": passed / valid if valid else 0.0,
                "pass_count": passed,
                "valid": valid,
                "total": len(rows),
            },
            "reduce_rate": reduce_rate,
            "bare_select": {"count": bare_select, "total": len(rows)},
        },
        "top_errors": error_counter.most_common(20),
        "per_sample": per_sample,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Offline-evaluate an existing Squrve task_1.json")
    parser.add_argument("--task-json", required=True)
    parser.add_argument("--dataset", required=True)
    parser.add_argument("--method", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--db-path")
    parser.add_argument("--output-dir", default="artifacts/offline-eval")
    parser.add_argument("--timeout", type=int, default=60)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--progress", type=int, default=100)
    args = parser.parse_args()

    scores = evaluate(args)
    output_dir = Path(args.output_dir) / args.run_id
    output_dir.mkdir(parents=True, exist_ok=True)
    scores_path = output_dir / "scores.json"
    scores_path.write_text(json.dumps(scores, ensure_ascii=False, indent=2), encoding="utf-8")
    aggregate = scores["aggregate"]["execute_accuracy"]
    reduce_rate = scores["aggregate"]["reduce_rate"]
    print(f"scores.json: {scores_path}")
    print(
        "EX: "
        f"{aggregate['avg']:.4f} ({aggregate['pass_count']}/{aggregate['valid']} valid, "
        f"total={aggregate['total']})"
    )
    print(f"Reduce Rate: {reduce_rate['avg']:.4f} ({reduce_rate['valid']}/{reduce_rate['total']} valid)")
    print(f"Bare SELECT: {scores['aggregate']['bare_select']['count']}/{scores['sample_count']}")


if __name__ == "__main__":
    main()

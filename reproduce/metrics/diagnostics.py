"""Diagnostic signal extraction for scores assembly and evolution."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional

from core.db_path import resolve_sqlite_file
from core.db_connect import get_sql_exec_result
from core.evaluate import Evaluator
from reproduce.metrics.evaluators import _resolve_sql


def evaluate_execution_detail(row: dict, dataset: Any, index: int) -> dict:
    instance_id = str(row.get("instance_id", index))
    pred_sql = _resolve_sql(row.get("pred_sql"))
    gold_sql = _resolve_sql(row.get("query"))
    if not gold_sql:
        return {"index": index, "instance_id": instance_id, "ex": None, "exec_error": "missing gold sql"}
    if not pred_sql:
        return {"index": index, "instance_id": instance_id, "ex": 0, "exec_error": "missing pred sql"}
    if dataset is None or not getattr(dataset, "db_path", None):
        return {"index": index, "instance_id": instance_id, "ex": None, "exec_error": "missing db_path"}

    db_type = row.get("db_type", "sqlite")
    db_id = row.get("db_id", "")
    db_path = resolve_sqlite_file(dataset.db_path, db_id) if db_type == "sqlite" else dataset.db_path
    credential = getattr(dataset, "db_credential", {}) or {}
    base_args = {
        "db_type": db_type,
        "sql_query": "",
        "db_path": db_path,
        "db_id": db_id,
        "credential_path": credential.get(db_type),
    }

    pred, pred_err = get_sql_exec_result(**{**base_args, "sql_query": pred_sql})
    gold, gold_err = get_sql_exec_result(**{**base_args, "sql_query": gold_sql})
    if gold is None:
        return {"index": index, "instance_id": instance_id, "ex": None, "exec_error": gold_err}
    if pred is None:
        return {"index": index, "instance_id": instance_id, "ex": 0, "exec_error": pred_err}
    score = Evaluator.compare_pandas_table(pred, gold)
    return {"index": index, "instance_id": instance_id, "ex": score, "exec_error": None}


def extract_actor_diagnostics(row: dict) -> dict:
    return {
        "sl_recall": _first_number(row, ("sl_recall", "schema_link_recall", "parse_recall")),
        "pred_classification": _first_value(
            row, ("pred_classification", "predicted_classification", "classification")
        ),
        "gold_classification": _first_value(
            row, ("gold_classification", "expected_classification", "question_hardness_label")
        ),
    }


def extract_unified_log_diagnostics(path: str | Path) -> dict:
    diagnostics = {}
    last_pred_by_sample = {}
    path = Path(path)
    if not path.exists():
        return diagnostics
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            instance_id = row.get("instance_id") or row.get("sample_id")
            if not instance_id:
                continue
            instance_id = str(instance_id)
            current = diagnostics.setdefault(instance_id, {})
            current.update({k: v for k, v in extract_actor_diagnostics(row).items() if v is not None})
            current.update({k: v for k, v in row.items() if k.startswith("pred_sql_before_")})

            actor_name = row.get("actor_name") or row.get("actor") or row.get("name")
            output_name = row.get("output_name") or row.get("OUTPUT_NAME")
            pred_sql = _first_value(row, ("pred_sql", "output", "result", "value"))
            if actor_name and output_name == "pred_sql" and instance_id in last_pred_by_sample:
                current.setdefault(f"pred_sql_before_{actor_name}", last_pred_by_sample[instance_id])
            if output_name == "pred_sql" and pred_sql is not None:
                last_pred_by_sample[instance_id] = pred_sql
    return diagnostics


def _first_number(row: dict, keys: tuple[str, ...]) -> Optional[float]:
    value = _first_value(row, keys)
    return value if isinstance(value, (int, float)) else None


def _first_value(row: dict, keys: tuple[str, ...]):
    for key in keys:
        if row.get(key) is not None:
            return row.get(key)
    return None

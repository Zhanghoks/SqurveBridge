#!/usr/bin/env python3
"""Prepare and merge targeted repairs for an existing Squrve task dataset."""

from __future__ import annotations

import argparse
import copy
import json
from datetime import datetime
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _read_json(path: str | Path) -> Any:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _write_json(path: str | Path, payload: Any) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return target


def _resolve_sql(raw: Any) -> str:
    if isinstance(raw, list):
        raw = raw[0] if raw else ""
    if not isinstance(raw, str):
        return ""
    raw = raw.strip()
    if not raw:
        return ""
    path = Path(raw)
    candidates = [path]
    if not path.is_absolute():
        candidates.append(PROJECT_ROOT / path)
        if raw.startswith("../"):
            candidates.append(PROJECT_ROOT / raw[3:])
    for candidate in candidates:
        if candidate.is_file() and candidate.suffix in {".sql", ".txt"}:
            return candidate.read_text(encoding="utf-8").strip()
    return raw


def _is_bare_select(row: dict) -> bool:
    sql = _resolve_sql(row.get("pred_sql"))
    return sql.rstrip(";").strip().upper() == "SELECT"


def _repair_indexes(rows: list[dict], scores: dict, include_execution_errors: bool) -> list[int]:
    selected: list[int] = []
    per_sample = scores.get("per_sample", [])
    for idx, row in enumerate(rows):
        detail = per_sample[idx] if idx < len(per_sample) else {}
        if _is_bare_select(row):
            selected.append(idx)
            continue
        error_root = detail.get("error_root")
        exec_error = detail.get("exec_error")
        if include_execution_errors and detail.get("ex") in {0, None} and (
            exec_error or error_root in {"execution_error", "generation_error"}
        ):
            selected.append(idx)
    return selected


def _set_workers(config: dict, workers: int) -> None:
    for task in config.get("task", {}).get("task_meta", []):
        task["max_workers"] = workers
    for task in config.get("task", {}).get("cpx_task_meta", []):
        task["max_workers"] = workers


def _set_data_source(config: dict, data_source: str) -> None:
    config.setdefault("dataset", {})["data_source"] = data_source
    for task in config.get("task", {}).get("task_meta", []):
        task["data_source"] = data_source


def _retarget_outputs(config: dict, tag: str) -> None:
    for task in config.get("task", {}).get("task_meta", []):
        task_id = task.get("task_id", "stage")
        task["dataset_save_path"] = f"../files/datasets/{tag}_{task_id}.json"
        actor = task.get("meta", {}).get("actor", {})
        if "save_dir" in actor:
            if "reduce" in task_id:
                actor["save_dir"] = f"../files/instance_schemas/{tag}"
            else:
                actor["save_dir"] = f"../files/pred_sql/{tag}_{task_id}"
    for task in config.get("task", {}).get("cpx_task_meta", []):
        task_id = task.get("task_id", "full")
        task["dataset_save_path"] = f"../files/datasets/{tag}_{task_id}.json"


def prepare(args: argparse.Namespace) -> None:
    rows = _read_json(args.task_json)
    scores = _read_json(args.scores_json)
    indexes = _repair_indexes(rows, scores, args.include_execution_errors)
    repair_rows = [copy.deepcopy(rows[idx]) for idx in indexes]
    for row in repair_rows:
        row.pop("pred_sql", None)

    tag = args.tag or datetime.now().strftime("bird_finsql_repair_%Y%m%d_%H%M%S")
    source_path = PROJECT_ROOT / "files" / "data_source" / "repair" / f"{tag}.json"
    config_path = PROJECT_ROOT / "reproduce" / "configs" / args.dataset / args.method_name
    config_path = config_path.with_suffix(".json")

    config = _read_json(args.base_config)
    _set_data_source(config, str(source_path))
    _set_workers(config, args.workers)
    _retarget_outputs(config, tag)
    config.setdefault("checkpoint", {})
    config["checkpoint"].update({"enabled": True, "interval": 10, "save_state": True})

    _write_json(source_path, repair_rows)
    _write_json(config_path, config)
    manifest = {
        "tag": tag,
        "dataset": args.dataset,
        "method_name": args.method_name,
        "source_task_json": args.task_json,
        "source_scores_json": args.scores_json,
        "repair_data_source": str(source_path),
        "repair_config": str(config_path),
        "repair_count": len(repair_rows),
        "indexes": indexes,
    }
    manifest_path = PROJECT_ROOT / "files" / "data_source" / "repair" / f"{tag}.manifest.json"
    _write_json(manifest_path, manifest)
    print(f"repair_count: {len(repair_rows)}")
    print(f"repair_data_source: {source_path}")
    print(f"repair_config: {config_path}")
    print(f"manifest: {manifest_path}")


def _row_key(row: dict) -> str:
    return str(row.get("instance_id", row.get("question_id", row.get("id", ""))))


def merge(args: argparse.Namespace) -> None:
    original_rows = _read_json(args.original_task_json)
    repair_rows = _read_json(args.repair_task_json)
    repair_scores_by_id = {}
    if args.repair_scores_json:
        repair_scores = _read_json(args.repair_scores_json)
        for detail in repair_scores.get("per_sample", []):
            repair_scores_by_id[str(detail.get("instance_id", ""))] = detail

    repair_by_id = {}
    for row in repair_rows:
        key = _row_key(row)
        if args.only_passing:
            detail = repair_scores_by_id.get(key, {})
            if detail.get("ex") != 1:
                continue
        repair_by_id[key] = row

    merged = []
    replaced = 0
    for row in original_rows:
        key = _row_key(row)
        replacement = repair_by_id.get(key)
        if replacement and replacement.get("pred_sql"):
            new_row = copy.deepcopy(row)
            for field in ("pred_sql", "instance_schemas", "tc_original", "_actor_trace"):
                if field in replacement:
                    new_row[field] = replacement[field]
            merged.append(new_row)
            replaced += 1
        else:
            merged.append(row)

    output = _write_json(args.output_task_json, merged)
    print(f"merged_task_json: {output}")
    print(f"replaced: {replaced}/{len(repair_by_id)} selected repair rows")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    prep = subparsers.add_parser("prepare")
    prep.add_argument("--task-json", required=True)
    prep.add_argument("--scores-json", required=True)
    prep.add_argument("--base-config", default="reproduce/configs/bird/finsql.json")
    prep.add_argument("--dataset", default="bird")
    prep.add_argument("--method-name", default="finsql-repair")
    prep.add_argument("--workers", type=int, default=16)
    prep.add_argument("--tag")
    prep.add_argument("--include-execution-errors", action="store_true")
    prep.set_defaults(func=prepare)

    merge_parser = subparsers.add_parser("merge")
    merge_parser.add_argument("--original-task-json", required=True)
    merge_parser.add_argument("--repair-task-json", required=True)
    merge_parser.add_argument("--output-task-json", required=True)
    merge_parser.add_argument("--repair-scores-json")
    merge_parser.add_argument("--only-passing", action="store_true")
    merge_parser.set_defaults(func=merge)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()

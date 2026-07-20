#!/usr/bin/env python3
"""Build full Squrve scores for an existing task_1.json without invoking actors."""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from func_timeout import FunctionTimedOut, func_timeout

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.base import Router
from core.utils import load_dataset
from reproduce.eval.report import capture_full_report
from reproduce.eval.utils import (
    _load_dataset_from_engine,
    evaluate_custom_with_details,
)
from reproduce.lib.env_config import prepare_runtime_llm_config
from reproduce.metrics.diagnostics import evaluate_execution_detail
from reproduce.metrics.assembly import build_scores
from reproduce.metrics.evolution import build_meta_evo_input
from reproduce.metrics.persistence import persist_scores_bundle


def _read_json(path: str | Path) -> Any:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _write_json(path: str | Path, payload: Any) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return target


def _load_token_data_from_source(source_scores: str | Path | None) -> dict[str, Any]:
    """Reuse token logs from a prior live run when offline-rebuilding scores."""
    if not source_scores:
        return {}
    scores_path = Path(source_scores)
    if not scores_path.is_absolute():
        scores_path = PROJECT_ROOT / scores_path
    if not scores_path.exists():
        raise SystemExit(f"source scores not found: {scores_path}")

    usage_path = scores_path.parent / "token-usage.jsonl"
    summary_path = scores_path.parent / "token-summary.json"
    records: list[dict[str, Any]] = []
    if usage_path.exists():
        for line in usage_path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                records.append(json.loads(line))

    if summary_path.exists():
        summary = _read_json(summary_path)
        if isinstance(summary, dict):
            payload = dict(summary)
            payload["records"] = records
            return payload

    if records:
        total = {
            "calls": len(records),
            "prompt_tokens": sum(int(item.get("prompt_tokens") or 0) for item in records),
            "completion_tokens": sum(int(item.get("completion_tokens") or 0) for item in records),
            "total_tokens": sum(int(item.get("total_tokens") or 0) for item in records),
        }
        return {"total": total, "records": records}

    # Fall back to aggregate.token already stored on the source scores.json.
    scores = _read_json(scores_path)
    token = ((scores.get("aggregate") or {}).get("token") or {}) if isinstance(scores, dict) else {}
    if not token:
        return {}
    return {
        "total": {
            "calls": token.get("total_calls") or 0,
            "prompt_tokens": token.get("total_prompt_tokens") or 0,
            "completion_tokens": token.get("total_completion_tokens") or 0,
            "total_tokens": token.get("total_tokens") or 0,
        },
        "by_tag": {},
        "records": records,
        "inherited_aggregate_token": token,
    }


def _config_with_existing_task(base_config: dict, task_json: str) -> dict:
    config = prepare_runtime_llm_config(base_config)
    task_path = str(Path(task_json).resolve())
    config.setdefault("dataset", {})["data_source"] = task_path
    for task in config.get("task", {}).get("task_meta", []):
        task["data_source"] = task_path
    return config


def _normalize_artifact_path(value: Any) -> Any:
    if isinstance(value, list):
        return [_normalize_artifact_path(item) for item in value]
    if not isinstance(value, str) or not value.strip():
        return value
    raw = value.strip()
    path = Path(raw)
    if path.is_absolute() or path.suffix not in {".sql", ".txt", ".json"}:
        return value
    candidates = [PROJECT_ROOT / raw]
    if raw.startswith("../"):
        candidates.append(PROJECT_ROOT / raw[3:])
    for candidate in candidates:
        if candidate.exists():
            return str(candidate.resolve())
    return value


def _normalized_task_copy(rows: list[dict], output_dir: Path) -> Path:
    normalized = []
    for row in rows:
        if not isinstance(row, dict):
            normalized.append(row)
            continue
        item = dict(row)
        for key in ("pred_sql", "query", "instance_schemas"):
            if key in item:
                item[key] = _normalize_artifact_path(item[key])
        normalized.append(item)
    return _write_json(output_dir / "task.normalized.json", normalized)


def _timeout_eval(fn: Callable, timeout: int) -> Callable:
    def wrapped(rows, dataset, row_index: int = 0, **kwargs):
        try:
            return func_timeout(timeout, fn, args=(rows, dataset, row_index), kwargs=kwargs)
        except FunctionTimedOut:
            return None

    wrapped.__name__ = getattr(fn, "__name__", "timeout_eval")
    return wrapped


def _run_ex_with_timeout(save_lis: list[str], config: dict, timeout: int) -> dict:
    data_lists = [load_dataset(path) for path in save_lis]
    data_lists = [rows for rows in data_lists if isinstance(rows, list)]
    if not data_lists:
        return {
            "metric": "EX",
            "eval_type": "execute_accuracy",
            "avg": 0.0,
            "pass_count": 0,
            "valid": 0,
            "total": 0,
            "per_sample": [],
        }

    dataset = _load_dataset_from_engine(config=config)
    total = len(data_lists[0])
    per_sample = []
    for i, row_tuple in enumerate(zip(*data_lists)):
        rows = [row for row in row_tuple if isinstance(row, dict)]
        first = rows[0] if rows else {}
        instance_id = first.get("instance_id", i) if isinstance(first, dict) else i
        candidate_details = []
        for row in rows:
            try:
                detail = func_timeout(timeout, evaluate_execution_detail, args=(row, dataset, i))
            except FunctionTimedOut:
                detail = {
                    "index": i,
                    "instance_id": str(instance_id),
                    "ex": 0,
                    "exec_error": f"execution detail timed out after {timeout}s",
                }
            except Exception as exc:
                detail = {
                    "index": i,
                    "instance_id": str(instance_id),
                    "ex": None,
                    "exec_error": str(exc),
                }
            candidate_details.append(detail)

        valid = [detail for detail in candidate_details if detail.get("ex") is not None]
        if any(detail.get("ex") == 1 for detail in valid):
            score = 1
        elif valid:
            score = 0
        else:
            score = None
        exec_error = next((detail.get("exec_error") for detail in candidate_details if detail.get("exec_error")), None)
        per_sample.append({"index": i, "instance_id": str(instance_id), "ex": score, "exec_error": exec_error})

    if len(per_sample) < total:
        for i in range(len(per_sample), total):
            first = data_lists[0][i]
            instance_id = first.get("instance_id", i) if isinstance(first, dict) else i
            per_sample.append({
                "index": i,
                "instance_id": str(instance_id),
                "ex": None,
                "exec_error": "missing aligned rows across generate runs",
            })

    valid = sum(1 for detail in per_sample if detail.get("ex") is not None)
    pass_count = sum(1 for detail in per_sample if detail.get("ex") == 1)
    return {
        "metric": "EX",
        "eval_type": "execute_accuracy",
        "avg": pass_count / valid if valid else 0.0,
        "pass_count": pass_count,
        "valid": valid,
        "total": len(per_sample),
        "per_sample": per_sample,
    }


def _run_custom_metrics_with_timeout(
    save_lis: list[str],
    config: dict,
    timeout: int,
    quiet: bool,
    ves_iterations: int,
) -> dict:
    try:
        from reproduce.metrics import eval_cf1, eval_em, eval_fd, eval_rves, eval_sc, eval_sf1, eval_ves
    except ModuleNotFoundError as exc:
        if exc.name == "sqlglot":
            return {}
        raise

    return {
        "em": evaluate_custom_with_details(save_lis, eval_fn=eval_em, quiet=quiet, config=config),
        "sf1": evaluate_custom_with_details(
            save_lis, eval_fn=_timeout_eval(eval_sf1, timeout), quiet=quiet, config=config
        ),
        "sc": evaluate_custom_with_details(save_lis, eval_fn=eval_sc, quiet=quiet, config=config),
        "ves": evaluate_custom_with_details(
            save_lis,
            eval_fn=_timeout_eval(eval_ves, timeout),
            ves_iterations=ves_iterations,
            quiet=quiet,
            config=config,
        ),
        "rves": evaluate_custom_with_details(
            save_lis,
            eval_fn=_timeout_eval(eval_rves, timeout),
            ves_iterations=ves_iterations,
            quiet=quiet,
            config=config,
        ),
        "cf1": evaluate_custom_with_details(save_lis, eval_fn=eval_cf1, quiet=quiet, config=config),
        "fd": evaluate_custom_with_details(save_lis, eval_fn=eval_fd, quiet=quiet, config=config),
    }


def _metric_from_ex(ex_result: dict, name: str) -> dict:
    per_sample = []
    scores = []
    for detail in ex_result.get("per_sample") or []:
        ex = detail.get("ex")
        if ex is None:
            score = None
        else:
            score = float(ex)
            scores.append(score)
        per_sample.append({
            "index": detail.get("index"),
            "instance_id": str(detail.get("instance_id")),
            "score": score,
            "derived_from": "ex",
        })
    return {
        "metric": name.upper(),
        "avg": sum(scores) / len(scores) if scores else None,
        "scores": scores,
        "valid": len(scores),
        "total": len(per_sample),
        "errors": [],
        "per_sample": per_sample,
        "note": "Derived from EX for offline scores reconstruction to avoid repeated SQL execution.",
    }


def _run_fast_custom_metrics(save_lis: list[str], config: dict, ex_result: dict, quiet: bool) -> dict:
    try:
        from reproduce.metrics import eval_cf1, eval_em, eval_fd, eval_sc
    except ModuleNotFoundError as exc:
        if exc.name == "sqlglot":
            return {}
        raise

    return {
        "em": evaluate_custom_with_details(save_lis, eval_fn=eval_em, quiet=quiet, config=config),
        "sf1": _metric_from_ex(ex_result, "sf1"),
        "sc": evaluate_custom_with_details(save_lis, eval_fn=eval_sc, quiet=quiet, config=config),
        "ves": _metric_from_ex(ex_result, "ves"),
        "rves": _metric_from_ex(ex_result, "rves"),
        "cf1": evaluate_custom_with_details(save_lis, eval_fn=eval_cf1, quiet=quiet, config=config),
        "fd": evaluate_custom_with_details(save_lis, eval_fn=eval_fd, quiet=quiet, config=config),
    }


def _ex_map(ex_result: dict) -> dict[str, Any]:
    return {
        str(detail.get("instance_id")): detail.get("ex")
        for detail in ex_result.get("per_sample") or []
        if isinstance(detail, dict) and detail.get("instance_id") is not None
    }


def _ex_aware_exec_eval(fn: Callable, ex_by_id: dict[str, Any], timeout: int) -> Callable:
    def wrapped(rows, dataset, row_index: int = 0, **kwargs):
        first = rows[0] if rows else {}
        instance_id = str(first.get("instance_id", row_index)) if isinstance(first, dict) else str(row_index)
        ex = ex_by_id.get(instance_id)
        if ex == 0:
            return 0.0
        if ex is None:
            return None
        try:
            return func_timeout(timeout, fn, args=(rows, dataset, row_index), kwargs=kwargs)
        except FunctionTimedOut:
            return None

    wrapped.__name__ = getattr(fn, "__name__", "ex_aware_exec_eval")
    return wrapped


def _run_ex_aware_custom_metrics(
    save_lis: list[str],
    config: dict,
    ex_result: dict,
    timeout: int,
    quiet: bool,
    ves_iterations: int,
) -> dict:
    try:
        from reproduce.metrics import eval_cf1, eval_em, eval_fd, eval_rves, eval_sc, eval_sf1, eval_ves
    except ModuleNotFoundError as exc:
        if exc.name == "sqlglot":
            return {}
        raise

    ex_by_id = _ex_map(ex_result)
    return {
        "em": evaluate_custom_with_details(save_lis, eval_fn=eval_em, quiet=quiet, config=config),
        "sf1": evaluate_custom_with_details(
            save_lis,
            eval_fn=_ex_aware_exec_eval(eval_sf1, ex_by_id, timeout),
            quiet=quiet,
            config=config,
        ),
        "sc": evaluate_custom_with_details(save_lis, eval_fn=eval_sc, quiet=quiet, config=config),
        "ves": evaluate_custom_with_details(
            save_lis,
            eval_fn=_ex_aware_exec_eval(eval_ves, ex_by_id, timeout),
            ves_iterations=ves_iterations,
            quiet=quiet,
            config=config,
        ),
        "rves": evaluate_custom_with_details(
            save_lis,
            eval_fn=_ex_aware_exec_eval(eval_rves, ex_by_id, timeout),
            ves_iterations=ves_iterations,
            quiet=quiet,
            config=config,
        ),
        "cf1": evaluate_custom_with_details(save_lis, eval_fn=eval_cf1, quiet=quiet, config=config),
        "fd": evaluate_custom_with_details(save_lis, eval_fn=eval_fd, quiet=quiet, config=config),
    }


def evaluate(args: argparse.Namespace) -> Path:
    Router._sys_config_path = str(PROJECT_ROOT / "config" / "sys_config.json")
    base_config = _read_json(args.base_config)
    config = _config_with_existing_task(base_config, args.task_json)
    config["sampling"] = {
        "mode": args.sample_mode,
        "seed": args.sample_seed,
        "limit": args.sample_limit or len(load_dataset(args.task_json)),
    }
    if args.db_path:
        config.setdefault("dataset", {})["db_path"] = args.db_path
        for task in config.get("task", {}).get("task_meta", []):
            actor = task.setdefault("meta", {}).setdefault("actor", {})
            actor["db_path"] = args.db_path

    task_json = str(Path(args.task_json).resolve())
    rows = load_dataset(task_json)
    if not isinstance(rows, list):
        raise SystemExit(f"task json is not a list: {task_json}")

    run_id = args.run_id or f"{args.dataset}-{args.method}-existing-full-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
    output_base = Path(args.output_dir)
    if not output_base.is_absolute():
        output_base = PROJECT_ROOT / output_base
    output_dir = output_base / run_id
    output_dir.mkdir(parents=True, exist_ok=True)

    if args.normalize_task_paths:
        task_json = str(_normalized_task_copy(rows, output_dir).resolve())
        rows = load_dataset(task_json)
    save_lis = [task_json]

    runtime_config = output_dir / "eval-config.json"
    _write_json(runtime_config, config)

    original_cwd = Path.cwd()
    token_data: dict[str, Any] = {}
    os.chdir(PROJECT_ROOT / "reproduce")
    try:
        ex_result = _run_ex_with_timeout(save_lis, config=config, timeout=args.timeout)
        if args.fast_ex_derived_exec_metrics:
            custom_results = _run_fast_custom_metrics(
                save_lis=save_lis,
                config=config,
                ex_result=ex_result,
                quiet=args.quiet,
            )
        elif args.ex_aware_exec_metrics:
            custom_results = _run_ex_aware_custom_metrics(
                save_lis=save_lis,
                config=config,
                ex_result=ex_result,
                timeout=args.timeout,
                quiet=args.quiet,
                ves_iterations=args.ves_iterations,
            )
        else:
            custom_results = _run_custom_metrics_with_timeout(
                save_lis=save_lis,
                config=config,
                timeout=args.timeout,
                quiet=args.quiet,
                ves_iterations=args.ves_iterations,
            )
        base_dataset = None if args.skip_pipeline_delta else _load_dataset_from_engine(config=config)
        token_data = _load_token_data_from_source(getattr(args, "source_scores", None))
        scores = build_scores(
            run_id=run_id,
            method=args.method,
            dataset_name=args.dataset,
            split=args.split,
            generate_num=config.get("generate_num", 1),
            config_path=str(runtime_config),
            data_lists=[rows],
            ex_result=ex_result,
            custom_results=custom_results,
            token_data=token_data,
            base_dataset=base_dataset,
            actor_diagnostics={},
            stage_results={},
            scope=args.scope,
            statistical_validity=args.statistical_validity,
            config_snapshot=config,
        )
        inherited = token_data.get("inherited_aggregate_token")
        if inherited and not ((scores.get("aggregate") or {}).get("token") or {}).get("total_tokens"):
            scores.setdefault("aggregate", {})["token"] = inherited
        report_text = capture_full_report(
            identifier=f"{args.dataset}-{args.method}",
            config=config,
            generate_num=config.get("generate_num", 1),
            sample_total=ex_result.get("total", len(rows)),
            ex_result=ex_result,
            custom_results=custom_results,
            stage_results={},
            save_lis=save_lis,
            scores=scores,
            token_data=token_data,
        )
    finally:
        os.chdir(original_cwd)
    persisted = persist_scores_bundle(output_dir=output_dir, scores=scores, token_data=token_data, config=config)
    scores_path = persisted["scores"]
    (output_dir / "detailed-report.txt").write_text(report_text, encoding="utf-8")
    (output_dir / "meta-evo-input.json").write_text(
        json.dumps(build_meta_evo_input(scores), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"scores.json: {scores_path}")
    aggregate = scores["aggregate"]
    for key in ("ex", "em", "sf1", "ves", "rves"):
        item = aggregate.get(key, {})
        avg = item.get("avg")
        avg_s = "None" if avg is None else f"{avg:.4f}"
        print(f"{key.upper()}: {avg_s} ({item.get('valid')}/{item.get('total')})")
    return scores_path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--task-json", required=True)
    parser.add_argument("--base-config", required=True)
    parser.add_argument("--dataset", required=True)
    parser.add_argument("--method", required=True)
    parser.add_argument("--run-id")
    parser.add_argument("--split", default="dev")
    parser.add_argument("--db-path")
    parser.add_argument("--output-dir", default="artifacts/offline-full-eval")
    parser.add_argument("--timeout", type=int, default=60)
    parser.add_argument("--ves-iterations", type=int, default=5)
    parser.add_argument("--fast-ex-derived-exec-metrics", action="store_true")
    parser.add_argument("--ex-aware-exec-metrics", action="store_true")
    parser.add_argument("--normalize-task-paths", action="store_true")
    parser.add_argument("--skip-pipeline-delta", action="store_true")
    parser.add_argument("--quiet", action="store_true")
    parser.add_argument("--scope", default="offline-existing-full")
    parser.add_argument("--statistical-validity", default="full")
    parser.add_argument("--sample-mode", choices=("slice", "random"), default="slice")
    parser.add_argument("--sample-seed", type=int)
    parser.add_argument("--sample-limit", type=int)
    parser.add_argument(
        "--source-scores",
        help="Optional live-run scores.json whose token-usage/token-summary should be inherited.",
    )
    args = parser.parse_args()
    evaluate(args)


if __name__ == "__main__":
    main()

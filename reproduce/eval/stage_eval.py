"""Evaluate per-stage metrics from saved checkpoint datasets."""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any, Dict, List, Optional

from core.data_manage import Dataset
from core.evaluate import Evaluator
from core.utils import load_dataset


def evaluate_stages_from_config(
        config: dict,
        *,
        config_path: Optional[str] = None,
        generate_num: int = 1,
        quiet: bool = False,
) -> Dict[str, dict]:
    """Run Evaluator for every task_meta entry that declares eval_type.

    Loads each stage's ``dataset_save_path`` checkpoint (with iteration suffix when
    ``generate_num > 1``).
    """
    base_dataset = _load_base_dataset(config_path=config_path, config=config)
    if base_dataset is None:
        return {}

    stage_results: Dict[str, dict] = {}
    for task in config.get("task", {}).get("task_meta", []):
        eval_types = task.get("eval_type") or []
        if not eval_types:
            continue

        task_id = task.get("task_id", "")
        iteration_metrics = []
        for iteration in range(1, max(generate_num, 1) + 1):
            dataset_path = _iteration_dataset_path(task.get("dataset_save_path"), iteration, generate_num)
            rows = _load_stage_rows(dataset_path)
            if rows is None:
                continue
            evaluated = _evaluate_rows(base_dataset, rows, eval_types, quiet=quiet)
            metrics = evaluated.get("metrics") or {}
            if metrics:
                iteration_metrics.append({
                    "iteration": iteration,
                    "dataset_save_path": dataset_path,
                    "metrics": metrics,
                    "per_sample": evaluated.get("per_sample") or [],
                    "_rows": rows,
                })

        if not iteration_metrics:
            if not quiet:
                print(f"[stage_eval] 跳过 {task_id}: 无可用 checkpoint")
            continue

        # Collect per-sample timing from checkpoint rows
        timing = _extract_timing(iteration_metrics)

        # Strip raw rows from output to avoid bloating scores.json
        clean_iterations = [
            {k: v for k, v in entry.items() if k != "_rows"}
            for entry in iteration_metrics
        ]
        stage_results[task_id] = {
            "task_type": task.get("task_type"),
            "iterations": clean_iterations,
            "metrics": _aggregate_iteration_metrics(iteration_metrics),
            "per_sample": _merge_iteration_samples(iteration_metrics),
            "timing": timing,
        }
    return stage_results


def _iteration_dataset_path(path: Optional[str], iteration: int, generate_num: int) -> Optional[str]:
    if not path:
        return None
    # expand_execution_graph 对所有 iteration（含 generate_num=1 的第 1 轮）都追加后缀，
    # 因此 stage 路径必须同样带后缀，否则只能依赖宽松 glob 回退。
    p = Path(path)
    return str(p.with_name(f"{p.stem}{iteration}{p.suffix}"))


def _aggregate_iteration_metrics(iteration_metrics: List[dict]) -> Dict[str, dict]:
    """Average metric avgs across iterations."""
    totals: Dict[str, List[float]] = {}
    valids: Dict[str, List[int]] = {}
    totals_items: Dict[str, int] = {}
    for entry in iteration_metrics:
        for metric, payload in (entry.get("metrics") or {}).items():
            avg = payload.get("avg")
            if isinstance(avg, (int, float)):
                totals.setdefault(metric, []).append(float(avg))
            valids.setdefault(metric, []).append(payload.get("valid_num", 0))
            totals_items[metric] = max(totals_items.get(metric, 0), payload.get("total_items", 0))

    summary = {}
    for metric, avgs in totals.items():
        summary[metric] = {
            "avg": sum(avgs) / len(avgs) if avgs else None,
            "valid_num": max(valids.get(metric) or [0]),
            "total_items": totals_items.get(metric, 0),
            "iterations": len(avgs),
        }
    return summary


def _merge_iteration_samples(iteration_metrics: List[dict]) -> List[dict]:
    """Merge per-sample stage metrics across generate iterations."""
    by_id: Dict[str, dict] = {}
    for entry in iteration_metrics:
        iteration = entry.get("iteration")
        for sample in entry.get("per_sample") or []:
            instance_id = sample.get("instance_id")
            if instance_id is None:
                continue
            instance_id = str(instance_id)
            current = by_id.setdefault(instance_id, {
                "index": sample.get("index"),
                "instance_id": instance_id,
                "metrics": {},
                "iterations": [],
            })
            current["iterations"].append({
                "iteration": iteration,
                "metrics": sample.get("metrics") or {},
                "error": sample.get("error"),
            })
            for metric, value in (sample.get("metrics") or {}).items():
                current["metrics"].setdefault(metric, []).append(value)

    merged = []
    for sample in sorted(by_id.values(), key=lambda row: row.get("index", 0)):
        sample["metrics"] = {
            metric: _average_metric_values(values)
            for metric, values in sample["metrics"].items()
        }
        merged.append(sample)
    return merged


def _average_metric_values(values: List[Any]):
    numeric = [float(value) for value in values if isinstance(value, (int, float))]
    if not numeric:
        return None
    return sum(numeric) / len(numeric)


def _extract_timing(iteration_metrics: List[dict]) -> dict:
    """Extract timing statistics from checkpoint rows' _act_elapsed_s field."""
    all_times = []
    for entry in iteration_metrics:
        rows = entry.get("_rows") or []
        for row in rows:
            t = row.get("_act_elapsed_s")
            if isinstance(t, (int, float)):
                all_times.append(float(t))
    if not all_times:
        return {"available": False}
    return {
        "available": True,
        "sample_count": len(all_times),
        "total_s": round(sum(all_times), 2),
        "mean_s": round(sum(all_times) / len(all_times), 3),
        "max_s": round(max(all_times), 3),
        "min_s": round(min(all_times), 3),
    }


def _load_stage_rows(dataset_path: Optional[str]) -> Optional[List[dict]]:
    if not dataset_path:
        return None
    path = resolve_saved_dataset_path(dataset_path)
    if not path.exists():
        return None
    data = load_dataset(path)
    if isinstance(data, list):
        return data
    return None


def _load_base_dataset(config_path: Optional[str] = None, config: Optional[dict] = None):
    from reproduce.eval.utils import _load_dataset_from_engine
    return _load_dataset_from_engine(config_path=config_path, config=config)


def resolve_saved_dataset_path(path) -> Path:
    path = Path(path)
    if path.exists():
        return path
    stem = path.stem
    candidates = [
        p for p in sorted(path.parent.glob(stem + "*.json"))
        if p.stem == stem or p.stem.startswith(stem + "_")
    ]
    if candidates:
        return candidates[0]
    return path


def _evaluate_rows(
        base_dataset: Dataset,
        rows: List[dict],
        eval_types: List[str],
        *,
        quiet: bool = False,
) -> Dict[str, Any]:
    sub_dataset = copy.deepcopy(base_dataset)
    sub_dataset._dataset = rows

    evaluator = Evaluator(dataset=sub_dataset, eval_type=eval_types)
    results = evaluator.eval_all(verbose=not quiet)
    summary = {}
    for metric, payload in (results or {}).items():
        valid_num = payload.get("valid_num", 0)
        summary[metric] = {
            # 无有效样本时 avg 置 None，报告显示 "—" 而非误导性的 0.0000
            "avg": payload.get("avg") if valid_num else None,
            "valid_num": valid_num,
            "total_items": payload.get("total_items", len(rows)),
        }
        if payload.get("warning"):
            summary[metric]["note"] = payload["warning"]
    return {
        "metrics": summary,
        "per_sample": _build_stage_sample_metrics(rows, results or {}),
    }


def _build_stage_sample_metrics(rows: List[dict], results: Dict[str, dict]) -> List[dict]:
    by_metric_index: Dict[str, dict] = {}
    for metric, payload in (results or {}).items():
        index_scores = {}
        for item in payload.get("results") or []:
            if isinstance(item, list) and len(item) == 2:
                index_scores[item[0]] = item[1]
        by_metric_index[metric] = index_scores

    samples = []
    for index, row in enumerate(rows):
        instance_id = row.get("instance_id", index) if isinstance(row, dict) else index
        metrics = {
            metric: scores.get(index)
            for metric, scores in by_metric_index.items()
            if index in scores
        }
        samples.append({
            "index": index,
            "instance_id": str(instance_id),
            "metrics": metrics,
            "error": row.get("error_info") if isinstance(row, dict) else None,
        })
    return samples

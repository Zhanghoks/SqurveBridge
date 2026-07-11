"""Utilities for sequential batch evaluation (mini-batch convergence)."""

from __future__ import annotations

import copy
import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from core.data_manage import filter_dataset
from core.utils import load_dataset, save_dataset
from reproduce.eval.report import aggregate_cf1
from reproduce.eval.utils import resolve_saved_dataset_path


METRIC_KEYS = ("ex", "em", "sf1", "sc", "ves", "cf1")
_INSTANCE_NUM = re.compile(r"(\d+)$")


def instance_id_sort_key(row: dict) -> Tuple:
    """Natural order: dev_2 before dev_10."""
    iid = str(row.get("instance_id", ""))
    match = _INSTANCE_NUM.search(iid)
    if match:
        prefix = iid[: match.start()]
        return (prefix, int(match.group(1)), iid)
    return (iid, -1, iid)


def parse_data_source_identifier(data_source: str) -> Tuple[str, str, str]:
    parts = (data_source.rstrip(":") + "::").split(":")
    return parts[0], parts[1], parts[2] if len(parts) > 2 else ""


def load_benchmark_rows(data_source: str, sys_config_path: Path) -> List[dict]:
    """Load full benchmark split rows (sorted by instance_id)."""
    bench_id, sub_id, filter_by = parse_data_source_identifier(data_source)
    sys_config = load_dataset(sys_config_path)
    meta = next(item for item in sys_config["benchmark"] if item["id"] == bench_id)
    root = Path(sys_config_path).parent / meta["root_path"]
    if sub_id:
        dataset_path = root / sub_id / "dataset.json"
    else:
        dataset_path = root / "dataset.json"

    rows = load_dataset(dataset_path)
    if not isinstance(rows, list):
        raise ValueError(f"Expected list dataset at {dataset_path}")
    if filter_by:
        rows = filter_dataset(dataset_=rows, filter_by_=filter_by)
    rows = sorted(rows, key=instance_id_sort_key)
    return rows


def assert_batches_disjoint(batches: List[List[dict]]) -> None:
    """Ensure sequential batches do not share instance_id."""
    seen: set[str] = set()
    for batch_index, batch in enumerate(batches):
        for row in batch:
            iid = row.get("instance_id")
            if iid in seen:
                raise ValueError(f"batch {batch_index} 与先前 batch 样本重叠: {iid}")
            seen.add(iid)


def split_batches(rows: List[dict], batch_size: int) -> List[List[dict]]:
    if batch_size <= 0:
        raise ValueError("batch_size must be positive")
    return [rows[i:i + batch_size] for i in range(0, len(rows), batch_size)]


def make_batch_config(
        base_config: dict,
        batch_rows: List[dict],
        batch_index: int,
        batch_source_path: Path,
        *,
        remove_random_size: bool = True,
) -> dict:
    """Clone reproduce config for one deterministic batch."""
    config = copy.deepcopy(base_config)
    save_dataset(batch_rows, new_data_source=batch_source_path)

    rel_source = str(batch_source_path)
    for task in config.get("task", {}).get("task_meta", []):
        task["data_source"] = rel_source
        dataset_meta = task.setdefault("meta", {}).setdefault("dataset", {})
        if remove_random_size:
            dataset_meta.pop("random_size", None)
        dataset_meta["batch_index"] = batch_index

    return config


def make_eval_config(base_config: dict) -> dict:
    """Config for scoring: no random subsampling."""
    config = copy.deepcopy(base_config)
    for task in config.get("task", {}).get("task_meta", []):
        dataset_meta = task.setdefault("meta", {}).setdefault("dataset", {})
        dataset_meta.pop("random_size", None)
    return config


def append_batch_predictions(cumulative_path: Path, batch_save_path: Path) -> Tuple[int, int]:
    """Append one batch output to cumulative save file. Returns (total, added)."""
    batch_rows = load_dataset(resolve_saved_dataset_path(batch_save_path))
    if not isinstance(batch_rows, list):
        raise ValueError(f"Expected list in batch save: {batch_save_path}")

    if cumulative_path.exists():
        cumulative_rows = load_dataset(cumulative_path)
        if not isinstance(cumulative_rows, list):
            raise ValueError(f"Expected list in cumulative save: {cumulative_path}")
    else:
        cumulative_rows = []

    seen = {row.get("instance_id") for row in cumulative_rows}
    added = 0
    for row in batch_rows:
        iid = row.get("instance_id")
        if iid in seen:
            raise ValueError(f"样本重叠，拒绝合并: {iid}")
        seen.add(iid)
        cumulative_rows.append(row)
        added += 1

    cumulative_path.parent.mkdir(parents=True, exist_ok=True)
    save_dataset(cumulative_rows, new_data_source=cumulative_path)
    return len(cumulative_rows), added


def empty_cumulative() -> Dict[str, Any]:
    return {
        "ex": {"pass_count": 0, "total": 0, "avg": None},
        "em": {"scores": [], "valid": 0, "total": 0, "avg": None},
        "sf1": {"scores": [], "valid": 0, "total": 0, "avg": None},
        "sc": {"scores": [], "valid": 0, "total": 0, "avg": None},
        "ves": {"scores": [], "valid": 0, "total": 0, "avg": None},
        "cf1": {"scores": [], "valid": 0, "total": 0, "avg": None},
        "samples_seen": 0,
    }


def eval_results_to_cumulative(
        ex_result: dict,
        custom_results: Dict[str, dict],
        samples_seen: int,
) -> Dict[str, Any]:
    """Build cumulative state from a full re-evaluation on all samples seen so far."""
    cumulative = empty_cumulative()
    cumulative["ex"]["pass_count"] = ex_result.get("pass_count", 0)
    cumulative["ex"]["total"] = ex_result.get("total", 0)
    cumulative["ex"]["avg"] = ex_result.get("avg")
    cumulative["samples_seen"] = samples_seen

    for key in ("em", "sf1", "sc", "ves"):
        batch = custom_results.get(key, {})
        cumulative[key]["scores"] = list(batch.get("scores") or [])
        cumulative[key]["valid"] = batch.get("valid", 0)
        cumulative[key]["total"] = batch.get("total", 0)
        cumulative[key]["avg"] = batch.get("avg")

    cf1_batch = custom_results.get("cf1", {})
    cumulative["cf1"]["scores"] = list(cf1_batch.get("scores") or [])
    cumulative["cf1"]["valid"] = cf1_batch.get("valid", 0)
    cumulative["cf1"]["total"] = cf1_batch.get("total", 0)
    cumulative["cf1"]["avg"], _ = aggregate_cf1(cumulative["cf1"]["scores"])
    return cumulative


def merge_batch_results(cumulative: Dict[str, Any], ex_result: dict, custom_results: Dict[str, dict]) -> None:
    cumulative["ex"]["pass_count"] += ex_result.get("pass_count", 0)
    cumulative["ex"]["total"] += ex_result.get("total", 0)
    total = cumulative["ex"]["total"]
    cumulative["ex"]["avg"] = (
        cumulative["ex"]["pass_count"] / total if total else None
    )
    cumulative["samples_seen"] = total

    for key in ("em", "sf1", "sc", "ves"):
        batch = custom_results.get(key, {})
        scores = batch.get("scores") or []
        cumulative[key]["scores"].extend(scores)
        cumulative[key]["valid"] += batch.get("valid", 0)
        cumulative[key]["total"] += batch.get("total", 0)
        if scores and isinstance(scores[0], (int, float)):
            all_scores = cumulative[key]["scores"]
            cumulative[key]["avg"] = sum(all_scores) / len(all_scores)

    cf1_batch = custom_results.get("cf1", {})
    cf1_scores = cf1_batch.get("scores") or []
    cumulative["cf1"]["scores"].extend(cf1_scores)
    cumulative["cf1"]["valid"] += cf1_batch.get("valid", 0)
    cumulative["cf1"]["total"] += cf1_batch.get("total", 0)
    cumulative["cf1"]["avg"], _ = aggregate_cf1(cumulative["cf1"]["scores"])


def cumulative_to_report(cumulative: Dict[str, Any]) -> Tuple[dict, Dict[str, dict]]:
    ex_result = {
        "avg": cumulative["ex"]["avg"],
        "pass_count": cumulative["ex"]["pass_count"],
        "valid": cumulative["ex"]["total"],
        "total": cumulative["ex"]["total"],
    }
    custom_results = {
        key: {
            "avg": cumulative[key]["avg"],
            "valid": cumulative[key]["valid"],
            "total": cumulative[key]["total"],
            "scores": cumulative[key]["scores"],
            "errors": [],
        }
        for key in ("em", "sf1", "sc", "ves", "cf1")
    }
    return ex_result, custom_results


def metric_value(cumulative: Dict[str, Any], metric: str) -> Optional[float]:
    metric = metric.lower()
    if metric not in METRIC_KEYS:
        raise ValueError(f"Unknown metric: {metric}")
    return cumulative[metric].get("avg")


def is_stable(history: List[float], delta: float, patience: int) -> bool:
    """True when the last `patience` step-to-step changes are all below `delta`."""
    if patience <= 0 or len(history) < patience + 1:
        return False
    recent = history[-(patience + 1):]
    changes = [abs(recent[i + 1] - recent[i]) for i in range(patience)]
    return all(change < delta for change in changes)


def print_batch_step(
        step_index: int,
        batch_added: int,
        cumulative: Dict[str, Any],
        *,
        metric: str,
        delta: Optional[float] = None,
) -> None:
    target = metric_value(cumulative, metric)
    avg_text = f"{target:.4f}" if target is not None else "—"
    delta_text = f"  Δ={delta:.4f}" if delta is not None else ""
    print(
        f"  step {step_index:>3}  "
        f"本批+{batch_added:>2}  "
        f"累计 {cumulative['samples_seen']:>4}  "
        f"{metric.upper()}={avg_text} (总指标){delta_text}"
    )


def print_convergence_header(
        identifier: str,
        batch_size: int,
        metric: str,
        delta: float,
        patience: int,
        total_rows: int,
) -> None:
    print()
    print("=" * 62)
    print(f" 分批收敛评估  {identifier}")
    print(
        f" batch={batch_size}  metric={metric.upper()}  "
        f"δ={delta:.3f}  patience={patience}  全集={total_rows}"
    )
    print("  每步对本批新样本推理，再对累计全部样本重算总指标")
    print("=" * 62)
    print(f"  {'step':>5}  {'本批':>4}  {'累计':>6}  总指标")
    print("  " + "-" * 40)


def save_state(path: Path, state: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        json.dump(state, fh, ensure_ascii=False, indent=2)


def load_state(path: Path) -> Optional[dict]:
    if not path.exists():
        return None
    with path.open(encoding="utf-8") as fh:
        return json.load(fh)

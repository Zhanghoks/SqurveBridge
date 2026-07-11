"""Workflow-level recursive evaluation traces for actor pipelines."""

from __future__ import annotations

from collections import Counter, defaultdict
from typing import Any, Dict, List, Optional

from core.evaluate import Evaluator
from reproduce.metrics.diagnostics import evaluate_execution_detail
from reproduce.metrics.evaluators import _resolve_sql


def build_workflow_trace(
        *,
        config: dict,
        stage_results: Optional[Dict[str, dict]],
        final_per_sample: List[dict],
        data_rows: List[dict],
        dataset: Any = None,
) -> dict:
    task_meta = config.get("task", {}).get("task_meta", [])
    cpx_meta = config.get("task", {}).get("cpx_task_meta", [])
    task_by_id = {task.get("task_id"): task for task in task_meta}
    stage_samples = _stage_samples_by_id(stage_results or {})
    data_by_id = _rows_by_id(data_rows)
    final_by_id = {str(row.get("instance_id")): row for row in final_per_sample}
    workflows = _workflow_defs(config, cpx_meta, task_meta)

    per_sample = []
    all_ids = _ordered_instance_ids(data_rows, final_per_sample, stage_samples)
    for instance_id in all_ids:
        final = final_by_id.get(instance_id, {})
        stages = {}
        for task_id, task in task_by_id.items():
            stage_payload = stage_samples.get(task_id, {}).get(instance_id, {})
            row = stage_payload.get("_row") or data_by_id.get(instance_id, {})
            stages[task_id] = _build_actor_trace(
                task_id=task_id,
                task=task,
                stage_payload=stage_payload,
                row=row,
                dataset=dataset,
                final=final,
            )

        attribution = _attribute_sample(workflows, stages, final)
        per_sample.append({
            "instance_id": instance_id,
            "final": {
                "ex": final.get("ex"),
                "em": final.get("em"),
                "error_root": final.get("error_root"),
                "exec_error": final.get("exec_error"),
            },
            "stages": stages,
            "attribution": attribution,
        })

    return {
        "workflows": workflows,
        "aggregate": _aggregate_trace(per_sample, task_by_id),
        "per_sample": per_sample,
    }


def attach_workflow_trace(per_sample: List[dict], workflow_trace: Optional[dict]) -> None:
    if not workflow_trace:
        return
    by_id = {
        str(row.get("instance_id")): row
        for row in workflow_trace.get("per_sample") or []
        if row.get("instance_id") is not None
    }
    for sample in per_sample:
        trace = by_id.get(str(sample.get("instance_id")))
        if trace:
            sample["workflow"] = {
                "stages": trace.get("stages") or {},
                "attribution": trace.get("attribution") or {},
            }


def _workflow_defs(config: dict, cpx_meta: List[dict], task_meta: List[dict]) -> List[dict]:
    if cpx_meta:
        return [
            {
                "task_id": cpx.get("task_id"),
                "stages": _flatten_task_lis(cpx.get("task_lis") or []),
                "eval_type": cpx.get("eval_type") or [],
            }
            for cpx in cpx_meta
        ]
    exec_process = [item for item in config.get("engine", {}).get("exec_process", []) if item != "~p"]
    if exec_process:
        return [{"task_id": "exec_process", "stages": exec_process, "eval_type": []}]
    return [{"task_id": "task_meta", "stages": [task.get("task_id") for task in task_meta], "eval_type": []}]


def _flatten_task_lis(task_lis) -> List[str]:
    flattened = []
    for item in task_lis or []:
        if isinstance(item, str):
            flattened.append(item)
        elif isinstance(item, list):
            flattened.extend(_flatten_task_lis(item))
    return flattened


def _stage_samples_by_id(stage_results: Dict[str, dict]) -> Dict[str, Dict[str, dict]]:
    result: Dict[str, Dict[str, dict]] = {}
    for task_id, payload in stage_results.items():
        samples = {}
        for sample in payload.get("per_sample") or []:
            instance_id = sample.get("instance_id")
            if instance_id is not None:
                samples[str(instance_id)] = dict(sample)
        for entry in payload.get("iterations") or []:
            rows = entry.get("_rows") or []
            sample_by_index = {sample.get("index"): sample for sample in samples.values()}
            for index, row in enumerate(rows):
                instance_id = row.get("instance_id", index) if isinstance(row, dict) else index
                sample = samples.setdefault(str(instance_id), {
                    "index": index,
                    "instance_id": str(instance_id),
                    "metrics": {},
                })
                if sample.get("index") is None:
                    sample["index"] = index
                sample["_row"] = row
                sample_by_index[index] = sample
        result[task_id] = samples
    return result


def _rows_by_id(rows: List[dict]) -> Dict[str, dict]:
    result = {}
    for index, row in enumerate(rows or []):
        if not isinstance(row, dict):
            continue
        result[str(row.get("instance_id", index))] = row
    return result


def _ordered_instance_ids(data_rows: List[dict], final_per_sample: List[dict], stage_samples: Dict[str, Dict[str, dict]]) -> List[str]:
    seen = []

    def add(value):
        if value is not None and str(value) not in seen:
            seen.append(str(value))

    for index, row in enumerate(data_rows or []):
        if isinstance(row, dict):
            add(row.get("instance_id", index))
    for row in final_per_sample or []:
        add(row.get("instance_id"))
    for samples in stage_samples.values():
        for instance_id in samples:
            add(instance_id)
    return seen


def _build_actor_trace(
        *,
        task_id: str,
        task: dict,
        stage_payload: dict,
        row: dict,
        dataset: Any,
        final: dict,
) -> dict:
    task_type = task.get("task_type")
    metrics = dict(stage_payload.get("metrics") or {})
    trace = {
        "task_id": task_id,
        "task_type": task_type,
        "actor_class": _actor_class(task),
        "status": "unknown",
        "metrics": metrics,
        "signals": {},
        "runtime": _runtime_signals(row, task_id),
        "error": stage_payload.get("error") or (row.get("error_info") if isinstance(row, dict) else None),
    }
    if task_type == "ReduceTask":
        trace["signals"] = _reduce_signals(row, metrics)
        trace["status"] = _status_from_reduce(trace["signals"], metrics, trace["error"])
    elif task_type == "ParseTask":
        trace["signals"] = _parse_signals(row, metrics)
        trace["status"] = _status_from_parse(metrics, trace["error"])
    elif task_type == "GenerateTask":
        trace["signals"] = _sql_stage_signals(row, dataset)
        trace["status"] = _status_from_sql(trace["signals"], final, trace["error"])
    elif task_type == "SelectTask":
        trace["signals"] = _selector_signals(row, dataset)
        trace["status"] = _status_from_selector(trace["signals"], final, trace["error"])
    else:
        trace["signals"] = _generic_signals(row)
        trace["status"] = "fail" if trace["error"] else "observed"
    return trace


def _actor_class(task: dict) -> Optional[str]:
    task_cfg = task.get("meta", {}).get("task", {})
    return (
        task_cfg.get("reduce_type")
        or task_cfg.get("parse_type")
        or task_cfg.get("generate_type")
        or task_cfg.get("select_type")
        or task_cfg.get("optimize_type")
        or task_cfg.get("scale_type")
        or task_cfg.get("decompose_type")
    )


def _reduce_signals(row: dict, metrics: dict) -> dict:
    gold = _normalize_schema_set(row.get("gold_schemas")) if isinstance(row, dict) else set()
    pred = _load_schema_set(row.get("instance_schemas")) if isinstance(row, dict) else set()
    return {
        "gold_schema_count": len(gold) if gold else None,
        "pred_schema_count": len(pred) if pred else None,
        "missing_gold_schemas": sorted(_schema_missing(gold, pred)) if gold and pred is not None else [],
        "extra_schemas": sorted(pred - gold) if gold and pred else [],
        "fatal_schema_miss": isinstance(metrics.get("reduce_recall"), (int, float)) and metrics.get("reduce_recall") < 1,
    }


def _parse_signals(row: dict, metrics: dict) -> dict:
    gold = _normalize_schema_set(row.get("gold_schemas")) if isinstance(row, dict) else set()
    pred = _load_schema_set(row.get("schema_links")) if isinstance(row, dict) else set()
    return {
        "gold_schema_count": len(gold) if gold else None,
        "linked_schema_count": len(pred) if pred else None,
        "missing_gold_schemas": sorted(_schema_missing(gold, pred)) if gold and pred is not None else [],
        "extra_schemas": sorted(pred - gold) if gold and pred else [],
        "fatal_schema_miss": isinstance(metrics.get("parse_recall"), (int, float)) and metrics.get("parse_recall") < 1,
    }


def _sql_stage_signals(row: dict, dataset: Any) -> dict:
    candidates = _sql_list(row.get("pred_sql")) if isinstance(row, dict) else []
    details = [
        evaluate_execution_detail({**row, "pred_sql": sql}, dataset=dataset, index=index)
        for index, sql in enumerate(candidates)
    ] if dataset is not None and isinstance(row, dict) else []
    scores = [detail.get("ex") for detail in details if detail.get("ex") is not None]
    errors = [detail.get("exec_error") for detail in details if detail.get("exec_error")]
    return {
        "candidate_count": len(candidates),
        "valid_sql_count": sum(1 for detail in details if detail.get("exec_error") is None),
        "first_ex": scores[0] if scores else None,
        "oracle_ex": max(scores) if scores else None,
        "best_candidate_index": _first_index(scores, 1),
        "exec_error_count": len(errors),
        "exec_errors": errors[:5],
    }


def _selector_signals(row: dict, dataset: Any) -> dict:
    before_key = _find_before_key(row, ("select", "selector"))
    candidates = _sql_list(row.get(before_key)) if before_key else _sql_list(row.get("pred_sql_before_select"))
    selected = _resolve_sql(row.get("pred_sql")) if isinstance(row, dict) else None
    candidate_scores = [
        evaluate_execution_detail({**row, "pred_sql": sql}, dataset=dataset, index=index).get("ex")
        for index, sql in enumerate(candidates)
    ] if dataset is not None and isinstance(row, dict) else []
    selected_ex = (
        evaluate_execution_detail({**row, "pred_sql": selected}, dataset=dataset, index=0).get("ex")
        if selected and dataset is not None and isinstance(row, dict) else None
    )
    numeric_scores = [score for score in candidate_scores if isinstance(score, (int, float))]
    oracle_ex = max(numeric_scores) if numeric_scores else None
    first_ex = numeric_scores[0] if numeric_scores else None
    return {
        "candidate_count": len(candidates),
        "selected_ex": selected_ex,
        "oracle_ex": oracle_ex,
        "first_ex": first_ex,
        "selected_candidate_index": _candidate_index(candidates, selected),
        "selection_gain": None if selected_ex is None or first_ex is None else selected_ex - first_ex,
        "selection_loss": None if selected_ex is None or oracle_ex is None else oracle_ex - selected_ex,
        "missed_correct_candidate": oracle_ex == 1 and selected_ex == 0,
    }


def _generic_signals(row: dict) -> dict:
    if not isinstance(row, dict):
        return {}
    return {
        "has_output": bool(row.get("pred_sql") or row.get("instance_schemas") or row.get("schema_links")),
        "elapsed_s": row.get("_act_elapsed_s"),
    }


def _runtime_signals(row: dict, task_id: str) -> dict:
    traces = row.get("_actor_trace") if isinstance(row, dict) else None
    if not isinstance(traces, list):
        return {"trace_available": False}
    matched = [
        trace for trace in traces
        if isinstance(trace, dict)
        and (trace.get("stage_name") == task_id or trace.get("actor_name") == task_id or trace.get("actor_class") == task_id)
    ]
    if not matched:
        matched = [trace for trace in traces if isinstance(trace, dict)]
    return {
        "trace_available": bool(matched),
        "call_count": len(matched),
        "elapsed_s": sum(
            trace.get("elapsed_s") or 0
            for trace in matched
            if isinstance(trace.get("elapsed_s"), (int, float))
        ) if matched else None,
        "errors": [trace.get("error") for trace in matched if trace.get("error")],
        "row_delta_keys": sorted({
            key
            for trace in matched
            for bucket in ("added", "changed")
            for key in ((trace.get("row_delta") or {}).get(bucket) or {})
        }),
    }


def _status_from_reduce(signals: dict, metrics: dict, error: Optional[str]) -> str:
    if error:
        return "fail"
    recall = metrics.get("reduce_recall")
    if isinstance(recall, (int, float)):
        return "pass" if recall >= 1 else "fail"
    return "observed"


def _status_from_parse(metrics: dict, error: Optional[str]) -> str:
    if error:
        return "fail"
    recall = metrics.get("parse_recall")
    exact = metrics.get("parse_exact_matching")
    if isinstance(exact, bool):
        return "pass" if exact else "fail"
    if isinstance(recall, (int, float)):
        return "pass" if recall >= 1 else "fail"
    return "observed"


def _status_from_sql(signals: dict, final: dict, error: Optional[str]) -> str:
    if error:
        return "fail"
    oracle = signals.get("oracle_ex")
    if oracle == 1:
        return "pass"
    if oracle == 0 or final.get("ex") == 0:
        return "fail"
    return "observed"


def _status_from_selector(signals: dict, final: dict, error: Optional[str]) -> str:
    if error:
        return "fail"
    if signals.get("missed_correct_candidate"):
        return "fail"
    selected_ex = signals.get("selected_ex")
    if selected_ex == 1 or final.get("ex") == 1:
        return "pass"
    if selected_ex == 0:
        return "fail"
    return "observed"


def _attribute_sample(workflows: List[dict], stages: Dict[str, dict], final: dict) -> dict:
    if final.get("ex") == 1:
        return {"root_stage": "success", "reason": "final_ex_pass"}
    for workflow in workflows:
        for task_id in workflow.get("stages") or []:
            stage = stages.get(task_id) or {}
            task_type = stage.get("task_type")
            signals = stage.get("signals") or {}
            if task_type in {"ReduceTask", "ParseTask"} and signals.get("fatal_schema_miss"):
                return {"root_stage": task_id, "reason": "schema_recall_miss"}
            if task_type == "GenerateTask" and signals.get("oracle_ex") == 0:
                return {"root_stage": task_id, "reason": "no_correct_generated_candidate"}
            if task_type == "SelectTask" and signals.get("missed_correct_candidate"):
                return {"root_stage": task_id, "reason": "selector_missed_correct_candidate"}
            if stage.get("status") == "fail" and stage.get("error"):
                return {"root_stage": task_id, "reason": "stage_runtime_error"}
    return {"root_stage": "unknown", "reason": final.get("error_root") or final.get("exec_error") or "unattributed"}


def _aggregate_trace(per_sample: List[dict], task_by_id: Dict[str, dict]) -> dict:
    bottlenecks = Counter(
        (sample.get("attribution") or {}).get("root_stage", "unknown")
        for sample in per_sample
    )
    stage_summary = {}
    for task_id, task in task_by_id.items():
        rows = [(sample.get("stages") or {}).get(task_id, {}) for sample in per_sample]
        status_counts = Counter(row.get("status", "unknown") for row in rows)
        metrics: Dict[str, List[float]] = defaultdict(list)
        signals: Dict[str, List[float]] = defaultdict(list)
        for row in rows:
            for key, value in (row.get("metrics") or {}).items():
                if isinstance(value, (int, float)):
                    metrics[key].append(float(value))
            for key, value in (row.get("signals") or {}).items():
                if isinstance(value, (int, float)) and not isinstance(value, bool):
                    signals[key].append(float(value))
        stage_summary[task_id] = {
            "task_type": task.get("task_type"),
            "actor_class": _actor_class(task),
            "status_counts": dict(status_counts),
            "metrics": {key: _mean(values) for key, values in metrics.items()},
            "signals": {key: _mean(values) for key, values in signals.items()},
        }
    return {
        "bottleneck_distribution": dict(bottlenecks),
        "stage_summary": stage_summary,
    }


def _load_schema_set(value: Any) -> set:
    try:
        if isinstance(value, str):
            from core.utils import load_dataset
            value = load_dataset(value)
    except Exception:
        pass
    return _normalize_schema_set(value)


def _normalize_schema_set(value: Any) -> set:
    normalized = Evaluator._normalize_pred_schemas(value)
    return normalized or set()


def _schema_missing(gold: set, pred: set) -> set:
    missing = set()
    for gold_item in gold:
        if not any(pred_item in gold_item for pred_item in pred):
            missing.add(gold_item)
    return missing


def _sql_list(value: Any) -> List[str]:
    if isinstance(value, list):
        return [sql for sql in (_resolve_sql(item) for item in value) if sql]
    sql = _resolve_sql(value)
    return [sql] if sql else []


def _find_before_key(row: dict, needles: tuple[str, ...]) -> Optional[str]:
    if not isinstance(row, dict):
        return None
    for key in row:
        lowered = key.lower()
        if key.startswith("pred_sql_before_") and any(needle in lowered for needle in needles):
            return key
    return None


def _candidate_index(candidates: List[str], selected: Optional[str]) -> Optional[int]:
    if selected is None:
        return None
    for index, candidate in enumerate(candidates):
        if candidate == selected:
            return index
    return None


def _first_index(values: List[Any], target: Any) -> Optional[int]:
    for index, value in enumerate(values):
        if value == target:
            return index
    return None


def _mean(values: List[float]) -> Optional[float]:
    return sum(values) / len(values) if values else None

"""Evolution-facing score comparison and Meta-Evo payload helpers."""

from __future__ import annotations

from typing import Any, Dict, Optional


def compare_scores(previous: dict, current: dict) -> dict:
    return {
        "runs": {
            "previous": previous.get("run_id"),
            "current": current.get("run_id"),
        },
        "metrics": {
            "ex": _metric_delta(previous, current, ("aggregate", "ex", "avg")),
            "em": _metric_delta(previous, current, ("aggregate", "em", "avg")),
            "sf1": _metric_delta(previous, current, ("aggregate", "sf1", "avg")),
            "ves": _metric_delta(previous, current, ("aggregate", "ves", "avg")),
            "token_total": _metric_delta(previous, current, ("aggregate", "token", "total_tokens")),
            "optimizer_fix_success_rate": _metric_delta(
                previous, current, ("aggregate", "pipeline", "optimizer", "fix_success_rate")
            ),
            "scaler_gain": _metric_delta(previous, current, ("aggregate", "pipeline", "scaler", "scaler_gain")),
            "selection_accuracy": _metric_delta(
                previous, current, ("aggregate", "pipeline", "selector", "selection_accuracy")
            ),
        },
        "regressions": {
            "ex": _ex_regressions(previous, current),
        },
        "improvements": {
            "ex": _ex_improvements(previous, current),
        },
    }


def build_meta_evo_input(scores: dict, target_metric: str = "ex") -> dict:
    aggregate = scores.get("aggregate") or {}
    error_dist = aggregate.get("error_root_distribution") or {}
    ranked_errors = sorted(error_dist.items(), key=lambda item: item[1].get("count", 0), reverse=True)
    examples = _examples_for_roots(scores.get("per_sample") or [], [root for root, _ in ranked_errors[:5]])
    return {
        "run_id": scores.get("run_id"),
        "target": {
            "metric": target_metric,
            "value": _get(scores, ("aggregate", target_metric, "avg")),
        },
        "by_hardness": scores.get("by_hardness") or {},
        "top_error_roots": [
            {
                "root": root,
                "count": stats.get("count", 0),
                "pct": stats.get("pct", 0),
                "sample_ids": stats.get("sample_ids", []),
            }
            for root, stats in ranked_errors[:5]
        ],
        "pipeline": aggregate.get("pipeline") or {},
        "token": aggregate.get("token") or {},
        "examples": examples,
    }


def _metric_delta(previous: dict, current: dict, path: tuple[str, ...]) -> dict:
    before = _get(previous, path)
    after = _get(current, path)
    return {
        "previous": before,
        "current": after,
        "delta": after - before if isinstance(before, (int, float)) and isinstance(after, (int, float)) else None,
    }


def _get(data: dict, path: tuple[str, ...]) -> Optional[Any]:
    current: Any = data
    for key in path:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


def _sample_ex_by_id(scores: dict) -> Dict[str, Any]:
    return {
        str(sample.get("instance_id")): sample.get("ex")
        for sample in scores.get("per_sample") or []
        if sample.get("instance_id") is not None
    }


def _ex_regressions(previous: dict, current: dict) -> list[str]:
    before = _sample_ex_by_id(previous)
    after = _sample_ex_by_id(current)
    return sorted(sample_id for sample_id, old in before.items() if old == 1 and after.get(sample_id) == 0)


def _ex_improvements(previous: dict, current: dict) -> list[str]:
    before = _sample_ex_by_id(previous)
    after = _sample_ex_by_id(current)
    return sorted(sample_id for sample_id, old in before.items() if old == 0 and after.get(sample_id) == 1)


def _examples_for_roots(per_sample: list[dict], roots: list[str]) -> list[dict]:
    examples = []
    for root in roots:
        for sample in per_sample:
            if sample.get("error_root") == root:
                examples.append({
                    "instance_id": sample.get("instance_id"),
                    "error_root": root,
                    "error_sub": sample.get("error_sub"),
                    "hardness": sample.get("hardness"),
                    "pipeline": sample.get("pipeline"),
                    "tokens": sample.get("tokens"),
                })
                break
    return examples

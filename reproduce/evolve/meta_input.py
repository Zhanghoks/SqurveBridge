"""Meta-Evo input payload: diagnostic state derived from a score bundle."""

from __future__ import annotations

from typing import Any, Optional


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


def _get(data: dict, path: tuple[str, ...]) -> Optional[Any]:
    current: Any = data
    for key in path:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


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

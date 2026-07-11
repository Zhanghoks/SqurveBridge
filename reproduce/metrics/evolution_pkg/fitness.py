"""Fitness scoring for bounded evolution evaluations."""

from __future__ import annotations

from typing import Any


DEFAULT_WEIGHTS = {
    "ex": 0.45,
    "em": 0.10,
    "ves": 0.10,
    "hard_slice": 0.20,
    "cost": 0.10,
    "latency": 0.05,
    "regression": 0.15,
}


def compute_fitness(
        *,
        ex: float | None = None,
        em: float | None = None,
        ves: float | None = None,
        hard_slice_score: float | None = None,
        cost_delta: float | None = None,
        latency_delta: float | None = None,
        regression_rate: float | None = None,
        weights: dict[str, float] | None = None,
) -> float:
    """Return a deterministic bounded-search fitness score.

    Metrics are expected in 0..1 units. Positive cost/latency deltas are
    regressions; negative deltas are improvements.
    """
    w = dict(DEFAULT_WEIGHTS)
    if weights:
        w.update(weights)

    score = 0.0
    score += w["ex"] * _value(ex)
    score += w["em"] * _value(em)
    score += w["ves"] * _value(ves)
    score += w["hard_slice"] * _value(hard_slice_score)
    score += w["cost"] * _cost_bonus(cost_delta)
    score += w["latency"] * _cost_bonus(latency_delta)
    score -= w["regression"] * _value(regression_rate)
    return round(score, 6)


def fitness_from_scores(
        scores: dict[str, Any],
        *,
        delta: dict[str, Any] | None = None,
        weights: dict[str, float] | None = None,
) -> float:
    aggregate = scores.get("aggregate") or {}
    delta = delta or {}
    return compute_fitness(
        ex=_metric_avg(aggregate, "ex"),
        em=_metric_avg(aggregate, "em"),
        ves=_metric_avg(aggregate, "ves"),
        hard_slice_score=_hard_slice(scores),
        cost_delta=_delta_value(delta, "token_total"),
        latency_delta=_delta_value(delta, "latency"),
        regression_rate=_regression_rate(delta, scores),
        weights=weights,
    )


def _metric_avg(aggregate: dict[str, Any], key: str) -> float | None:
    value = aggregate.get(key)
    if isinstance(value, dict):
        value = value.get("avg")
    return value if isinstance(value, (int, float)) else None


def _hard_slice(scores: dict[str, Any]) -> float | None:
    by_hardness = scores.get("by_hardness") or {}
    values = []
    for key in ("hard", "extra", "challenging"):
        item = by_hardness.get(key)
        if isinstance(item, dict) and isinstance(item.get("ex"), (int, float)):
            values.append(float(item["ex"]))
    return sum(values) / len(values) if values else None


def _delta_value(delta: dict[str, Any], key: str) -> float | None:
    metrics = delta.get("metrics") if isinstance(delta.get("metrics"), dict) else delta
    item = metrics.get(key) if isinstance(metrics, dict) else None
    if isinstance(item, dict):
        value = item.get("delta")
        return value if isinstance(value, (int, float)) else None
    return item if isinstance(item, (int, float)) else None


def _regression_rate(delta: dict[str, Any], scores: dict[str, Any]) -> float | None:
    regressions = ((delta.get("regressions") or {}).get("ex") or []) if isinstance(delta, dict) else []
    sample_count = scores.get("sample_count") or len(scores.get("per_sample") or [])
    if not sample_count:
        return None
    return len(regressions) / sample_count


def _cost_bonus(delta: float | None) -> float:
    if delta is None:
        return 0.0
    return max(-1.0, min(1.0, -float(delta)))


def _value(value: float | None) -> float:
    if value is None:
        return 0.0
    return max(0.0, min(1.0, float(value)))

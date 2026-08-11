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

# Reward assigned to a candidate that failed to produce a usable evaluation.
# It must stay below the worst achievable valid *improvement*
# (worst candidate fitness minus best baseline fitness, about -1.15) so that
# a crashed rollout can never outrank a candidate that ran and merely
# regressed.
R_INVALID = -2.0


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
        cost_delta=_relative_delta(delta, "token_total"),
        latency_delta=_relative_delta(delta, "latency_avg"),
        regression_rate=_regression_rate(delta, scores),
        weights=weights,
    )


def improvement_from_scores(
        candidate_scores: dict[str, Any],
        baseline_scores: dict[str, Any],
        *,
        delta: dict[str, Any] | None = None,
        weights: dict[str, float] | None = None,
) -> float:
    """Return the baseline-centered reward: fitness(candidate) - fitness(baseline).

    Both sides use the same weights and the same baseline bundle, so a
    candidate that changes nothing scores exactly 0 instead of inheriting the
    baseline's absolute fitness. The baseline is scored without delta terms
    (its cost/latency/regression relative to itself is zero by definition).
    """
    candidate = fitness_from_scores(candidate_scores, delta=delta, weights=weights)
    baseline = fitness_from_scores(baseline_scores, weights=weights)
    return round(candidate - baseline, 6)


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


def _relative_delta(delta: dict[str, Any], key: str) -> float | None:
    """Return a cost/latency change expressed as a fraction of the baseline.

    Absolute deltas (a token count, a wall-clock second) cannot be compared
    against the 0..1 unit scale the weights assume, and would saturate
    ``_cost_bonus`` on any real run.
    """
    metrics = delta.get("metrics") if isinstance(delta.get("metrics"), dict) else delta
    item = metrics.get(key) if isinstance(metrics, dict) else None
    if not isinstance(item, dict):
        return item if isinstance(item, (int, float)) else None
    change = item.get("delta")
    if not isinstance(change, (int, float)):
        return None
    previous = item.get("previous")
    if isinstance(previous, (int, float)) and previous:
        return change / abs(previous)
    return change


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

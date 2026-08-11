"""Uncertainty-aware statistics for aggregated evaluation cells.

Every aggregated value should carry its sample size and, where configured, a
confidence interval, so that bounded-slice results (n=50 smoke runs) cannot be
read with full-split confidence.
"""

from __future__ import annotations

import math
import random
from typing import Optional, Sequence


DEFAULT_Z = 1.959963984540054  # two-sided 95%


def mean(values: Sequence[float]) -> Optional[float]:
    values = [float(v) for v in values]
    return sum(values) / len(values) if values else None


def percentile(values: Sequence[float], p: float) -> Optional[float]:
    """Linear-interpolation percentile (inclusive), p in [0, 100]."""
    if not values:
        return None
    if not 0 <= p <= 100:
        raise ValueError(f"percentile out of range: {p}")
    ordered = sorted(float(v) for v in values)
    if len(ordered) == 1:
        return ordered[0]
    rank = (p / 100) * (len(ordered) - 1)
    lower = math.floor(rank)
    upper = math.ceil(rank)
    if lower == upper:
        return ordered[lower]
    weight = rank - lower
    return ordered[lower] * (1 - weight) + ordered[upper] * weight


def wilson_interval(successes: float, total: int, z: float = DEFAULT_Z) -> Optional[tuple[float, float]]:
    """Wilson score interval for a Bernoulli rate."""
    if total <= 0:
        return None
    phat = successes / total
    denom = 1 + z * z / total
    center = (phat + z * z / (2 * total)) / denom
    margin = (z * math.sqrt(phat * (1 - phat) / total + z * z / (4 * total * total))) / denom
    return (max(0.0, center - margin), min(1.0, center + margin))


def bootstrap_interval(
        values: Sequence[float],
        *,
        n_resamples: int = 1000,
        confidence: float = 0.95,
        seed: int = 42,
) -> Optional[tuple[float, float]]:
    """Deterministic percentile-bootstrap interval for the mean."""
    values = [float(v) for v in values]
    if not values:
        return None
    if len(values) == 1:
        return (values[0], values[0])
    rng = random.Random(seed)
    n = len(values)
    means = []
    for _ in range(n_resamples):
        sample = [values[rng.randrange(n)] for _ in range(n)]
        means.append(sum(sample) / n)
    alpha = (1 - confidence) / 2 * 100
    return (percentile(means, alpha), percentile(means, 100 - alpha))


def min_sample_ok(n: int, minimum: int) -> bool:
    return n >= max(minimum, 1)

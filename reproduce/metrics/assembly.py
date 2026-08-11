"""Forwarding facade: the bundle builder moved to ``reproduce.eval.bundle.build``.

Kept so existing imports (`from reproduce.metrics.assembly import build_scores`)
stay valid during the evaluation-package migration. New code should import from
``reproduce.eval.bundle.build`` directly.
"""

from reproduce.eval.bundle.build import (  # noqa: F401
    CF1_KEYS,
    HARDNESS_ORDER,
    METRIC_KEYS,
    auto_hardness,
    build_scores,
)

__all__ = [
    "CF1_KEYS",
    "HARDNESS_ORDER",
    "METRIC_KEYS",
    "auto_hardness",
    "build_scores",
]

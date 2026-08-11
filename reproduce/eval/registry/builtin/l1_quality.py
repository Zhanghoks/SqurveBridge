"""L1: final-SQL quality metrics."""

from __future__ import annotations

from reproduce.eval.registry.registry import MetricRegistry
from reproduce.eval.registry.spec import MetricSpec


def register(registry: MetricRegistry) -> None:
    registry.register_all([
        MetricSpec(
            id="ex", layer="L1", source="ex", aggregation="rate",
            interval="wilson",
            description="Execution accuracy against gold result sets.",
        ),
        MetricSpec(
            id="em", layer="L1", source="em", aggregation="rate",
            interval="wilson",
            description="Exact match over the seven normalized SQL component sets.",
        ),
        MetricSpec(
            id="sf1", layer="L1", source="sf1", aggregation="mean",
            interval="bootstrap",
            description="Soft result-set F1 with partial credit for overlap.",
        ),
        MetricSpec(
            id="sc", layer="L1", source="sc", aggregation="mean",
            description="Self-consistency across generate_num candidates (needs generate_num >= 2).",
        ),
        MetricSpec(
            id="ves", layer="L1", source="ves", aggregation="mean",
            interval="bootstrap",
            description="Valid-efficiency score; efficiency counted only when the result is correct.",
        ),
        MetricSpec(
            id="rves", layer="L1", source="rves", aggregation="mean",
            interval="bootstrap",
            description="Reward-weighted valid-efficiency score.",
        ),
    ])

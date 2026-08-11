"""L3: structural behavior of the predicted SQL."""

from __future__ import annotations

from reproduce.eval.registry.registry import MetricRegistry
from reproduce.eval.registry.spec import MetricSpec


CF1_COMPONENTS = ("select", "where", "group", "order", "join", "iuen", "keywords")


def register(registry: MetricRegistry) -> None:
    for component in CF1_COMPONENTS:
        registry.register(MetricSpec(
            id=f"cf1_{component}", layer="L3", source=f"cf1.cf1_{component}",
            aggregation="mean", publication="aggregate_only",
            description=f"Component F1 over the normalized {component.upper()} clause set.",
        ))
    registry.register_all([
        MetricSpec(
            id="sl_recall", layer="L3", source="sl_recall", aggregation="mean",
            publication="aggregate_only",
            description="Schema-linking recall captured by linking-aware methods.",
        ),
        MetricSpec(
            id="fd", layer="L3", source="derived:fd", aggregation="derived",
            publication="aggregate_only", sliceable=False,
            description="Predicted-minus-gold SQL feature deltas (mean and std per feature).",
        ),
    ])

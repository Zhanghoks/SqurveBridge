"""Builtin metric and slice declarations for the six evaluation layers."""

from __future__ import annotations

from reproduce.eval.registry.registry import MetricRegistry
from reproduce.eval.registry.spec import SliceSpec
from reproduce.eval.registry.builtin import (  # noqa: F401
    l1_quality,
    l2_cost,
    l3_structure,
    l4_attribution,
    l5_process,
    l6_matrix,
)


HARDNESS_ORDER = ("easy", "medium", "hard", "extra")


def register_builtins(registry: MetricRegistry) -> None:
    l1_quality.register(registry)
    l2_cost.register(registry)
    l3_structure.register(registry)
    l4_attribution.register(registry)
    l5_process.register(registry)
    l6_matrix.register(registry)

    registry.register_slice(SliceSpec(
        id="hardness", field="hardness", values=HARDNESS_ORDER,
        description="Auto-classified SQL hardness (Spider taxonomy).",
    ))
    registry.register_slice(SliceSpec(
        id="db_type", field="db_type",
        description="Database backend type (sqlite, bigquery, snowflake, ...).",
    ))

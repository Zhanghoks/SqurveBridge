"""L6: cross-method comparative metrics.

Derived from the correctness/latency matrix ``(query, method) -> (Y, t)``
stored in the eval store across runs; computed by
``reproduce/eval/views/matrix.py``. Definitions follow arXiv 2602.15564
Section 3 and Appendices B/C.
"""

from __future__ import annotations

from reproduce.eval.registry.registry import MetricRegistry
from reproduce.eval.registry.spec import MetricSpec


def register(registry: MetricRegistry) -> None:
    registry.register_all([
        MetricSpec(
            id="oracle_gap", layer="L6", source="derived:oracle_gap",
            aggregation="matrix", sliceable=False, publication="aggregate_only",
            description="EX_dynamic minus EX_static: gain from per-query oracle method selection.",
        ),
        MetricSpec(
            id="method_disagreement", layer="L6", source="derived:method_disagreement",
            aggregation="matrix", sliceable=False, publication="aggregate_only",
            description="Pairwise correctness/efficiency disagreement matrix across methods.",
        ),
        MetricSpec(
            id="empirical_difficulty", layer="L6", source="derived:empirical_difficulty",
            aggregation="matrix", sliceable=False, publication="aggregate_only",
            description="Per-query count of methods that solve it (N(q)).",
        ),
        MetricSpec(
            id="uniquely_solved", layer="L6", source="derived:uniquely_solved",
            aggregation="matrix", sliceable=False, publication="aggregate_only",
            description="Per-method count of queries only that method solves.",
        ),
        MetricSpec(
            id="efficiency_headroom", layer="L6", source="derived:efficiency_headroom",
            aggregation="matrix", sliceable=False, publication="aggregate_only",
            description="Correctness-constrained latency headroom per difficulty stratum.",
        ),
    ])

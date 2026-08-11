"""L2: runtime and cost metrics.

Latency metrics fold ``act_elapsed_s`` (captured per sample by the engine
runtime); token metrics fold the per-sample token map. Both were previously
captured but only partially aggregated.
"""

from __future__ import annotations

from reproduce.eval.registry.registry import MetricRegistry
from reproduce.eval.registry.spec import MetricSpec


def register(registry: MetricRegistry) -> None:
    registry.register_all([
        MetricSpec(
            id="latency_avg", layer="L2", source="act_elapsed_s",
            aggregation="mean", unit="seconds", higher_is_better=False,
            interval="bootstrap", publication="aggregate_only",
            description="Mean per-sample actor wall time.",
        ),
        MetricSpec(
            id="latency_p50", layer="L2", source="act_elapsed_s",
            aggregation="percentile:50", unit="seconds", higher_is_better=False,
            publication="aggregate_only",
            description="Median per-sample actor wall time.",
        ),
        MetricSpec(
            id="latency_p95", layer="L2", source="act_elapsed_s",
            aggregation="percentile:95", unit="seconds", higher_is_better=False,
            publication="aggregate_only",
            description="95th-percentile per-sample actor wall time.",
        ),
        MetricSpec(
            id="token_total", layer="L2", source="derived:token_total",
            aggregation="derived", unit="tokens", higher_is_better=False,
            publication="aggregate_only", sliceable=False,
            description="Total tokens across all calls (from the token logger).",
        ),
        MetricSpec(
            id="token_avg_per_sample", layer="L2", source="derived:token_avg_per_sample",
            aggregation="derived", unit="tokens", higher_is_better=False,
            publication="aggregate_only", sliceable=False,
            description="Average tokens per evaluated sample.",
        ),
        MetricSpec(
            id="cost_per_correct", layer="L2", source="derived:cost_per_correct",
            aggregation="derived", unit="tokens", higher_is_better=False,
            publication="aggregate_only", sliceable=False,
            description="Total tokens divided by the number of correct samples.",
        ),
    ])

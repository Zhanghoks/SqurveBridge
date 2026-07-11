"""Promotion policy for smoke, bounded, and full evolution stages."""

from __future__ import annotations

from typing import Iterable

from reproduce.metrics.evolution_pkg.node import EvolutionNode


def smoke_gate_promote(nodes: Iterable[EvolutionNode], promote_top_k: int = 2) -> list[EvolutionNode]:
    return _promote(nodes, promote_top_k=promote_top_k, decision="smoke_promoted")


def bounded_eval_promote(nodes: Iterable[EvolutionNode], promote_top_k: int = 1) -> list[EvolutionNode]:
    return _promote(nodes, promote_top_k=promote_top_k, decision="full_confirmation")


def _promote(nodes: Iterable[EvolutionNode], *, promote_top_k: int, decision: str) -> list[EvolutionNode]:
    node_list = list(nodes)
    ranked = sorted(
        [node for node in node_list if node.status == "pass" and node.fitness is not None],
        key=lambda node: (float(node.fitness), -node.branch_id),
        reverse=True,
    )
    promoted_ids = {node.node_id for node in ranked[:promote_top_k]}
    for node in node_list:
        node.promoted = node.node_id in promoted_ids
        if node.promoted:
            node.decision = decision
    return ranked[:promote_top_k]

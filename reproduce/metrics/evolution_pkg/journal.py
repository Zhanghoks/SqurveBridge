"""Journal state for evolution runs."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from reproduce.metrics.evolution_pkg.artifacts import read_json, write_json
from reproduce.metrics.evolution_pkg.node import EvolutionNode


@dataclass
class EvolutionJournal:
    evolve_slug: str
    baseline_run_slug: str | None = None
    method: str | None = None
    benchmark: str | None = None
    policy: str = "bounded_search_default"
    round: int = 0
    rounds_completed: int = 0
    nodes: list[EvolutionNode] = field(default_factory=list)
    best_node: str | None = None
    recommendation: str | None = None
    stagnation: dict[str, Any] = field(default_factory=lambda: {
        "branch_stagnant": [],
        "global_stagnant": False,
        "dry_rounds": 0,
    })

    def add_node(self, node: EvolutionNode) -> None:
        if any(existing.node_id == node.node_id for existing in self.nodes):
            raise ValueError(f"Duplicate evolution node: {node.node_id}")
        self.nodes.append(node)
        self.update_best()

    def update_node(self, node_id: str, **changes: Any) -> EvolutionNode:
        node = self.get_node(node_id)
        for key, value in changes.items():
            if not hasattr(node, key):
                raise AttributeError(key)
            setattr(node, key, value)
        node.__post_init__()
        self.update_best()
        return node

    def get_node(self, node_id: str) -> EvolutionNode:
        for node in self.nodes:
            if node.node_id == node_id:
                return node
        raise KeyError(node_id)

    def ranked_nodes(self, *, status: str | None = "pass") -> list[EvolutionNode]:
        nodes = [node for node in self.nodes if node.fitness is not None]
        if status is not None:
            nodes = [node for node in nodes if node.status == status]
        return sorted(nodes, key=lambda node: float(node.fitness), reverse=True)

    def update_best(self) -> str | None:
        ranked = self.ranked_nodes(status=None)
        self.best_node = ranked[0].node_id if ranked else None
        return self.best_node

    def branch_stagnant(self, branch_id: int, threshold: int = 3, epsilon: float = 0.0) -> bool:
        branch_nodes = [node for node in self.nodes if node.branch_id == branch_id and node.fitness is not None]
        if len(branch_nodes) < threshold + 1:
            return False
        best_before = max(float(node.fitness) for node in branch_nodes[:-threshold])
        recent_best = max(float(node.fitness) for node in branch_nodes[-threshold:])
        stagnant = recent_best <= best_before + epsilon
        if stagnant:
            current = set(self.stagnation.get("branch_stagnant") or [])
            current.add(branch_id)
            self.stagnation["branch_stagnant"] = sorted(current)
        return stagnant

    def global_stagnant(self, window: int = 4, epsilon: float = 0.0) -> bool:
        scored = [node for node in self.nodes if node.fitness is not None]
        if len(scored) < window + 1:
            self.stagnation["global_stagnant"] = False
            return False
        best_before = max(float(node.fitness) for node in scored[:-window])
        recent_best = max(float(node.fitness) for node in scored[-window:])
        stagnant = recent_best <= best_before + epsilon
        self.stagnation["global_stagnant"] = stagnant
        if stagnant:
            self.stagnation["dry_rounds"] = int(self.stagnation.get("dry_rounds") or 0) + 1
        else:
            self.stagnation["dry_rounds"] = 0
        return stagnant

    def top_k_diverse(self, k: int, per_branch_limit: int = 1) -> list[EvolutionNode]:
        selected: list[EvolutionNode] = []
        counts: dict[int, int] = {}
        for node in self.ranked_nodes(status="pass"):
            if counts.get(node.branch_id, 0) >= per_branch_limit:
                continue
            selected.append(node)
            counts[node.branch_id] = counts.get(node.branch_id, 0) + 1
            if len(selected) >= k:
                break
        return selected

    def to_dict(self) -> dict[str, Any]:
        return {
            "evolve_slug": self.evolve_slug,
            "baseline_run_slug": self.baseline_run_slug,
            "method": self.method,
            "benchmark": self.benchmark,
            "policy": self.policy,
            "round": self.round,
            "rounds_completed": self.rounds_completed,
            "nodes": [node.to_dict() for node in self.nodes],
            "best_node": self.best_node,
            "recommendation": self.recommendation,
            "stagnation": self.stagnation,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "EvolutionJournal":
        return cls(
            evolve_slug=str(data["evolve_slug"]),
            baseline_run_slug=data.get("baseline_run_slug"),
            method=data.get("method"),
            benchmark=data.get("benchmark"),
            policy=str(data.get("policy", "bounded_search_default")),
            round=int(data.get("round", 0)),
            rounds_completed=int(data.get("rounds_completed", 0)),
            nodes=[EvolutionNode.from_dict(item) for item in data.get("nodes") or []],
            best_node=data.get("best_node"),
            recommendation=data.get("recommendation"),
            stagnation=dict(data.get("stagnation") or {}),
        )

    def write(self, path: str | Path) -> Path:
        return write_json(path, self.to_dict())

    @classmethod
    def read(cls, path: str | Path) -> "EvolutionJournal":
        return cls.from_dict(read_json(path))

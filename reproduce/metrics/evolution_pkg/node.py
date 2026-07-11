"""Evolution node schema and serialization."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


VALID_STATUSES = {"planned", "running", "pass", "buggy", "reverted", "recommended"}


@dataclass
class EvolutionNode:
    node_id: str
    parent_id: str = "baseline"
    branch_id: int = 0
    stage: str = "improve"
    method: str = ""
    benchmark: str = ""
    target_dimensions: list[str] = field(default_factory=list)
    change_scope: str = ""
    allowed_scope: list[str] = field(default_factory=lambda: ["prompt", "config", "adapter"])
    plan_path: str = "change-plan.md"
    patch_path: str = "patch.diff"
    run_command_path: str = "run-command.sh"
    fitness: float | None = None
    status: str = "planned"
    decision: str = "candidate"
    promoted: bool = False
    scores: dict[str, Any] = field(default_factory=dict)
    delta: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.status not in VALID_STATUSES:
            raise ValueError(f"Invalid evolution node status: {self.status}")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "EvolutionNode":
        return cls(
            node_id=str(data["node_id"]),
            parent_id=str(data.get("parent_id", "baseline")),
            branch_id=int(data.get("branch_id", 0)),
            stage=str(data.get("stage", "improve")),
            method=str(data.get("method", "")),
            benchmark=str(data.get("benchmark", "")),
            target_dimensions=list(data.get("target_dimensions") or []),
            change_scope=str(data.get("change_scope", "")),
            allowed_scope=list(data.get("allowed_scope") or ["prompt", "config", "adapter"]),
            plan_path=str(data.get("plan_path", "change-plan.md")),
            patch_path=str(data.get("patch_path", "patch.diff")),
            run_command_path=str(data.get("run_command_path", "run-command.sh")),
            fitness=data.get("fitness"),
            status=str(data.get("status", "planned")),
            decision=str(data.get("decision", "candidate")),
            promoted=bool(data.get("promoted", False)),
            scores=dict(data.get("scores") or {}),
            delta=dict(data.get("delta") or {}),
            metadata=dict(data.get("metadata") or {}),
        )

    def write(self, path: str | Path) -> Path:
        from reproduce.metrics.evolution_pkg.artifacts import write_json

        return write_json(path, self.to_dict())

    @classmethod
    def read(cls, path: str | Path) -> "EvolutionNode":
        from reproduce.metrics.evolution_pkg.artifacts import read_json

        return cls.from_dict(read_json(path))

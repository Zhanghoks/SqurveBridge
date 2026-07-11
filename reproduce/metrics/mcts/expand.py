"""Action providers for Meta-Evo MCTS expansion."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Iterable, List, Sequence, Set


@dataclass
class Action:
    action_id: str
    description: str
    target_metric: str
    scope: str
    risk: str
    patches: List[dict] = field(default_factory=list)
    run_command: str = ""

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "Action":
        return cls(
            action_id=str(data["action_id"]),
            description=str(data.get("description", "")),
            target_metric=str(data.get("target_metric", "ex")),
            scope=str(data.get("scope", "B")),
            risk=str(data.get("risk", "medium")),
            patches=list(data.get("patches") or []),
            run_command=str(data.get("run_command", "")),
        )


def load_actions(path: str | Path) -> List[Action]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return [Action.from_dict(item) for item in data]


def generate_actions(
        weakness_profile: str,
        existing_action_ids: Set[str] | None = None,
        limit: int = 4,
) -> List[Action]:
    existing_action_ids = existing_action_ids or set()
    candidates = _heuristic_candidates(weakness_profile)
    result = []
    for action in candidates:
        if action.action_id in existing_action_ids:
            continue
        result.append(action)
        if len(result) >= limit:
            break
    return result


def choose_actions(pool: Sequence[Action], used_ids: Iterable[str], limit: int) -> List[Action]:
    used = set(used_ids)
    return [action for action in pool if action.action_id not in used][:limit]


def _heuristic_candidates(profile: str) -> List[Action]:
    text = profile.lower()
    candidates = []
    if "join" in text:
        candidates.append(Action(
            action_id="heuristic-join-prompt",
            description="Tighten JOIN evidence collection in the generator/parser prompt path.",
            target_metric="cf1_join",
            scope="B",
            risk="medium",
            patches=[],
        ))
    if "where" in text or "predicate" in text:
        candidates.append(Action(
            action_id="heuristic-predicate-coverage",
            description="Add stricter predicate preservation guidance.",
            target_metric="cf1_where",
            scope="B",
            risk="medium",
            patches=[],
        ))
    if "schema_linking_miss" in text or "schema" in text:
        candidates.append(Action(
            action_id="heuristic-schema-linking",
            description="Improve schema linking recall before SQL generation.",
            target_metric="schema_linking_miss",
            scope="B",
            risk="medium",
            patches=[],
        ))
    candidates.append(Action(
        action_id="heuristic-general-sql-validity",
        description="Improve final SQL validity and execution safety.",
        target_metric="ex",
        scope="B",
        risk="low",
        patches=[],
    ))
    return candidates

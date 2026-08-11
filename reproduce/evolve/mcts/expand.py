"""Action providers for Meta-Evo MCTS expansion."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Iterable, List, Sequence, Set, Tuple


_SCOPE_ORDER = {"A": 0, "B": 1, "C": 2}
_RISK_ORDER = {"low": 0, "medium": 1, "high": 2}


@dataclass
class Action:
    action_id: str
    description: str
    target_metric: str
    scope: str
    risk: str
    patches: List[dict] = field(default_factory=list)
    run_command: str = ""

    @property
    def executable(self) -> bool:
        """An action with neither patches nor a run command evaluates nothing
        but the baseline, so running it only burns rollout budget."""
        return bool(self.patches) or bool(self.run_command)

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
    """Return heuristic *templates* derived from a weakness profile.

    These candidates carry no patches; they are outlines for the Meta-Evo
    agent to fill in. Until an agent attaches concrete patches (or a run
    command) they are not executable and must not enter the search pool —
    ``filter_executable`` enforces that at pool-loading time.
    """
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


def filter_executable(actions: Sequence[Action]) -> Tuple[List[Action], List[str]]:
    """Split a pool into executable actions and skipped (no patch, no command) ids."""
    executable = [action for action in actions if action.executable]
    skipped = [action.action_id for action in actions if not action.executable]
    return executable, skipped


def combine_actions(chain: Sequence[Action]) -> Action:
    """Merge a root->leaf action chain into one composite action.

    Patches are concatenated in chain order so a rollout applies the whole
    path; scope and risk take the most severe value on the chain, and the
    run command comes from the last action that declares one.
    """
    if not chain:
        raise ValueError("combine_actions requires a non-empty chain")
    if len(chain) == 1:
        return chain[0]
    patches: List[dict] = []
    for action in chain:
        patches.extend(action.patches)
    run_command = ""
    for action in chain:
        if action.run_command:
            run_command = action.run_command
    return Action(
        action_id="+".join(action.action_id for action in chain),
        description="; ".join(action.description for action in chain if action.description),
        target_metric=chain[-1].target_metric,
        scope=max((action.scope for action in chain), key=lambda s: _SCOPE_ORDER.get(s, 1)),
        risk=max((action.risk for action in chain), key=lambda r: _RISK_ORDER.get(r, 1)),
        patches=patches,
        run_command=run_command,
    )


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

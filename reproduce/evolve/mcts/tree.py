"""Monte Carlo tree structures for Meta-Evo search."""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Sequence


EXPLORATION_C = 1.41421356237


@dataclass
class TreeNode:
    node_id: str
    parent_id: Optional[str] = None
    branch_id: int = 0
    depth: int = 0
    action: Optional[dict] = None
    visits: int = 0
    total_score: float = 0.0
    scores: List[float] = field(default_factory=list)
    children: List["TreeNode"] = field(default_factory=list)
    status: str = "open"
    best_score: float | None = None
    last_improved_at: int | None = None
    forced_backprop: bool = False

    @property
    def average_score(self) -> float:
        return self.total_score / self.visits if self.visits else 0.0

    @property
    def value(self) -> float:
        return self.average_score

    def to_dict(self) -> dict:
        return {
            "node_id": self.node_id,
            "parent_id": self.parent_id,
            "branch_id": self.branch_id,
            "depth": self.depth,
            "action": self.action,
            "visits": self.visits,
            "total_score": self.total_score,
            "scores": self.scores,
            "value": self.value,
            "average_score": self.average_score,
            "status": self.status,
            "best_score": self.best_score,
            "last_improved_at": self.last_improved_at,
            "forced_backprop": self.forced_backprop,
            "children": [child.to_dict() for child in self.children],
        }

    @classmethod
    def from_dict(cls, data: dict) -> "TreeNode":
        node = cls(
            node_id=data["node_id"],
            parent_id=data.get("parent_id"),
            branch_id=data.get("branch_id", 0),
            depth=data.get("depth", 0),
            action=data.get("action"),
            visits=data.get("visits", 0),
            total_score=data.get("total_score", 0.0),
            scores=list(data.get("scores") or []),
            status=data.get("status", "open"),
            best_score=data.get("best_score"),
            last_improved_at=data.get("last_improved_at"),
            forced_backprop=bool(data.get("forced_backprop", False)),
        )
        node.children = [cls.from_dict(child) for child in data.get("children") or []]
        return node


def progressive_width(visits: int) -> int:
    return max(1, min(4, math.ceil(math.sqrt(max(1, visits)))))


def explore_weight(progress: float, *, min_weight: float = 0.2) -> float:
    progress = max(0.0, min(1.0, progress))
    if progress < 0.5:
        return 1.0
    if progress < 0.7:
        return 1.0 - ((progress - 0.5) / 0.2) * (1.0 - min_weight)
    return min_weight


def decay_exploration(base: float, progress: float) -> float:
    return base * explore_weight(progress)


@dataclass
class ActionStats:
    """Bandit statistics for one candidate update, shared across the tree.

    ``visits`` is a float so that prior-experience warm starts can inject
    discounted pseudo-counts that real evaluations quickly outweigh.
    """

    action_id: str
    visits: float = 0.0
    total_reward: float = 0.0

    @property
    def average_reward(self) -> float:
        return self.total_reward / self.visits if self.visits else 0.0


def record_action_result(stats: Dict[str, ActionStats], action_id: str, reward: float) -> ActionStats:
    entry = stats.setdefault(action_id, ActionStats(action_id=action_id))
    entry.visits += 1
    entry.total_reward += reward
    return entry


def warm_start_action_stats(
        stats: Dict[str, ActionStats],
        priors: Iterable[Any],
        *,
        discount: float = 0.3,
        failed_reward: float = -1.0,
        known_action_ids: set[str] | None = None,
) -> Dict[str, ActionStats]:
    """Seed bandit statistics from prior evolution runs.

    Each historical evaluation contributes ``discount`` pseudo-visits. A
    successful prior contributes its recorded fitness; a failed one (rolled
    back, buggy, REGRESSION) contributes ``failed_reward`` so the action is
    down-weighted rather than excluded — it stays selectable if fresh
    evidence favors it or nothing better exists.
    """
    for prior in priors:
        action_id = getattr(prior, "action_id", None)
        if not action_id:
            continue
        if known_action_ids is not None and action_id not in known_action_ids:
            continue
        failed = bool(getattr(prior, "failed", False))
        fitness = getattr(prior, "fitness", None)
        if failed:
            reward = failed_reward
        elif isinstance(fitness, (int, float)):
            reward = float(fitness)
        else:
            continue
        entry = stats.setdefault(action_id, ActionStats(action_id=action_id))
        entry.visits += discount
        entry.total_reward += discount * reward
    return stats


def action_uct_score(
        stats: Dict[str, ActionStats],
        action_id: str,
        parent_visits: int,
        exploration: float = EXPLORATION_C,
) -> float:
    entry = stats.get(action_id)
    if entry is None or entry.visits == 0:
        return float("inf")
    return entry.average_reward + exploration * math.sqrt(math.log(max(parent_visits, 1)) / entry.visits)


def select_action(
        actions: Sequence[Any],
        stats: Dict[str, ActionStats],
        parent_visits: int,
        exploration: float = EXPLORATION_C,
) -> Optional[Any]:
    """Pick the next update to expand using UCT over candidate actions.

    Untried actions score ``inf`` so every candidate is sampled once before any
    is revisited. Ties keep the caller's ordering, which keeps a search
    reproducible for a fixed action pool.
    """
    if not actions:
        return None
    return max(
        actions,
        key=lambda action: action_uct_score(stats, action.action_id, parent_visits, exploration),
    )


def ancestor_action_ids(node: TreeNode, nodes_by_id: Dict[str, TreeNode]) -> List[str]:
    """Return action ids along the root->node path, ordered root-first."""
    chain: List[str] = []
    current: Optional[TreeNode] = node
    while current is not None:
        if current.action:
            action_id = current.action.get("action_id")
            if action_id:
                chain.append(str(action_id))
        current = nodes_by_id.get(current.parent_id) if current.parent_id else None
    chain.reverse()
    return chain


def child_action_ids(node: TreeNode) -> Iterable[str]:
    return {
        str(child.action.get("action_id"))
        for child in node.children
        if child.action and child.action.get("action_id")
    }


def uct_score(node: TreeNode, parent_visits: int, exploration: float = EXPLORATION_C) -> float:
    if node.visits == 0:
        return float("inf")
    return node.average_score + exploration * math.sqrt(math.log(max(parent_visits, 1)) / node.visits)


def select_leaf(root: TreeNode, exploration: float = EXPLORATION_C) -> TreeNode:
    node = root
    while node.children:
        node = max(node.children, key=lambda child: uct_score(child, max(node.visits, 1), exploration))
        if node.visits == 0:
            return node
    return node


def backpropagate(node: TreeNode, score: float, nodes_by_id: Dict[str, TreeNode]) -> None:
    current: Optional[TreeNode] = node
    while current is not None:
        current.visits += 1
        current.total_score += score
        current.scores.append(score)
        if current.best_score is None or score > current.best_score:
            current.best_score = score
            current.last_improved_at = current.visits
        current = nodes_by_id.get(current.parent_id) if current.parent_id else None


def best_path(root: TreeNode) -> List[TreeNode]:
    """Greedy descent that stops as soon as no child improves on its parent.

    Descending all the way to a leaf would report the last node on the branch
    even when it scored worse than the node it extends, which is how a failed
    rollout can end up presented as the search result.
    """
    path: List[TreeNode] = []
    node = root
    while node.children:
        best_child = max(node.children, key=lambda child: (child.average_score, child.visits))
        if path and best_child.average_score <= node.average_score:
            break
        path.append(best_child)
        node = best_child
    return path


def index_nodes(root: TreeNode) -> Dict[str, TreeNode]:
    result = {root.node_id: root}
    for child in root.children:
        result.update(index_nodes(child))
    return result


def add_child(parent: TreeNode, node_id: str, action: dict, branch_id: int | None = None) -> TreeNode:
    child = TreeNode(
        node_id=node_id,
        parent_id=parent.node_id,
        branch_id=branch_id if branch_id is not None else parent.branch_id,
        depth=parent.depth + 1,
        action=action,
    )
    parent.children.append(child)
    return child

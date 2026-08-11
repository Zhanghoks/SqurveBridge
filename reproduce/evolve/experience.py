"""Markdown experience memory helpers and prior-experience loading.

Writing: ``append_success`` / ``append_failed_pattern`` persist reviewed
outcomes into ``evolution-memory.md``. Include ``- Action: <action_id>``
lines in the body so later searches can parse them back.

Reading: ``action_priors_from_journal`` and ``failed_action_ids_from_memory``
turn past evolution runs into warm-start signal for the next search.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any, Iterable


def append_success(memory_path: str | Path, *, title: str, body: str) -> Path:
    return _append(memory_path, "Successful Patterns", title=title, body=body)


def append_failed_pattern(memory_path: str | Path, *, title: str, body: str) -> Path:
    return _append(memory_path, "Failed Patterns", title=title, body=body)


@dataclass
class ActionPrior:
    """One historical evaluation of a candidate action."""

    action_id: str
    fitness: float | None
    failed: bool


def action_priors_from_journal(journal: dict[str, Any]) -> list[ActionPrior]:
    """Extract per-action outcomes from a past journal.json payload.

    A node counts as failed when it was rolled back, recorded as buggy, or
    its verdict was REGRESSION/STOP; everything else with a fitness is a
    (possibly weak) success signal.
    """
    priors: list[ActionPrior] = []
    for node in journal.get("nodes") or []:
        action = (node.get("metadata") or {}).get("action") or {}
        action_id = action.get("action_id")
        if not action_id:
            continue
        verdict = ((node.get("delta") or {}).get("verdict") or "").upper()
        failed = (
            node.get("status") in {"buggy", "reverted"}
            or node.get("decision") == "rolled_back"
            or verdict in {"REGRESSION", "STOP"}
        )
        fitness = node.get("fitness")
        priors.append(ActionPrior(
            action_id=str(action_id),
            fitness=float(fitness) if isinstance(fitness, (int, float)) else None,
            failed=failed,
        ))
    return priors


def failed_action_ids_from_memory(memory_path: str | Path) -> set[str]:
    """Parse ``- Action: <id>`` lines under Failed Patterns sections."""
    path = Path(memory_path)
    if not path.exists():
        return set()
    failed: set[str] = set()
    in_failed_section = False
    for line in path.read_text(encoding="utf-8").splitlines():
        heading = re.match(r"^##\s+(.*)$", line.strip())
        if heading:
            in_failed_section = heading.group(1).strip() == "Failed Patterns"
            continue
        if in_failed_section:
            match = re.match(r"^-\s*Action:\s*(\S+)", line.strip())
            if match:
                failed.add(match.group(1))
    return failed


def merge_priors(journal_payloads: Iterable[dict[str, Any]]) -> list[ActionPrior]:
    priors: list[ActionPrior] = []
    for payload in journal_payloads:
        priors.extend(action_priors_from_journal(payload))
    return priors


def _append(memory_path: str | Path, section: str, *, title: str, body: str) -> Path:
    path = Path(memory_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    existing = path.read_text(encoding="utf-8") if path.exists() else "# Evolution Memory\n\n"
    entry = f"\n## {section}\n### {title}\n- Date: {date.today().isoformat()}\n{body.rstrip()}\n"
    path.write_text(existing.rstrip() + "\n" + entry, encoding="utf-8")
    return path

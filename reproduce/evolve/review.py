"""Deterministic review-loop ledger for Meta-Evo artifacts.

The AI review loop (``skills/evolve-review/SKILL.md``) iterates
review -> findings -> revise -> re-review. This module owns the
deterministic side of that loop: the findings ledger, round history,
and the verdict rule. The agent authors and resolves findings; this
module decides whether the loop may exit.

Verdict rule (``compute_verdict``):

- ``revise``    open blocker/major findings remain, budget not exhausted.
- ``approve``   no open blocker/major findings AND the most recent
                completed round introduced zero new blocker/major
                findings (a "clean round"). Minor/nit findings do not
                block approval but stay on record.
- ``escalate``  ``max_rounds`` exhausted before an approvable state was
                reached (open blocker/major findings remain, or no clean
                round materialized). Escalation hands the target to the
                human gate; the loop must not keep spinning. Waiving a
                blocker/major finding without a human decision is not an
                escalation path: ``waive_finding`` rejects it outright.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path
from typing import Any, Literal, get_args

from reproduce.evolve.process_artifacts import now_iso, write_json

Severity = Literal["blocker", "major", "minor", "nit"]
SEVERITIES = set(get_args(Severity))
BLOCKING_SEVERITIES = {"blocker", "major"}

TARGET_KINDS = {
    "change-plan",
    "patch",
    "weakness-profile",
    "comparison-report",
    "evaluator-report",
    "skill-doc",
}

DEFAULT_MAX_ROUNDS = 5
DEFAULT_CLEAN_ROUNDS_REQUIRED = 1


@dataclass
class Finding:
    finding_id: str
    severity: str
    category: str
    location: str
    summary: str
    recommendation: str
    status: str = "open"  # open | resolved | waived
    opened_round: int = 1
    closed_round: int | None = None
    resolution: str | None = None
    waived_by_human: bool = False

    def is_open_blocking(self) -> bool:
        return self.status == "open" and self.severity in BLOCKING_SEVERITIES


@dataclass
class ReviewRound:
    round: int
    reviewer: str
    new_finding_ids: list[str] = field(default_factory=list)
    notes: str = ""
    at: str = field(default_factory=now_iso)


@dataclass
class ReviewState:
    version: int
    target_kind: str
    target_ref: str
    status: str = "in_review"  # in_review | approved | escalated
    max_rounds: int = DEFAULT_MAX_ROUNDS
    clean_rounds_required: int = DEFAULT_CLEAN_ROUNDS_REQUIRED
    rounds: list[ReviewRound] = field(default_factory=list)
    findings: list[Finding] = field(default_factory=list)
    escalation_reason: str | None = None
    created_at: str = field(default_factory=now_iso)
    updated_at: str = field(default_factory=now_iso)

    # -- queries ---------------------------------------------------------

    @property
    def current_round(self) -> int:
        return len(self.rounds)

    def open_blocking(self) -> list[Finding]:
        return [f for f in self.findings if f.is_open_blocking()]

    def open_findings(self) -> list[Finding]:
        return [f for f in self.findings if f.status == "open"]

    def finding(self, finding_id: str) -> Finding:
        for candidate in self.findings:
            if candidate.finding_id == finding_id:
                return candidate
        raise KeyError(f"Unknown finding: {finding_id}")

    # -- serialization ---------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["verdict"] = compute_verdict(self)
        return payload

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ReviewState":
        state = _from_fields(cls, data)
        state.rounds = [_from_fields(ReviewRound, item) for item in data.get("rounds", [])]
        state.findings = [_from_fields(Finding, item) for item in data.get("findings", [])]
        return state


def _from_fields(cls, data: dict[str, Any]):
    """Build a dataclass from a JSON dict, ignoring unknown/derived keys.

    Nested ``rounds``/``findings`` are rebuilt separately by the caller.
    """
    names = {f.name for f in fields(cls)}
    return cls(**{k: v for k, v in data.items() if k in names and k not in ("rounds", "findings")})


# -- lifecycle -------------------------------------------------------------


def open_review(
        *,
        target_kind: str,
        target_ref: str,
        max_rounds: int = DEFAULT_MAX_ROUNDS,
        clean_rounds_required: int = DEFAULT_CLEAN_ROUNDS_REQUIRED,
) -> ReviewState:
    if target_kind not in TARGET_KINDS:
        raise ValueError(f"Unknown review target kind: {target_kind} (expected one of {sorted(TARGET_KINDS)})")
    if max_rounds < 1:
        raise ValueError("max_rounds must be >= 1")
    return ReviewState(
        version=1,
        target_kind=target_kind,
        target_ref=target_ref,
        max_rounds=max_rounds,
        clean_rounds_required=clean_rounds_required,
    )


def record_round(
        state: ReviewState,
        *,
        reviewer: str,
        findings: list[dict[str, Any]] | None = None,
        notes: str = "",
) -> ReviewState:
    """Record one completed review pass and its newly raised findings."""
    if state.status != "in_review":
        raise ValueError(f"Review is closed with status {state.status!r}")
    round_number = state.current_round + 1
    new_ids: list[str] = []
    for raw in findings or []:
        severity = str(raw.get("severity", "")).lower()
        if severity not in SEVERITIES:
            raise ValueError(f"Invalid severity: {raw.get('severity')!r}")
        finding_id = f"F{len(state.findings) + 1:03d}"
        state.findings.append(Finding(
            finding_id=finding_id,
            severity=severity,
            category=str(raw.get("category", "correctness")),
            location=str(raw.get("location", "")),
            summary=str(raw.get("summary", "")),
            recommendation=str(raw.get("recommendation", "")),
            opened_round=round_number,
        ))
        new_ids.append(finding_id)
    state.rounds.append(ReviewRound(
        round=round_number,
        reviewer=reviewer,
        new_finding_ids=new_ids,
        notes=notes,
    ))
    state.updated_at = now_iso()
    _settle(state)
    return state


def resolve_finding(state: ReviewState, finding_id: str, *, resolution: str) -> ReviewState:
    if not resolution.strip():
        raise ValueError("resolution must describe the concrete fix")
    finding = state.finding(finding_id)
    if finding.status != "open":
        raise ValueError(f"Finding {finding_id} is already {finding.status}")
    finding.status = "resolved"
    finding.closed_round = state.current_round
    finding.resolution = resolution
    state.updated_at = now_iso()
    return state


def waive_finding(
        state: ReviewState,
        finding_id: str,
        *,
        reason: str,
        human_approved: bool = False,
) -> ReviewState:
    """Waive a finding. Blocker/major waivers require a human decision."""
    if not reason.strip():
        raise ValueError("waive reason is required")
    finding = state.finding(finding_id)
    if finding.status != "open":
        raise ValueError(f"Finding {finding_id} is already {finding.status}")
    if finding.severity in BLOCKING_SEVERITIES and not human_approved:
        raise PermissionError(
            f"Finding {finding_id} is severity={finding.severity}; waiving it requires an explicit human decision"
        )
    finding.status = "waived"
    finding.closed_round = state.current_round
    finding.resolution = reason
    finding.waived_by_human = human_approved
    state.updated_at = now_iso()
    _settle(state)
    return state


def compute_verdict(state: ReviewState) -> str:
    """Pure verdict function; never mutates state."""
    if state.status == "approved":
        return "approve"
    if state.status == "escalated":
        return "escalate"
    if not state.rounds:
        return "revise"
    if state.open_blocking():
        if state.current_round >= state.max_rounds:
            return "escalate"
        return "revise"
    clean_tail = 0
    for completed in reversed(state.rounds):
        new_blocking = [
            fid for fid in completed.new_finding_ids
            if state.finding(fid).severity in BLOCKING_SEVERITIES
        ]
        if new_blocking:
            break
        clean_tail += 1
    if clean_tail >= state.clean_rounds_required:
        return "approve"
    if state.current_round >= state.max_rounds:
        return "escalate"
    return "revise"


# -- persistence -----------------------------------------------------------


def read_review(path: str | Path) -> ReviewState:
    return ReviewState.from_dict(json.loads(Path(path).read_text(encoding="utf-8")))


def collect_review_gates(evolve_dir: str | Path) -> dict[str, dict[str, Any]]:
    """Scan an evolution run dir for every review ledger and its verdict.

    Returns ``{gate_key: {target_kind, target_ref, status, verdict, path}}``
    where gate_key is ``run:<target>`` for run-level reviews under
    ``reviews/`` and ``node:<node_id>`` for candidate reviews under
    ``nodes/<node_id>/review/``.
    """
    evolve_dir = Path(evolve_dir)
    gates: dict[str, dict[str, Any]] = {}

    def register(key: str, path: Path) -> None:
        state = read_review(path)
        gates[key] = {
            "target_kind": state.target_kind,
            "target_ref": state.target_ref,
            "status": state.status,
            "verdict": compute_verdict(state),
            "round": state.current_round,
            "open_blocking": [f.finding_id for f in state.open_blocking()],
            "path": str(path.relative_to(evolve_dir)),
        }

    for path in sorted((evolve_dir / "reviews").glob("*/review-state.json")):
        register(f"run:{path.parent.name}", path)
    for path in sorted((evolve_dir / "nodes").glob("*/review/review-state.json")):
        register(f"node:{path.parent.parent.name}", path)
    return gates


def candidate_gate_blockers(evolve_dir: str | Path) -> list[str]:
    """Gate keys of candidate nodes whose review is not approved.

    A node without any review ledger is itself a blocker: evaluation budget
    must not be spent on unreviewed candidates.
    """
    evolve_dir = Path(evolve_dir)
    gates = collect_review_gates(evolve_dir)
    blockers: list[str] = []
    nodes_root = evolve_dir / "nodes"
    if nodes_root.exists():
        for node_dir in sorted(p for p in nodes_root.iterdir() if p.is_dir()):
            key = f"node:{node_dir.name}"
            gate = gates.get(key)
            if gate is None:
                blockers.append(f"{key} (no review ledger)")
            elif gate["verdict"] != "approve":
                blockers.append(f"{key} (verdict={gate['verdict']})")
    return blockers


def write_review(path: str | Path, state: ReviewState) -> Path:
    state.updated_at = now_iso()
    return write_json(path, state.to_dict())


def _settle(state: ReviewState) -> None:
    verdict = compute_verdict(state)
    if verdict == "approve":
        state.status = "approved"
    elif verdict == "escalate":
        state.status = "escalated"
        if not state.escalation_reason:
            open_blocking = ", ".join(f.finding_id for f in state.open_blocking()) or "none"
            state.escalation_reason = (
                f"max_rounds={state.max_rounds} reached with open blocking findings: {open_blocking}"
            )

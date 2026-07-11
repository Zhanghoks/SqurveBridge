"""Run-level state machine for Meta-Evo."""

from __future__ import annotations

import fnmatch
import json
from dataclasses import asdict, dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Literal

from reproduce.metrics.evolution_pkg.process_artifacts import (
    append_process_event,
    now_iso,
    render_progress,
    sha256_file,
    update_artifact_manifest,
    write_json,
)


class EvolvePhase(str, Enum):
    INITIALIZED = "initialized"
    BASELINE_LOADED = "baseline_loaded"
    WEAKNESS_PROFILED = "weakness_profiled"
    ACTIONS_GENERATED = "actions_generated"
    SMOKE_RUNNING = "smoke_running"
    SMOKE_PROMOTED = "smoke_promoted"
    BOUNDED_RUNNING = "bounded_running"
    BOUNDED_PROMOTED = "bounded_promoted"
    FULL_CONFIRMING = "full_confirming"
    REVIEW_PENDING = "review_pending"
    ACCEPTED = "accepted"
    CONTINUED = "continued"
    ROLLED_BACK = "rolled_back"
    STOPPED = "stopped"
    FAILED = "failed"


TERMINAL_PHASES = {
    EvolvePhase.ACCEPTED,
    EvolvePhase.ROLLED_BACK,
    EvolvePhase.STOPPED,
    EvolvePhase.FAILED,
}


VALID_TRANSITIONS = {
    EvolvePhase.INITIALIZED: {EvolvePhase.BASELINE_LOADED, EvolvePhase.ACTIONS_GENERATED, EvolvePhase.FAILED},
    EvolvePhase.BASELINE_LOADED: {EvolvePhase.WEAKNESS_PROFILED, EvolvePhase.FAILED},
    EvolvePhase.WEAKNESS_PROFILED: {EvolvePhase.ACTIONS_GENERATED, EvolvePhase.FAILED},
    EvolvePhase.ACTIONS_GENERATED: {EvolvePhase.SMOKE_RUNNING, EvolvePhase.STOPPED, EvolvePhase.FAILED},
    EvolvePhase.SMOKE_RUNNING: {EvolvePhase.SMOKE_PROMOTED, EvolvePhase.STOPPED, EvolvePhase.FAILED},
    EvolvePhase.SMOKE_PROMOTED: {EvolvePhase.BOUNDED_RUNNING, EvolvePhase.STOPPED, EvolvePhase.FAILED},
    EvolvePhase.BOUNDED_RUNNING: {EvolvePhase.BOUNDED_PROMOTED, EvolvePhase.STOPPED, EvolvePhase.FAILED},
    EvolvePhase.BOUNDED_PROMOTED: {EvolvePhase.FULL_CONFIRMING, EvolvePhase.REVIEW_PENDING, EvolvePhase.FAILED},
    EvolvePhase.FULL_CONFIRMING: {EvolvePhase.REVIEW_PENDING, EvolvePhase.FAILED},
    EvolvePhase.REVIEW_PENDING: {
        EvolvePhase.ACCEPTED,
        EvolvePhase.CONTINUED,
        EvolvePhase.ROLLED_BACK,
        EvolvePhase.FAILED,
    },
    EvolvePhase.CONTINUED: {EvolvePhase.ACTIONS_GENERATED, EvolvePhase.FAILED},
}


@dataclass
class EvolveState:
    version: int
    slug: str
    phase: EvolvePhase
    round: int = 0
    active_stage: str | None = None
    current_node: str | None = None
    policy: str = "bounded_search_default"
    baseline_run_slug: str | None = None
    method: str | None = None
    benchmark: str | None = None
    budget: dict[str, Any] = field(default_factory=dict)
    last_transition: dict[str, Any] | None = None
    human_gate: dict[str, Any] | None = None
    failure: dict[str, Any] | None = None
    created_at: str = field(default_factory=now_iso)
    updated_at: str = field(default_factory=now_iso)

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["phase"] = self.phase.value
        return payload

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "EvolveState":
        return cls(
            version=int(data.get("version", 1)),
            slug=str(data.get("slug") or data.get("evolve_slug")),
            phase=EvolvePhase(str(data.get("phase") or data.get("status") or EvolvePhase.INITIALIZED.value)),
            round=int(data.get("round", 0)),
            active_stage=data.get("active_stage"),
            current_node=data.get("current_node"),
            policy=str(data.get("policy", "bounded_search_default")),
            baseline_run_slug=data.get("baseline_run_slug"),
            method=data.get("method"),
            benchmark=data.get("benchmark"),
            budget=dict(data.get("budget") or {}),
            last_transition=data.get("last_transition"),
            human_gate=data.get("human_gate"),
            failure=data.get("failure"),
            created_at=str(data.get("created_at") or now_iso()),
            updated_at=str(data.get("updated_at") or now_iso()),
        )


def initialize_state(
        *,
        slug: str,
        baseline_run_slug: str | None = None,
        method: str | None = None,
        benchmark: str | None = None,
        policy: str = "bounded_search_default",
        budget: dict[str, Any] | None = None,
) -> EvolveState:
    return EvolveState(
        version=1,
        slug=slug,
        phase=EvolvePhase.INITIALIZED,
        baseline_run_slug=baseline_run_slug,
        method=method,
        benchmark=benchmark,
        policy=policy,
        budget=budget or {},
    )


def read_state(path: str | Path) -> EvolveState:
    return EvolveState.from_dict(json.loads(Path(path).read_text(encoding="utf-8")))


def write_state(path: str | Path, state: EvolveState) -> Path:
    state.updated_at = now_iso()
    return write_json(path, state.to_dict())


def transition(
        state: EvolveState,
        to_phase: EvolvePhase | str,
        *,
        reason: str,
        artifact_refs: list[str] | None = None,
        journal_path: str | Path | None = None,
        transition_id: str | None = None,
        active_stage: str | None = None,
        current_node: str | None = None,
        failure: dict[str, Any] | None = None,
) -> EvolveState:
    to_phase = to_phase if isinstance(to_phase, EvolvePhase) else EvolvePhase(str(to_phase))
    if state.phase == to_phase and transition_id:
        last = state.last_transition or {}
        if last.get("transition_id") == transition_id:
            return state
    allowed = VALID_TRANSITIONS.get(state.phase, set())
    if to_phase not in allowed:
        raise ValueError(f"Invalid evolution transition: {state.phase.value} -> {to_phase.value}")
    refs = artifact_refs or []
    state.last_transition = {
        "transition_id": transition_id or _transition_id(state, to_phase),
        "from": state.phase.value,
        "to": to_phase.value,
        "round": state.round,
        "stage": active_stage or state.active_stage,
        "reason": reason,
        "artifact_refs": refs,
        "journal_fingerprint": _fingerprint(journal_path),
        "stage_artifact_fingerprints": _artifact_fingerprints(refs, base_path=Path(journal_path).parent if journal_path else None),
        "at": now_iso(),
    }
    state.phase = to_phase
    state.active_stage = active_stage
    if current_node is not None:
        state.current_node = current_node
    state.failure = failure
    return state


def transition_evolve_dir(
        evolve_dir: str | Path,
        to_phase: EvolvePhase | str,
        *,
        reason: str,
        artifact_refs: list[str] | None = None,
        active_stage: str | None = None,
        current_node: str | None = None,
        failure: dict[str, Any] | None = None,
        kind: str = "state",
        producer: str = "state_machine.transition",
) -> EvolveState:
    evolve_dir = Path(evolve_dir)
    state_path = evolve_dir / "evolve-state.json"
    journal_path = evolve_dir / "journal.json"
    state = read_state(state_path)
    state = transition(
        state,
        to_phase,
        reason=reason,
        artifact_refs=artifact_refs or ["journal.json"],
        journal_path=journal_path,
        active_stage=active_stage,
        current_node=current_node,
        failure=failure,
    )
    write_state(state_path, state)
    append_process_event(evolve_dir, {
        "event_id": state.last_transition["transition_id"],
        "type": "transition",
        "phase": state.phase.value,
        "round": state.round,
        "stage": state.active_stage,
        "node_id": state.current_node,
        "producer": producer,
        "inputs": ["journal.json"],
        "outputs": artifact_refs or ["evolve-state.json"],
        "status": "completed",
    })
    update_artifact_manifest(
        evolve_dir,
        ["evolve-state.json", *(artifact_refs or [])],
        kind=kind,
        phase=state.phase.value,
        round=state.round,
        producer=producer,
    )
    render_progress(evolve_dir)
    return state


def next_resume_action(
        state: EvolveState,
        journal: Any,
) -> Literal["run_smoke", "run_bounded", "run_full", "reconcile_review", "await_review", "stop"]:
    phase = state.phase
    if phase in {EvolvePhase.INITIALIZED, EvolvePhase.BASELINE_LOADED, EvolvePhase.WEAKNESS_PROFILED}:
        return "run_smoke"
    if phase == EvolvePhase.ACTIONS_GENERATED:
        return "run_smoke"
    if phase == EvolvePhase.SMOKE_RUNNING:
        return "run_bounded" if _has_smoke_promoted(journal) else "run_smoke"
    if phase == EvolvePhase.SMOKE_PROMOTED:
        return "run_bounded"
    if phase == EvolvePhase.BOUNDED_RUNNING:
        return "run_full" if _has_bounded_promoted(journal) else "run_bounded"
    if phase == EvolvePhase.BOUNDED_PROMOTED:
        return "run_full"
    if phase == EvolvePhase.FULL_CONFIRMING:
        return "reconcile_review"
    if phase == EvolvePhase.REVIEW_PENDING:
        return "await_review"
    return "stop"


def assert_resume_consistency(state: EvolveState, journal: Any) -> None:
    if state.phase == EvolvePhase.FULL_CONFIRMING and state.current_node and journal.best_node:
        if state.current_node != journal.best_node:
            raise ValueError("full_confirming current_node does not match journal.best_node")
    if state.phase == EvolvePhase.REVIEW_PENDING and not journal.best_node:
        raise ValueError("review_pending requires journal.best_node")


def classify_scope_c(action: Any) -> dict[str, Any] | None:
    paths = [str((patch or {}).get("path", "")) for patch in getattr(action, "patches", [])]
    matched = [path for path in paths if is_scope_c_path(path)]
    if str(getattr(action, "scope", "")).upper() == "C" or matched:
        return {
            "reason": "scope_c_change",
            "action_id": getattr(action, "action_id", None),
            "paths": matched,
            "required_decision": "approve_scope_c",
        }
    return None


def is_scope_c_path(path: str) -> bool:
    normalized = path.replace("\\", "/")
    patterns = [
        "core/**",
        "**/engine/**",
        "**/*engine*.py",
        "**/router/**",
        "**/*router*.py",
        "**/evaluator/**",
        "**/*evaluator*.py",
        "**/dataloader/**",
        "**/*data_loader*.py",
        "**/*dataloader*.py",
        "**/*backend*.py",
    ]
    return any(fnmatch.fnmatch(normalized, pattern) for pattern in patterns)


def _has_smoke_promoted(journal: Any) -> bool:
    return any(node.promoted and node.status == "pass" and node.decision == "smoke_promoted" for node in journal.nodes)


def _has_bounded_promoted(journal: Any) -> bool:
    return any(node.promoted and node.status == "pass" and node.decision == "full_confirmation" for node in journal.nodes)


def _transition_id(state: EvolveState, to_phase: EvolvePhase) -> str:
    return f"round-{state.round}:{state.phase.value}->{to_phase.value}:{now_iso()}"


def _fingerprint(path: str | Path | None) -> str | None:
    if not path or not Path(path).exists():
        return None
    return f"sha256:{sha256_file(path)}"


def _artifact_fingerprints(refs: list[str], *, base_path: Path | None) -> dict[str, str]:
    result = {}
    if base_path is None:
        return result
    for ref in refs:
        path = Path(ref)
        full_path = path if path.is_absolute() else base_path / path
        if full_path.exists() and full_path.is_file():
            result[ref] = f"sha256:{sha256_file(full_path)}"
    return result

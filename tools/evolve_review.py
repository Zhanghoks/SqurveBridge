#!/usr/bin/env python3
"""Thin CLI over reproduce.evolve.review for the evolve-review loop.

Every command prints a machine-readable JSON summary on stdout so the
agent can branch on ``verdict`` without parsing prose:

    python3 tools/evolve_review.py open --state <review-state.json> \
        --target-kind change-plan --target-ref nodes/n001/change-plan.md
    python3 tools/evolve_review.py record-round --state <path> \
        --reviewer agent:critic --findings findings.json
    python3 tools/evolve_review.py resolve --state <path> --finding F001 \
        --resolution "..."
    python3 tools/evolve_review.py waive --state <path> --finding F002 \
        --reason "..." [--human-approved]
    python3 tools/evolve_review.py verdict --state <path>

``--evolve-dir`` (optional, any command) appends the action to
``process-events.jsonl`` and the artifact manifest of that run.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from reproduce.evolve.process_artifacts import append_process_event, update_artifact_manifest
from reproduce.evolve.review import (
    compute_verdict,
    open_review,
    read_review,
    record_round,
    resolve_finding,
    waive_finding,
    write_review,
)


def _summary(state) -> dict:
    return {
        "target_kind": state.target_kind,
        "target_ref": state.target_ref,
        "status": state.status,
        "verdict": compute_verdict(state),
        "round": state.current_round,
        "max_rounds": state.max_rounds,
        "open_blocking": [f.finding_id for f in state.open_blocking()],
        "open_findings": [f.finding_id for f in state.open_findings()],
        "escalation_reason": state.escalation_reason,
    }


def _emit(state, args, *, event_type: str) -> None:
    write_review(args.state, state)
    if getattr(args, "evolve_dir", None):
        append_process_event(args.evolve_dir, {
            "type": event_type,
            "producer": "tools/evolve_review.py",
            "target_kind": state.target_kind,
            "target_ref": state.target_ref,
            "review_status": state.status,
            "review_round": state.current_round,
            "outputs": [str(args.state)],
        })
        update_artifact_manifest(
            args.evolve_dir,
            [str(args.state)],
            kind="review",
            phase=state.status,
            producer="tools/evolve_review.py",
        )
    print(json.dumps(_summary(state), ensure_ascii=False, indent=2))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)

    def common(p: argparse.ArgumentParser) -> None:
        p.add_argument("--state", required=True, help="Path to review-state.json")
        p.add_argument("--evolve-dir", default=None, help="Optional artifacts/evolve/<slug> dir for event logging")

    p_open = sub.add_parser("open", help="Open a new review loop")
    common(p_open)
    p_open.add_argument("--target-kind", required=True)
    p_open.add_argument("--target-ref", required=True)
    p_open.add_argument("--max-rounds", type=int, default=5)
    p_open.add_argument("--clean-rounds", type=int, default=1)

    p_round = sub.add_parser("record-round", help="Record one review pass and its new findings")
    common(p_round)
    p_round.add_argument("--reviewer", required=True)
    p_round.add_argument("--findings", default=None, help="JSON file: list of findings, or {\"findings\": [...]}")
    p_round.add_argument("--notes", default="")

    p_resolve = sub.add_parser("resolve", help="Mark a finding as fixed")
    common(p_resolve)
    p_resolve.add_argument("--finding", required=True)
    p_resolve.add_argument("--resolution", required=True)

    p_waive = sub.add_parser("waive", help="Waive a finding (blocker/major requires --human-approved)")
    common(p_waive)
    p_waive.add_argument("--finding", required=True)
    p_waive.add_argument("--reason", required=True)
    p_waive.add_argument("--human-approved", action="store_true")

    p_verdict = sub.add_parser("verdict", help="Print the current verdict summary")
    common(p_verdict)

    args = parser.parse_args(argv)

    if args.command == "open":
        state_path = Path(args.state)
        if state_path.exists():
            parser.error(f"{state_path} already exists; refusing to overwrite an existing review")
        state = open_review(
            target_kind=args.target_kind,
            target_ref=args.target_ref,
            max_rounds=args.max_rounds,
            clean_rounds_required=args.clean_rounds,
        )
        _emit(state, args, event_type="review_opened")
        return 0

    state = read_review(args.state)

    if args.command == "record-round":
        findings = []
        if args.findings:
            payload = json.loads(Path(args.findings).read_text(encoding="utf-8"))
            findings = payload["findings"] if isinstance(payload, dict) else payload
        state = record_round(state, reviewer=args.reviewer, findings=findings, notes=args.notes)
        _emit(state, args, event_type="review_round")
    elif args.command == "resolve":
        state = resolve_finding(state, args.finding, resolution=args.resolution)
        _emit(state, args, event_type="review_resolve")
    elif args.command == "waive":
        state = waive_finding(state, args.finding, reason=args.reason, human_approved=args.human_approved)
        _emit(state, args, event_type="review_waive")
    elif args.command == "verdict":
        print(json.dumps(_summary(state), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

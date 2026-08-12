"""Regressions for the Meta-Evo run state machine and review-gate resume."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from reproduce.evolve.review import (
    candidate_gate_blockers,
    open_review,
    record_round,
    write_review,
)
from reproduce.evolve.state_machine import (
    EvolvePhase,
    initialize_state,
    next_resume_action,
    next_step,
    transition,
    write_state,
)


class _StubJournal:
    def __init__(self, best_node=None, nodes=None):
        self.best_node = best_node
        self.nodes = nodes or []


class PhaseGraphTests(unittest.TestCase):
    def _state_at(self, phase: EvolvePhase):
        state = initialize_state(slug="evo-test")
        state.phase = phase
        return state

    def test_review_gated_path_is_valid(self):
        state = self._state_at(EvolvePhase.ACTIONS_GENERATED)
        transition(state, EvolvePhase.CANDIDATES_REVIEWED, reason="all candidate reviews approved")
        transition(state, EvolvePhase.SMOKE_RUNNING, reason="run_smoke")
        self.assertEqual(state.phase, EvolvePhase.SMOKE_RUNNING)

        state = self._state_at(EvolvePhase.FULL_CONFIRMING)
        transition(state, EvolvePhase.REPORT_REVIEWED, reason="report review approved")
        transition(state, EvolvePhase.REVIEW_PENDING, reason="hand to human")
        self.assertEqual(state.phase, EvolvePhase.REVIEW_PENDING)

    def test_legacy_direct_path_stays_valid(self):
        state = self._state_at(EvolvePhase.ACTIONS_GENERATED)
        transition(state, EvolvePhase.SMOKE_RUNNING, reason="legacy run")
        self.assertEqual(state.phase, EvolvePhase.SMOKE_RUNNING)

        state = self._state_at(EvolvePhase.FULL_CONFIRMING)
        transition(state, EvolvePhase.REVIEW_PENDING, reason="legacy run")
        self.assertEqual(state.phase, EvolvePhase.REVIEW_PENDING)

    def test_review_phases_cannot_be_skipped_backwards(self):
        state = self._state_at(EvolvePhase.CANDIDATES_REVIEWED)
        with self.assertRaises(ValueError):
            transition(state, EvolvePhase.ACTIONS_GENERATED, reason="illegal")

    def test_resume_actions_for_review_phases(self):
        journal = _StubJournal()
        state = self._state_at(EvolvePhase.CANDIDATES_REVIEWED)
        self.assertEqual(next_resume_action(state, journal), "run_smoke")
        state = self._state_at(EvolvePhase.REPORT_REVIEWED)
        self.assertEqual(next_resume_action(state, journal), "await_review")


class NextStepTests(unittest.TestCase):
    def _make_run(self, tmp: str) -> Path:
        evolve_dir = Path(tmp) / "evo-run"
        evolve_dir.mkdir()
        state = initialize_state(slug="evo-run")
        state.phase = EvolvePhase.ACTIONS_GENERATED
        write_state(evolve_dir / "evolve-state.json", state)
        (evolve_dir / "journal.json").write_text(json.dumps({
            "version": 1, "evolve_slug": "evo-run", "nodes": [], "best_node": None,
        }), encoding="utf-8")
        return evolve_dir

    def _approve_node(self, evolve_dir: Path, node_id: str) -> None:
        review = open_review(target_kind="change-plan", target_ref=f"nodes/{node_id}/change-plan.md")
        record_round(review, reviewer="subagent:critic", findings=[])
        write_review(evolve_dir / "nodes" / node_id / "review" / "review-state.json", review)

    def test_unreviewed_candidates_withhold_the_funnel(self):
        with tempfile.TemporaryDirectory() as tmp:
            evolve_dir = self._make_run(tmp)
            (evolve_dir / "nodes" / "n001_fix").mkdir(parents=True)
            step = next_step(evolve_dir)
            self.assertEqual(step["resume_action"], "run_candidate_review")
            self.assertIn("node:n001_fix (no review ledger)", step["candidate_gate_blockers"])

    def test_approved_candidates_release_the_smoke_stage(self):
        with tempfile.TemporaryDirectory() as tmp:
            evolve_dir = self._make_run(tmp)
            (evolve_dir / "nodes" / "n001_fix").mkdir(parents=True)
            self._approve_node(evolve_dir, "n001_fix")
            step = next_step(evolve_dir)
            self.assertEqual(step["resume_action"], "run_smoke")
            self.assertEqual(step["candidate_gate_blockers"], [])
            self.assertIn("--stage smoke", step["next_command"])
            self.assertEqual(step["review_gates"]["node:n001_fix"]["verdict"], "approve")

    def test_escalated_gate_forces_await_review(self):
        with tempfile.TemporaryDirectory() as tmp:
            evolve_dir = self._make_run(tmp)
            (evolve_dir / "nodes" / "n001_fix").mkdir(parents=True)
            review = open_review(target_kind="change-plan", target_ref="x", max_rounds=1)
            record_round(review, reviewer="critic", findings=[{
                "severity": "blocker", "category": "scope", "location": "patch.diff",
                "summary": "touches core", "recommendation": "narrow scope",
            }])
            write_review(evolve_dir / "nodes" / "n001_fix" / "review" / "review-state.json", review)
            step = next_step(evolve_dir)
            self.assertEqual(step["resume_action"], "await_review")
            self.assertIn("node:n001_fix", step["next_command"])

    def test_gate_blockers_report_missing_and_unapproved_nodes(self):
        with tempfile.TemporaryDirectory() as tmp:
            evolve_dir = self._make_run(tmp)
            (evolve_dir / "nodes" / "n001_ok").mkdir(parents=True)
            (evolve_dir / "nodes" / "n002_missing").mkdir(parents=True)
            self._approve_node(evolve_dir, "n001_ok")
            blockers = candidate_gate_blockers(evolve_dir)
            self.assertEqual(blockers, ["node:n002_missing (no review ledger)"])


if __name__ == "__main__":
    unittest.main()

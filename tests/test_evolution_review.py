"""Regressions for the Meta-Evo iterative review loop ledger."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from reproduce.evolve.review import (
    compute_verdict,
    open_review,
    read_review,
    record_round,
    resolve_finding,
    waive_finding,
    write_review,
)


def _finding(severity: str, summary: str = "issue") -> dict:
    return {
        "severity": severity,
        "category": "correctness",
        "location": "change-plan.md#scope",
        "summary": summary,
        "recommendation": "fix it",
    }


class VerdictTests(unittest.TestCase):
    def test_new_review_requires_a_round_before_approval(self):
        state = open_review(target_kind="change-plan", target_ref="nodes/n001/change-plan.md")
        self.assertEqual(compute_verdict(state), "revise")

    def test_clean_first_round_approves(self):
        state = open_review(target_kind="change-plan", target_ref="x")
        record_round(state, reviewer="subagent:critic", findings=[])
        self.assertEqual(state.status, "approved")
        self.assertEqual(compute_verdict(state), "approve")

    def test_blocking_finding_requires_fix_and_clean_re_review(self):
        state = open_review(target_kind="patch", target_ref="x")
        record_round(state, reviewer="subagent:critic", findings=[_finding("blocker")])
        self.assertEqual(compute_verdict(state), "revise")

        resolve_finding(state, "F001", resolution="rewrote the patch hunk")
        # Resolution alone is not approval: a clean re-review round is required.
        self.assertEqual(compute_verdict(state), "revise")

        record_round(state, reviewer="subagent:critic", findings=[])
        self.assertEqual(compute_verdict(state), "approve")

    def test_minor_findings_do_not_block_approval_but_stay_open(self):
        state = open_review(target_kind="comparison-report", target_ref="x")
        record_round(state, reviewer="agent:critic", findings=[_finding("minor"), _finding("nit")])
        self.assertEqual(compute_verdict(state), "approve")
        self.assertEqual(len(state.open_findings()), 2)

    def test_escalates_when_max_rounds_exhausted_with_open_blocker(self):
        state = open_review(target_kind="change-plan", target_ref="x", max_rounds=2)
        record_round(state, reviewer="critic", findings=[_finding("blocker")])
        record_round(state, reviewer="critic", findings=[_finding("major")])
        self.assertEqual(state.status, "escalated")
        self.assertEqual(compute_verdict(state), "escalate")
        self.assertIn("max_rounds", state.escalation_reason)

    def test_escalates_when_budget_ends_resolved_but_without_a_clean_round(self):
        # All blocking findings are resolved, yet the final round still raised
        # one, so no clean round exists when max_rounds runs out.
        state = open_review(target_kind="patch", target_ref="x", max_rounds=2)
        record_round(state, reviewer="critic", findings=[_finding("blocker")])
        resolve_finding(state, "F001", resolution="rewrote hunk")
        record_round(state, reviewer="critic", findings=[_finding("major")])
        resolve_finding(state, "F002", resolution="narrowed scope")
        self.assertEqual(compute_verdict(state), "escalate")

    def test_closed_review_rejects_new_rounds(self):
        state = open_review(target_kind="change-plan", target_ref="x")
        record_round(state, reviewer="critic", findings=[])
        with self.assertRaises(ValueError):
            record_round(state, reviewer="critic", findings=[])


class WaiverTests(unittest.TestCase):
    def test_blocker_waiver_requires_human(self):
        state = open_review(target_kind="patch", target_ref="x")
        record_round(state, reviewer="critic", findings=[_finding("blocker")])
        with self.assertRaises(PermissionError):
            waive_finding(state, "F001", reason="agent thinks it is fine")

    def test_human_approved_waiver_unblocks(self):
        state = open_review(target_kind="patch", target_ref="x")
        record_round(state, reviewer="critic", findings=[_finding("blocker")])
        waive_finding(state, "F001", reason="user accepted the risk", human_approved=True)
        self.assertTrue(state.finding("F001").waived_by_human)
        # The waiving round raised a blocking finding, so a clean re-review is still required.
        self.assertEqual(compute_verdict(state), "revise")
        record_round(state, reviewer="critic", findings=[])
        self.assertEqual(compute_verdict(state), "approve")

    def test_minor_waiver_needs_reason_only(self):
        state = open_review(target_kind="patch", target_ref="x")
        record_round(state, reviewer="critic", findings=[_finding("minor")])
        waive_finding(state, "F001", reason="cosmetic; deferred")
        self.assertEqual(state.finding("F001").status, "waived")


class PersistenceTests(unittest.TestCase):
    def test_roundtrip_preserves_ledger(self):
        state = open_review(target_kind="weakness-profile", target_ref="weakness_profile.md")
        record_round(state, reviewer="critic", findings=[_finding("major")])
        resolve_finding(state, "F001", resolution="added sample counts")
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "review-state.json"
            write_review(path, state)
            loaded = read_review(path)
        self.assertEqual(loaded.target_kind, "weakness-profile")
        self.assertEqual(loaded.finding("F001").status, "resolved")
        self.assertEqual(compute_verdict(loaded), "revise")

    def test_invalid_target_kind_rejected(self):
        with self.assertRaises(ValueError):
            open_review(target_kind="poem", target_ref="x")

    def test_invalid_severity_rejected(self):
        state = open_review(target_kind="patch", target_ref="x")
        with self.assertRaises(ValueError):
            record_round(state, reviewer="critic", findings=[_finding("catastrophic")])


class CliTests(unittest.TestCase):
    def _run(self, *argv: str) -> dict:
        proc = subprocess.run(
            [sys.executable, str(ROOT / "tools" / "evolve_review.py"), *argv],
            capture_output=True, text=True, check=True,
        )
        return json.loads(proc.stdout)

    def test_cli_full_loop(self):
        with tempfile.TemporaryDirectory() as tmp:
            state = str(Path(tmp) / "review-state.json")
            findings = Path(tmp) / "round-1-findings.json"
            findings.write_text(json.dumps({"findings": [_finding("blocker")]}), encoding="utf-8")

            out = self._run("open", "--state", state, "--target-kind", "change-plan", "--target-ref", "plan.md")
            self.assertEqual(out["verdict"], "revise")

            out = self._run("record-round", "--state", state, "--reviewer", "subagent:critic",
                            "--findings", str(findings))
            self.assertEqual(out["open_blocking"], ["F001"])

            out = self._run("resolve", "--state", state, "--finding", "F001", "--resolution", "fixed hunk")
            self.assertEqual(out["verdict"], "revise")

            out = self._run("record-round", "--state", state, "--reviewer", "subagent:critic")
            self.assertEqual(out["verdict"], "approve")
            self.assertEqual(out["status"], "approved")

    def test_cli_refuses_to_overwrite_existing_review(self):
        with tempfile.TemporaryDirectory() as tmp:
            state = str(Path(tmp) / "review-state.json")
            self._run("open", "--state", state, "--target-kind", "patch", "--target-ref", "p.diff")
            proc = subprocess.run(
                [sys.executable, str(ROOT / "tools" / "evolve_review.py"),
                 "open", "--state", state, "--target-kind", "patch", "--target-ref", "p.diff"],
                capture_output=True, text=True,
            )
            self.assertNotEqual(proc.returncode, 0)


if __name__ == "__main__":
    unittest.main()

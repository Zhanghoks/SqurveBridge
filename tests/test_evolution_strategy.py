# Regressions for the Meta-Evo strategy upgrades: cumulative action chains,
# baseline-centered rewards, promotion gating, experience warm-starts,
# stagnation semantics, and executable-action pool filtering.

import json
import tempfile
import unittest
from pathlib import Path

from reproduce.evolve.artifacts import init_evolve_dir, record_user_review, write_json
from reproduce.evolve.budget import smoke_gate_promote
from reproduce.evolve.experience import (
    action_priors_from_journal,
    failed_action_ids_from_memory,
)
from reproduce.evolve.fitness import R_INVALID, improvement_from_scores
from reproduce.evolve.journal import EvolutionJournal
from reproduce.evolve.node import EvolutionNode
from reproduce.evolve.mcts.expand import Action, combine_actions, filter_executable, generate_actions
from reproduce.evolve.mcts.orchestrator import run_bounded_funnel, run_search
from reproduce.evolve.mcts.tree import ActionStats, warm_start_action_stats


def _action(action_id: str, *, target_metric: str = "ex", patches=None) -> Action:
    return Action(
        action_id=action_id,
        description=f"candidate {action_id}",
        target_metric=target_metric,
        scope="B",
        risk="low",
        patches=patches if patches is not None else [{"path": "x.py", "old_string": "a", "new_string": "b"}],
    )


def _bundle(ex: float, *, tokens: int = 1000) -> dict:
    return {
        "run_id": f"run-{ex}",
        "sample_count": 2,
        "aggregate": {
            "ex": {"avg": ex},
            "em": {"avg": 0.0},
            "ves": {"avg": 0.0},
            "token": {"total_tokens": tokens},
        },
        "by_hardness": {"hard": {"ex": ex}},
        "per_sample": [
            {"instance_id": f"s{index}", "ex": 1, "act_elapsed_s": 1.0}
            for index in range(2)
        ],
    }


class BaselineCenteredRewardTests(unittest.TestCase):
    def test_noop_candidate_scores_zero(self):
        baseline = _bundle(0.5)
        self.assertEqual(improvement_from_scores(_bundle(0.5), baseline), 0.0)

    def test_improvement_is_positive_and_regression_negative(self):
        baseline = _bundle(0.5)
        self.assertGreater(improvement_from_scores(_bundle(0.6), baseline), 0.0)
        self.assertLess(improvement_from_scores(_bundle(0.4), baseline), 0.0)

    def test_invalid_reward_stays_below_worst_valid_improvement(self):
        # Worst candidate fitness (-0.30) minus best baseline fitness (0.85).
        self.assertLess(R_INVALID, -1.15)

    def test_target_metric_bonus_is_proportional(self):
        baseline = _bundle(0.5)
        improved = _bundle(0.6)

        def simulator(action, _iteration):
            return {"score": 0.6, "scores": improved}

        with_bonus = run_search(
            actions=[_action("a", target_metric="ex")],
            rollouts=1,
            simulator=simulator,
            baseline_score=0.5,
            baseline_scores=baseline,
            target_bonus_weight=0.15,
        )
        without_bonus = run_search(
            actions=[_action("a", target_metric="ex")],
            rollouts=1,
            simulator=simulator,
            baseline_score=0.5,
            baseline_scores=baseline,
            target_bonus_weight=0.0,
        )

        self.assertAlmostEqual(
            with_bonus["best_reward"] - without_bonus["best_reward"],
            0.15 * 0.1,
            places=6,
        )


class PromotionGateTests(unittest.TestCase):
    def _node(self, node_id: str, fitness: float | None, status: str = "pass") -> EvolutionNode:
        return EvolutionNode(node_id=node_id, branch_id=1, fitness=fitness, status=status)

    def test_zero_improvement_is_not_promoted(self):
        nodes = [self._node("noop", 0.0), self._node("win", 0.2)]

        promoted = smoke_gate_promote(nodes, promote_top_k=2)

        self.assertEqual([node.node_id for node in promoted], ["win"])
        self.assertFalse(nodes[0].promoted)

    def test_negative_improvement_is_not_promoted(self):
        nodes = [self._node("worse", -0.1)]
        self.assertEqual(smoke_gate_promote(nodes, promote_top_k=1), [])

    def test_cost_only_improvement_is_promoted(self):
        # A candidate that holds EX but cuts cost has a small positive reward.
        nodes = [self._node("cheaper", 0.02)]
        self.assertEqual([n.node_id for n in smoke_gate_promote(nodes)], ["cheaper"])


class ExecutablePoolTests(unittest.TestCase):
    def test_heuristic_templates_are_not_executable(self):
        templates = generate_actions("join predicate schema weakness")
        executable, skipped = filter_executable(templates)

        self.assertEqual(executable, [])
        self.assertEqual(len(skipped), len(templates))

    def test_actions_with_patches_or_commands_pass_the_filter(self):
        pool = [
            _action("patched"),
            Action("cmd-only", "runs a config flag", "ex", "B", "low", patches=[], run_command="run.sh"),
            Action("empty", "outline only", "ex", "B", "low", patches=[]),
        ]

        executable, skipped = filter_executable(pool)

        self.assertEqual([action.action_id for action in executable], ["patched", "cmd-only"])
        self.assertEqual(skipped, ["empty"])

    def test_funnel_filters_non_executable_actions_at_pool_load(self):
        evaluated = []

        def simulator(action, _iteration):
            evaluated.append(action.action_id)
            return 0.6

        result = run_bounded_funnel(
            actions=[_action("patched"), Action("empty", "outline only", "ex", "B", "low", patches=[])],
            smoke_simulator=simulator,
            baseline_score=0.5,
            smoke_rollouts=4,
        )

        self.assertEqual(result["skipped_no_patch"], ["empty"])
        self.assertNotIn("empty", evaluated)


class CumulativeChainTests(unittest.TestCase):
    def test_combine_actions_merges_patches_in_chain_order(self):
        first = _action("a", patches=[{"path": "x.py", "old_string": "1", "new_string": "2"}])
        second = _action("b", patches=[{"path": "y.py", "old_string": "3", "new_string": "4"}])

        composite = combine_actions([first, second])

        self.assertEqual(composite.action_id, "a+b")
        self.assertEqual([patch["path"] for patch in composite.patches], ["x.py", "y.py"])

    def test_chains_only_stack_verified_actions(self):
        baseline = _bundle(0.5)
        bundles = {
            "good": _bundle(0.6),   # CONTINUE -> verified
            "flat": _bundle(0.5),   # DRY -> never verified
        }
        evaluated = []

        def simulator(action, _iteration):
            evaluated.append(action.action_id)
            bundle = bundles.get(action.action_id, _bundle(0.62))
            return {"score": bundle["aggregate"]["ex"]["avg"], "scores": bundle}

        run_search(
            actions=[_action("good"), _action("flat")],
            rollouts=8,
            simulator=simulator,
            baseline_score=0.5,
            baseline_scores=baseline,
            cumulative_updates=True,
        )

        chain_ids = [action_id for action_id in evaluated if "+" in action_id]
        for chain_id in chain_ids:
            self.assertNotIn("flat", chain_id.split("+")[1:],
                             "an unverified (DRY) action must never be stacked onto a chain")

    def test_chain_depth_is_capped(self):
        baseline = _bundle(0.5)
        counter = iter(range(100))

        def simulator(action, _iteration):
            # Every evaluation improves, so every action gets verified and
            # chains keep growing until the depth cap stops them.
            bundle = _bundle(0.6 + 0.001 * next(counter))
            return {"score": bundle["aggregate"]["ex"]["avg"], "scores": bundle}

        result = run_search(
            actions=[_action(f"a{i}") for i in range(6)],
            rollouts=24,
            simulator=simulator,
            baseline_score=0.5,
            baseline_scores=baseline,
            cumulative_updates=True,
            max_chain_depth=2,
            dry_round_limit=100,
        )

        def max_depth(node, depth=0):
            children = node.get("children") or []
            return max([depth] + [max_depth(child, depth + 1) for child in children])

        self.assertLessEqual(max_depth(result["tree"]), 2)

    def test_memo_hits_do_not_inflate_visits(self):
        calls = []

        def simulator(action, _iteration):
            calls.append(action.action_id)
            return 0.5

        result = run_search(
            actions=[_action("a")],
            rollouts=6,
            simulator=simulator,
            baseline_score=0.0,
        )

        self.assertEqual(calls, ["a"])
        self.assertEqual(result["evaluations"], 1)
        self.assertEqual(result["tree"]["visits"], 1)

    def test_cross_branch_memo_hits_do_not_count_as_evaluations(self):
        # In non-cumulative mode the same leaf action reached via another
        # branch shares its rollout; reusing it must not spend budget.
        calls = []

        def simulator(action, _iteration):
            calls.append(action.action_id)
            return 0.6

        result = run_search(
            actions=[_action("a"), _action("b")],
            rollouts=8,
            simulator=simulator,
            baseline_score=0.5,
            cumulative_updates=False,
        )

        self.assertEqual(sorted(calls), ["a", "b"])
        self.assertEqual(result["evaluations"], 2)


class ExperienceWarmStartTests(unittest.TestCase):
    def _journal_payload(self) -> dict:
        return {
            "evolve_slug": "past",
            "nodes": [
                {
                    "node_id": "node-1",
                    "status": "buggy",
                    "fitness": -0.5,
                    "delta": {"verdict": "REGRESSION"},
                    "metadata": {"action": {"action_id": "bad"}},
                },
                {
                    "node_id": "node-2",
                    "status": "pass",
                    "fitness": 0.3,
                    "decision": "smoke_promoted",
                    "delta": {"verdict": "CONTINUE"},
                    "metadata": {"action": {"action_id": "promising"}},
                },
            ],
        }

    def test_priors_classify_failures_and_successes(self):
        priors = action_priors_from_journal(self._journal_payload())

        by_id = {prior.action_id: prior for prior in priors}
        self.assertTrue(by_id["bad"].failed)
        self.assertFalse(by_id["promising"].failed)

    def test_warm_start_downweights_failures_without_excluding_them(self):
        stats: dict[str, ActionStats] = {}
        priors = action_priors_from_journal(self._journal_payload())

        warm_start_action_stats(stats, priors, discount=0.3, failed_reward=-1.0)

        self.assertAlmostEqual(stats["bad"].visits, 0.3)
        self.assertLess(stats["bad"].average_reward, stats["promising"].average_reward)

    def test_fresh_actions_are_tried_before_previously_failed_ones(self):
        order = []

        def simulator(action, _iteration):
            order.append(action.action_id)
            return 0.5

        run_search(
            actions=[_action("bad"), _action("fresh")],
            rollouts=2,
            simulator=simulator,
            baseline_score=0.0,
            prior_journals=[self._journal_payload()],
        )

        self.assertEqual(order[0], "fresh",
                         "a previously failed action must not outrank an untried one")

    def test_review_outcomes_land_in_experience_memory(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "evolve"
            evolve_dir = init_evolve_dir("demo-slug", artifacts_root=root)
            journal = EvolutionJournal.read(evolve_dir / "journal.json")
            journal.add_node(EvolutionNode(
                node_id="node-1",
                branch_id=1,
                fitness=0.2,
                status="pass",
                metadata={"action": {"action_id": "fix-joins"}},
            ))
            journal.write(evolve_dir / "journal.json")

            record_user_review(evolve_dir, recommendation="adopt", outcome="rollback", best_node_id="node-1")

            memory = root / "evolution-memory.md"
            self.assertIn("Failed Patterns", memory.read_text(encoding="utf-8"))
            self.assertEqual(failed_action_ids_from_memory(memory), {"fix-joins"})

            record_user_review(evolve_dir, recommendation="adopt", outcome="accept", best_node_id="node-1")
            self.assertIn("Successful Patterns", memory.read_text(encoding="utf-8"))


class StagnationTests(unittest.TestCase):
    def test_dry_rounds_count_fresh_evaluations_not_loop_turns(self):
        with tempfile.TemporaryDirectory() as tmp:
            journal_path = Path(tmp) / "journal.json"
            EvolutionJournal(evolve_slug="stagnation-test").write(journal_path)
            baseline = _bundle(0.5)

            def simulator(action, _iteration):
                # Every candidate reproduces the baseline: zero improvement.
                return {"score": 0.5, "scores": _bundle(0.5)}

            result = run_search(
                actions=[_action(f"a{i}") for i in range(10)],
                rollouts=20,
                simulator=simulator,
                baseline_score=0.5,
                baseline_scores=baseline,
                journal_path=journal_path,
                dry_round_limit=2,
            )

            journal = EvolutionJournal.read(journal_path)
            # The stagnation window needs 5 scored nodes before it can fire;
            # dry rounds 1 and 2 land on evaluations 5 and 6.
            self.assertEqual(result["evaluations"], 6)
            self.assertEqual(journal.stagnation["dry_rounds"], 2)

    def test_stagnant_branches_are_pruned_from_selection(self):
        with tempfile.TemporaryDirectory() as tmp:
            journal_path = Path(tmp) / "journal.json"
            journal = EvolutionJournal(evolve_slug="prune-test")
            journal.stagnation["branch_stagnant"] = [1]
            journal.write(journal_path)
            baseline = _bundle(0.5)
            counter = iter(range(100))

            def simulator(action, _iteration):
                bundle = _bundle(0.6 + 0.001 * next(counter))
                return {"score": bundle["aggregate"]["ex"]["avg"], "scores": bundle}

            result = run_search(
                actions=[_action("a"), _action("b"), _action("c")],
                rollouts=6,
                simulator=simulator,
                baseline_score=0.5,
                baseline_scores=baseline,
                journal_path=journal_path,
                dry_round_limit=100,
            )

            # Branch 1 is the first root child; with branch 2 available, deeper
            # expansion must happen outside the stagnant branch.
            children = result["tree"]["children"]
            branch_one = [child for child in children if child["branch_id"] == 1]
            self.assertTrue(branch_one)
            self.assertEqual(branch_one[0]["children"], [])


if __name__ == "__main__":
    unittest.main()

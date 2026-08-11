# Regressions for the Meta-Evo bounded search loop and its fitness signal.

import unittest

from reproduce.eval.bundle.compare import compare_scores
from reproduce.evolve.fitness import (
    DEFAULT_WEIGHTS,
    R_INVALID,
    compute_fitness,
    fitness_from_scores,
)
from reproduce.evolve.mcts.expand import Action
from reproduce.evolve.mcts.orchestrator import run_search
from reproduce.evolve.mcts.tree import (
    ActionStats,
    TreeNode,
    add_child,
    ancestor_action_ids,
    record_action_result,
    select_action,
)


def _action(action_id: str, target_metric: str = "ex") -> Action:
    return Action(
        action_id=action_id,
        description=f"candidate {action_id}",
        target_metric=target_metric,
        scope="B",
        risk="low",
    )


def _scores(ex: float, *, em: float = 0.0, ves: float = 0.0, tokens: int = 1000,
            latency: float = 1.0, per_sample_ex=(1, 1)) -> dict:
    return {
        "run_id": f"run-{ex}",
        "sample_count": len(per_sample_ex),
        "aggregate": {
            "ex": {"avg": ex},
            "em": {"avg": em},
            "ves": {"avg": ves},
            "token": {"total_tokens": tokens},
        },
        "by_hardness": {"hard": {"ex": ex}},
        "per_sample": [
            {"instance_id": f"s{index}", "ex": value, "act_elapsed_s": latency}
            for index, value in enumerate(per_sample_ex)
        ],
    }


class FitnessTests(unittest.TestCase):
    def test_all_weighted_terms_contribute(self):
        quality_only = compute_fitness(ex=1.0)
        full = compute_fitness(ex=1.0, em=1.0, ves=1.0, hard_slice_score=1.0)

        self.assertAlmostEqual(quality_only, DEFAULT_WEIGHTS["ex"])
        self.assertAlmostEqual(
            full,
            DEFAULT_WEIGHTS["ex"] + DEFAULT_WEIGHTS["em"] + DEFAULT_WEIGHTS["ves"] + DEFAULT_WEIGHTS["hard_slice"],
        )

    def test_regression_penalty_lowers_reward(self):
        clean = compute_fitness(ex=0.8, regression_rate=0.0)
        regressed = compute_fitness(ex=0.8, regression_rate=1.0)

        self.assertAlmostEqual(clean - regressed, DEFAULT_WEIGHTS["regression"])

    def test_cost_delta_is_relative_and_does_not_saturate(self):
        baseline = _scores(0.5, tokens=100_000)
        candidate = _scores(0.5, tokens=105_000)

        delta = compare_scores(baseline, candidate)
        fitness = fitness_from_scores(candidate, delta=delta)
        without_cost = fitness_from_scores(candidate, delta={})

        # A 5% token increase must cost 5% of the cost weight, not all of it.
        self.assertAlmostEqual(without_cost - fitness, DEFAULT_WEIGHTS["cost"] * 0.05, places=6)

    def test_latency_delta_reaches_the_fitness(self):
        baseline = _scores(0.5, latency=2.0)
        candidate = _scores(0.5, latency=1.0)

        delta = compare_scores(baseline, candidate)
        self.assertAlmostEqual(delta["metrics"]["latency_avg"]["delta"], -1.0)

        improved = fitness_from_scores(candidate, delta=delta)
        neutral = fitness_from_scores(candidate, delta={})
        self.assertGreater(improved, neutral)

    def test_per_sample_regressions_feed_the_fitness(self):
        baseline = _scores(1.0, per_sample_ex=(1, 1))
        candidate = _scores(0.5, per_sample_ex=(1, 0))

        delta = compare_scores(baseline, candidate)
        self.assertEqual(delta["regressions"]["ex"], ["s1"])

        penalised = fitness_from_scores(candidate, delta=delta)
        unpenalised = fitness_from_scores(candidate, delta={})
        self.assertAlmostEqual(unpenalised - penalised, DEFAULT_WEIGHTS["regression"] * 0.5, places=6)

    def test_invalid_reward_is_below_the_worst_valid_fitness(self):
        worst_valid = compute_fitness(
            ex=0.0, em=0.0, ves=0.0, hard_slice_score=0.0,
            cost_delta=1.0, latency_delta=1.0, regression_rate=1.0,
        )
        self.assertLess(R_INVALID, worst_valid)


class ActionSelectionTests(unittest.TestCase):
    def test_untried_actions_are_sampled_before_any_repeat(self):
        stats: dict[str, ActionStats] = {}
        actions = [_action("a"), _action("b")]
        record_action_result(stats, "a", 0.9)

        chosen = select_action(actions, stats, parent_visits=1)

        self.assertEqual(chosen.action_id, "b")

    def test_higher_reward_action_wins_once_all_are_tried(self):
        stats: dict[str, ActionStats] = {}
        actions = [_action("a"), _action("b")]
        for _ in range(5):
            record_action_result(stats, "a", 0.1)
            record_action_result(stats, "b", 0.9)

        chosen = select_action(actions, stats, parent_visits=10)

        self.assertEqual(chosen.action_id, "b")

    def test_ancestor_action_ids_are_ordered_root_first(self):
        root = TreeNode(node_id="root")
        nodes = {"root": root}
        first = add_child(root, "node-1", _action("a").to_dict())
        nodes["node-1"] = first
        second = add_child(first, "node-2", _action("b").to_dict())
        nodes["node-2"] = second

        self.assertEqual(ancestor_action_ids(second, nodes), ["a", "b"])


class SearchLoopTests(unittest.TestCase):
    def test_reward_not_raw_metric_drives_the_tree(self):
        # "cheap" has a lower EX but spends far fewer tokens; the multi-objective
        # reward must prefer it over the raw-metric leader.
        baseline = _scores(0.50, tokens=100_000)
        bundles = {
            "cheap": _scores(0.60, tokens=10_000),
            "greedy": _scores(0.62, tokens=1_000_000),
        }

        def simulator(action, _iteration):
            bundle = bundles[action.action_id]
            return {"score": bundle["aggregate"]["ex"]["avg"], "scores": bundle}

        result = run_search(
            actions=[_action("cheap"), _action("greedy")],
            rollouts=4,
            simulator=simulator,
            baseline_score=0.50,
            baseline_scores=baseline,
        )

        self.assertEqual([step["action_id"] for step in result["best_path"]][0], "cheap")

    def test_failed_rollout_is_penalised_not_treated_as_baseline(self):
        def simulator(action, _iteration):
            if action.action_id == "broken":
                return {"score": None, "verdict": {"verdict": "STOP", "reason": "command failed"}}
            return {"score": 0.30}

        result = run_search(
            actions=[_action("broken"), _action("weak")],
            rollouts=4,
            simulator=simulator,
            baseline_score=0.90,
        )

        # 0.30 is a regression against a 0.90 baseline, but it still ran, so it
        # must outrank the candidate that never produced a score.
        self.assertEqual([step["action_id"] for step in result["best_path"]][0], "weak")
        self.assertGreater(result["best_reward"], R_INVALID)

    def test_verdict_reports_the_raw_metric_not_the_reward(self):
        def simulator(_action, _iteration):
            return 0.75

        result = run_search(
            actions=[_action("a")],
            rollouts=2,
            simulator=simulator,
            baseline_score=0.50,
        )

        self.assertEqual(result["verdict"]["current"], 0.75)
        self.assertAlmostEqual(result["verdict"]["delta"], 0.25)

    def test_repeated_visits_reuse_the_memoized_rollout(self):
        calls = []

        def simulator(action, _iteration):
            calls.append(action.action_id)
            return 0.5

        run_search(
            actions=[_action("a")],
            rollouts=6,
            simulator=simulator,
            baseline_score=0.0,
        )

        self.assertEqual(calls, ["a"])

    def test_budget_is_spent_on_candidates_rather_than_idling(self):
        seen = []

        def simulator(action, _iteration):
            seen.append(action.action_id)
            return {"a": 0.4, "b": 0.6, "c": 0.5}[action.action_id]

        run_search(
            actions=[_action("a"), _action("b"), _action("c")],
            rollouts=8,
            simulator=simulator,
            baseline_score=0.0,
        )

        self.assertEqual(set(seen), {"a", "b", "c"})


if __name__ == "__main__":
    unittest.main()

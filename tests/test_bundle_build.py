# The registry-era bundle builder must keep the v1 contract and fix the
# known aggregation bugs (latency missing, per_call_p95 == max).

import unittest

from reproduce.eval.aggregate.statistics import percentile
from reproduce.eval.bundle.build import build_scores
from reproduce.eval.bundle.schema import validate_bundle
from reproduce.metrics.assembly import build_scores as facade_build_scores


def _rows():
    return [
        {
            "instance_id": "q0",
            "db_id": "db_a",
            "db_type": "sqlite",
            "question": "How many users are there?",
            "query": "SELECT count(*) FROM users",
            "pred_sql": "SELECT count(*) FROM users",
            "_act_elapsed_s": 1.0,
        },
        {
            "instance_id": "q1",
            "db_id": "db_a",
            "db_type": "sqlite",
            "question": "List user names.",
            "query": "SELECT name FROM users",
            "pred_sql": "SELECT id FROM users",
            "_act_elapsed_s": 3.0,
        },
    ]


def _token_data():
    records = [
        {"tag": "sample:q0|generate", "prompt_tokens": 80, "completion_tokens": 20, "total_tokens": 100},
        {"tag": "sample:q1|generate", "prompt_tokens": 80, "completion_tokens": 20, "total_tokens": 100},
        {"tag": "sample:q1|generate", "prompt_tokens": 700, "completion_tokens": 300, "total_tokens": 1000},
    ]
    return {
        "total": {"calls": 3, "prompt_tokens": 860, "completion_tokens": 340, "total_tokens": 1200},
        "by_tag": {
            "sample:q0|generate": {"calls": 1, "total_tokens": 100, "mean": 100},
            "sample:q1|generate": {"calls": 2, "total_tokens": 1100, "mean": 550},
        },
        "records": records,
    }


def _build(**overrides):
    kwargs = dict(
        run_id="test-run",
        method="demo-method",
        dataset_name="demo-bench",
        split="dev",
        generate_num=1,
        config_path="reproduce/configs/demo/demo.json",
        data_lists=[_rows()],
        ex_result={
            "avg": 0.5,
            "pass_count": 1,
            "valid": 2,
            "total": 2,
            "per_sample": [
                {"instance_id": "q0", "ex": 1, "exec_error": None},
                {"instance_id": "q1", "ex": 0, "exec_error": None},
            ],
        },
        custom_results={},
        token_data=_token_data(),
        stage_results={
            "demo_parse": {
                "task_type": "ParseTask",
                "metrics": {
                    "parse_recall": {"avg": 0.9, "valid_num": 2, "total_items": 2},
                    "parse_precision": {"avg": 0.8, "valid_num": 2, "total_items": 2},
                },
            },
        },
    )
    kwargs.update(overrides)
    return build_scores(**kwargs)


class BundleBuildTests(unittest.TestCase):
    def test_v1_contract_holds(self):
        scores = _build()
        self.assertEqual(validate_bundle(scores), [])
        self.assertEqual(scores["sample_count"], 2)
        self.assertEqual(scores["aggregate"]["ex"]["avg"], 0.5)

    def test_bernoulli_metrics_carry_wilson_intervals(self):
        ex_cell = _build()["aggregate"]["ex"]
        self.assertEqual(ex_cell["interval_kind"], "wilson95")
        low, high = ex_cell["interval"]
        self.assertLess(low, 0.5)
        self.assertGreater(high, 0.5)

    def test_gate_funnel_lands_in_aggregate(self):
        funnel = _build()["aggregate"]["funnel"]["gate"]
        self.assertEqual(
            list(funnel["survival"]), ["parseable", "timely", "executable", "correct", "efficient"])
        self.assertEqual(funnel["survival"]["correct"], 0.5)

    def test_latency_is_aggregated(self):
        latency = _build()["aggregate"]["latency"]
        self.assertEqual(latency["sample_count"], 2)
        self.assertAlmostEqual(latency["avg_s"], 2.0)
        self.assertAlmostEqual(latency["p50_s"], 2.0)
        self.assertAlmostEqual(latency["p95_s"], percentile([1.0, 3.0], 95))

    def test_per_call_p95_is_a_percentile_not_max(self):
        by_step = _build()["aggregate"]["token"]["by_step"]
        cell = by_step["generate"]
        expected = percentile([100.0, 100.0, 1000.0], 95)
        self.assertAlmostEqual(cell["per_call_p95"], expected)
        self.assertLess(cell["per_call_p95"], 1000.0)
        self.assertEqual(cell["calls"], 3)
        self.assertEqual(cell["total_tokens"], 1200)

    def test_stage_metrics_are_surfaced(self):
        stage = _build()["aggregate"]["stage"]
        self.assertIn("demo_parse", stage)
        self.assertEqual(stage["demo_parse"]["task_type"], "ParseTask")
        self.assertEqual(stage["demo_parse"]["metrics"]["parse_precision"]["avg"], 0.8)

    def test_sl_recall_aggregate_present_even_when_unavailable(self):
        aggregate = _build()["aggregate"]
        self.assertEqual(aggregate["sl_recall"]["valid"], 0)
        self.assertIsNone(aggregate["sl_recall"]["avg"])
        self.assertEqual(aggregate["sl_recall"]["total"], 2)

    def test_slices_keep_legacy_shape(self):
        scores = _build()
        self.assertEqual(list(scores["by_hardness"]), ["easy", "medium", "hard", "extra"])
        for cell in scores["by_hardness"].values():
            self.assertEqual(
                set(cell), {"count", "ex", "em", "cf1_join", "cf1_where", "error_dist"})
        self.assertIn("sqlite", scores["by_db_type"])
        self.assertEqual(set(scores["by_component_hardness"]) & {"cf1_join", "cf1_where"},
                         {"cf1_join", "cf1_where"})

    def test_error_attribution_only_over_failures(self):
        dist = _build()["aggregate"]["error_root_distribution"]
        self.assertTrue(all(entry["sample_ids"] == ["q1"] for entry in dist.values()))

    def test_facade_import_is_the_same_function(self):
        self.assertIs(facade_build_scores, build_scores)


if __name__ == "__main__":
    unittest.main()

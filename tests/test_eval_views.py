# Views regressions: publication completeness, long-table store, L6 matrix,
# and by-id fitness access.

import sqlite3
import tempfile
import unittest
from pathlib import Path

from reproduce.eval.views.evidence import (
    publication_completeness,
    sample_diagnostics,
)
from reproduce.eval.views.fitness import fitness_inputs, metric_value
from reproduce.eval.views.matrix import (
    MethodMatrix,
    disagreement,
    efficiency_headroom,
    empirical_difficulty,
    matrix_report,
    oracle_gap,
    uniquely_solved,
)
from reproduce.eval.views.store import load_sample_metric, persist_eval_store


def _bundle(run_id, method, per_sample, *, ex_avg):
    return {
        "run_id": run_id,
        "method": method,
        "dataset": "demo-bench",
        "split": "dev",
        "generate_num": 1,
        "scope": "full",
        "timestamp": f"2026-08-12T00:00:00+00:00-{run_id}",
        "sample_count": len(per_sample),
        "aggregate": {
            "ex": {"avg": ex_avg, "pass_count": sum(r["ex"] for r in per_sample),
                   "valid": len(per_sample), "total": len(per_sample)},
            "em": {"avg": 0.5, "valid": len(per_sample), "total": len(per_sample)},
            "sf1": {"avg": 0.6, "valid": len(per_sample), "total": len(per_sample)},
            "sc": {"avg": None, "valid": 0, "total": len(per_sample)},
            "ves": {"avg": 0.7, "valid": len(per_sample), "total": len(per_sample)},
            "rves": {"avg": 0.65, "valid": len(per_sample), "total": len(per_sample)},
            "cf1": {f"cf1_{c}": {"avg": 0.9} for c in
                    ("select", "where", "group", "order", "join", "iuen", "keywords")},
            "fd": {},
            "error_root_distribution": {"model_missing_join": {"count": 1, "pct": 1.0, "sample_ids": ["q1"]}},
            "pipeline": {},
            "token": {"total_calls": 2, "total_tokens": 1200, "avg_per_sample": 600},
            "latency": {"sample_count": len(per_sample), "avg_s": 2.0, "p50_s": 2.0, "p95_s": 3.0},
            "sl_recall": {"avg": 0.95, "valid": len(per_sample), "total": len(per_sample)},
        },
        "per_sample": per_sample,
    }


def _row(qid, ex, elapsed, *, error_root=None):
    return {
        "instance_id": qid,
        "db_id": "db_a",
        "db_type": "sqlite",
        "hardness": "medium",
        "question": "hidden",
        "gold_sql": "SELECT 1",
        "pred_sql": "SELECT 1",
        "ex": ex,
        "em": ex,
        "sf1": float(ex),
        "sc": None,
        "ves": float(ex),
        "rves": float(ex),
        "cf1": {"cf1_join": 1.0 if ex else 0.0},
        "sl_recall": 1.0,
        "error_root": error_root,
        "error_sub": "cf1_join=0.00" if error_root else None,
        "exec_error": None,
        "act_elapsed_s": elapsed,
        "tokens": {"generate": 100},
    }


# method A solves q0,q1,q2 (fast); method B solves q1,q3 (slow on shared wins)
METHOD_A = [
    _row("q0", 1, 1.0), _row("q1", 1, 1.0), _row("q2", 1, 1.0),
    _row("q3", 0, 1.0, error_root="model_missing_join"),
]
METHOD_B = [
    _row("q0", 0, 3.0, error_root="model_missing_join"), _row("q1", 1, 3.0),
    _row("q2", 0, 3.0, error_root="model_missing_join"), _row("q3", 1, 3.0),
]


class EvidenceViewTests(unittest.TestCase):
    def test_complete_bundle_reports_nothing_missing(self):
        bundle = _bundle("run-a", "method-a", METHOD_A, ex_avg=0.75)
        self.assertEqual(publication_completeness(bundle), [])

    def test_dropping_cf1_is_detected(self):
        bundle = _bundle("run-a", "method-a", METHOD_A, ex_avg=0.75)
        bundle["aggregate"].pop("cf1")
        missing = publication_completeness(bundle)
        self.assertIn("cf1_join", missing)

    def test_dropping_latency_is_detected_when_captured(self):
        bundle = _bundle("run-a", "method-a", METHOD_A, ex_avg=0.75)
        bundle["aggregate"].pop("latency")
        missing = publication_completeness(bundle)
        self.assertIn("latency_p95", missing)

    def test_uncaptured_signals_are_not_false_positives(self):
        rows = [dict(row, act_elapsed_s=None, sl_recall=None) for row in METHOD_A]
        bundle = _bundle("run-a", "method-a", rows, ex_avg=0.75)
        bundle["aggregate"].pop("latency")
        bundle["aggregate"].pop("sl_recall")
        missing = publication_completeness(bundle)
        self.assertNotIn("latency_p95", missing)
        self.assertNotIn("sl_recall", missing)

    def test_sample_diagnostics_include_token_usage_and_latency(self):
        bundle = _bundle("run-a", "method-a", METHOD_A, ex_avg=0.75)
        records = sample_diagnostics(bundle)
        self.assertEqual(len(records), 4)
        first = records[0]
        self.assertEqual(first["token_usage"], {"generate": 100})
        self.assertEqual(first["latency_ms"], 1000.0)
        self.assertNotIn("question", first)
        failed = next(r for r in records if r["instance_id"] == "q3")
        self.assertEqual(failed["error_category"], "model_missing_join")


class StoreViewTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Path(self.tmp.name) / "eval-store.sqlite"
        persist_eval_store(_bundle("run-a", "method-a", METHOD_A, ex_avg=0.75), self.db)
        persist_eval_store(_bundle("run-b", "method-b", METHOD_B, ex_avg=0.5), self.db)

    def tearDown(self):
        self.tmp.cleanup()

    def test_long_table_roundtrip(self):
        ex = load_sample_metric(self.db, "ex")
        self.assertEqual(ex["method-a"]["q0"], 1.0)
        self.assertEqual(ex["method-b"]["q0"], 0.0)
        latency = load_sample_metric(self.db, "act_elapsed_s")
        self.assertEqual(latency["method-b"]["q1"], 3.0)

    def test_raw_text_is_excluded_by_default(self):
        import json

        with sqlite3.connect(self.db) as conn:
            text_rows = conn.execute("SELECT COUNT(*) FROM sample_text").fetchone()[0]
            scores_json = conn.execute(
                "SELECT scores_json FROM runs WHERE run_id='run-a'").fetchone()[0]
        self.assertEqual(text_rows, 0)
        self.assertNotIn("per_sample", json.loads(scores_json))

    def test_meta_labels_are_stored(self):
        with sqlite3.connect(self.db) as conn:
            rows = conn.execute(
                "SELECT value FROM sample_meta WHERE run_id='run-a' AND field='error_root'"
            ).fetchall()
        self.assertEqual(rows, [("model_missing_join",)])


class MatrixViewTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Path(self.tmp.name) / "eval-store.sqlite"
        persist_eval_store(_bundle("run-a", "method-a", METHOD_A, ex_avg=0.75), self.db)
        persist_eval_store(_bundle("run-b", "method-b", METHOD_B, ex_avg=0.5), self.db)
        self.matrix = MethodMatrix.from_store(self.db, dataset="demo-bench", split="dev")

    def tearDown(self):
        self.tmp.cleanup()

    def test_oracle_gap(self):
        report = oracle_gap(self.matrix)
        # static best = method-a (3/4); oracle solves all 4 queries
        self.assertEqual(report["best_static_method"], "method-a")
        self.assertAlmostEqual(report["ex_static"], 0.75)
        self.assertAlmostEqual(report["ex_dynamic"], 1.0)
        self.assertAlmostEqual(report["gap"], 0.25)

    def test_disagreement(self):
        pair = disagreement(self.matrix)["method-a"]["method-b"]
        # they disagree on q0, q2, q3 -> 3/4
        self.assertAlmostEqual(pair["sample"], 0.75)
        # |1-3|/(1+3) = 0.5 on every query
        self.assertAlmostEqual(pair["efficiency"], 0.5)
        self.assertAlmostEqual(pair["combined"], 0.625)

    def test_empirical_difficulty_and_uniquely_solved(self):
        difficulty = empirical_difficulty(self.matrix)
        self.assertEqual(difficulty["per_query"], {"q0": 1, "q1": 2, "q2": 1, "q3": 1})
        self.assertEqual(difficulty["histogram"], {1: 3, 2: 1})
        unique = uniquely_solved(self.matrix)
        self.assertEqual(unique["counts"], {"method-a": 2, "method-b": 1})

    def test_efficiency_headroom(self):
        headroom = efficiency_headroom(self.matrix)
        # stratum N=2 (q1): correct latencies {1.0, 3.0} -> headroom 2/3
        self.assertAlmostEqual(headroom[2]["headroom"], 2 / 3)
        # stratum N=1: single correct method per query -> zero headroom
        self.assertAlmostEqual(headroom[1]["headroom"], 0.0)

    def test_matrix_report_uses_registry_ids(self):
        report = matrix_report(self.matrix)
        for key in ("oracle_gap", "method_disagreement", "empirical_difficulty",
                    "uniquely_solved", "efficiency_headroom"):
            self.assertIn(key, report)


class FitnessViewTests(unittest.TestCase):
    def test_metric_values_resolve_by_id(self):
        bundle = _bundle("run-a", "method-a", METHOD_A, ex_avg=0.75)
        self.assertEqual(metric_value(bundle, "ex"), 0.75)
        self.assertEqual(metric_value(bundle, "cf1_join"), 0.9)
        self.assertEqual(metric_value(bundle, "latency_p95"), 3.0)
        self.assertEqual(metric_value(bundle, "token_total"), 1200)
        self.assertEqual(metric_value(bundle, "cost_per_correct"), 1200 / 3)

    def test_fitness_inputs_shape(self):
        bundle = _bundle("run-a", "method-a", METHOD_A, ex_avg=0.75)
        inputs = fitness_inputs(bundle)
        self.assertEqual(inputs["ex"], 0.75)
        self.assertEqual(inputs["latency_avg"], 2.0)
        self.assertIn("hard_slice_score", inputs)


if __name__ == "__main__":
    unittest.main()

# Foundation regressions for the registry-driven evaluation package:
# the new aggregation engine must reproduce the legacy assembly numbers.

import json
import unittest
from pathlib import Path

from reproduce.eval.aggregate import engine
from reproduce.eval.aggregate import statistics as stats
from reproduce.eval.aggregate.slicing import slice_rows
from reproduce.eval.bundle.schema import (
    V1_REQUIRED_TOP_KEYS,
    validate_bundle,
    validate_published_bundle,
)
from reproduce.eval.paths import allowed_config_output_roots, evidence_root, files_root, project_root
from reproduce.eval.bundle import build as bundle_build
from reproduce.eval.registry import default_registry


def _sample(instance_id, hardness, db_type, ex, em, cf1_join, cf1_where, elapsed):
    return {
        "instance_id": instance_id,
        "hardness": hardness,
        "db_type": db_type,
        "ex": ex,
        "em": em,
        "sf1": ex * 0.9,
        "sc": None,
        "ves": ex * 0.8,
        "rves": ex * 0.7,
        "cf1": {"cf1_join": cf1_join, "cf1_where": cf1_where},
        "error_root": None if ex == 1 else "model_missing_join",
        "act_elapsed_s": elapsed,
    }


SAMPLES = [
    _sample("s0", "easy", "sqlite", 1, 1, 1.0, 1.0, 1.0),
    _sample("s1", "easy", "sqlite", 0, 0, 0.0, 0.5, 2.0),
    _sample("s2", "medium", "sqlite", 1, 0, 1.0, 0.8, 3.0),
    _sample("s3", "hard", "bigquery", 0, 0, 0.4, 0.2, 8.0),
    _sample("s4", "extra", None, 1, 1, 1.0, 1.0, 5.0),
]


class RegistryTests(unittest.TestCase):
    def test_default_registry_loads_all_layers(self):
        registry = default_registry()
        by_layer = {layer: registry.metrics(layer=layer) for layer in ("L1", "L2", "L3", "L4", "L5", "L6")}
        for layer, specs in by_layer.items():
            self.assertTrue(specs, f"layer {layer} has no registered metrics")
        ids = [spec.id for spec in registry.metrics()]
        self.assertEqual(len(ids), len(set(ids)))
        for expected in ("ex", "latency_p95", "cf1_join", "error_root_distribution",
                         "selection_regret", "oracle_gap"):
            self.assertIn(expected, ids)

    def test_slices_registered(self):
        registry = default_registry()
        self.assertEqual(
            {spec.id for spec in registry.slices()},
            {"hardness", "db_type"},
        )


class StatisticsTests(unittest.TestCase):
    def test_percentile_linear_interpolation(self):
        values = [1, 2, 3, 4]
        self.assertEqual(stats.percentile(values, 0), 1)
        self.assertEqual(stats.percentile(values, 100), 4)
        self.assertAlmostEqual(stats.percentile(values, 50), 2.5)
        self.assertAlmostEqual(stats.percentile(values, 95), 3.85)

    def test_percentile_is_not_max(self):
        values = [1.0] * 99 + [100.0]
        self.assertLess(stats.percentile(values, 95), 100.0)

    def test_wilson_interval_shrinks_with_n(self):
        small = stats.wilson_interval(5, 10)
        large = stats.wilson_interval(500, 1000)
        self.assertLess(large[1] - large[0], small[1] - small[0])
        self.assertGreaterEqual(small[0], 0.0)
        self.assertLessEqual(small[1], 1.0)

    def test_bootstrap_interval_is_deterministic_and_covers_mean(self):
        values = [0.2, 0.4, 0.6, 0.8, 1.0]
        first = stats.bootstrap_interval(values)
        second = stats.bootstrap_interval(values)
        self.assertEqual(first, second)
        self.assertLessEqual(first[0], sum(values) / len(values))
        self.assertGreaterEqual(first[1], sum(values) / len(values))


class EngineLegacyEquivalenceTests(unittest.TestCase):
    """The registry engine must reproduce assembly's numbers exactly."""

    def test_cf1_aggregation_matches_assembly(self):
        registry = default_registry()
        legacy = bundle_build._aggregate_cf1(SAMPLES)
        for component in ("cf1_join", "cf1_where"):
            cell = engine.fold_metric(SAMPLES, registry.get(component))
            self.assertEqual(cell["avg"], legacy[component]["avg"], component)

    def test_hardness_slice_matches_assembly(self):
        registry = default_registry()
        legacy = bundle_build._by_hardness(SAMPLES)
        sliced = engine.slice_metrics(SAMPLES, registry, metric_ids=["ex", "em", "cf1_join", "cf1_where"])
        for hardness in ("easy", "medium", "hard", "extra"):
            with self.subTest(hardness=hardness):
                new_cell = sliced["hardness"][hardness]
                old_cell = legacy[hardness]
                self.assertEqual(new_cell["count"], old_cell["count"])
                if old_cell["count"] == 0:
                    continue
                self.assertEqual(new_cell["ex"]["avg"], old_cell["ex"])
                self.assertEqual(new_cell["em"]["avg"], old_cell["em"])
                self.assertEqual(new_cell["cf1_join"]["avg"], old_cell["cf1_join"])
                self.assertEqual(new_cell["cf1_where"]["avg"], old_cell["cf1_where"])

    def test_db_type_slice_matches_assembly(self):
        registry = default_registry()
        legacy = bundle_build._by_db_type(SAMPLES)
        sliced = engine.slice_metrics(SAMPLES, registry, metric_ids=["ex", "em"])
        self.assertEqual(set(sliced["db_type"]), set(legacy))
        for db_type, old_cell in legacy.items():
            new_cell = sliced["db_type"][db_type]
            self.assertEqual(new_cell["count"], old_cell["count"])
            self.assertEqual(new_cell["ex"]["avg"], old_cell["ex"])

    def test_latency_metrics_fold_from_per_sample(self):
        registry = default_registry()
        avg = engine.fold_metric(SAMPLES, registry.get("latency_avg"))
        p95 = engine.fold_metric(SAMPLES, registry.get("latency_p95"))
        self.assertAlmostEqual(avg["avg"], (1.0 + 2.0 + 3.0 + 8.0 + 5.0) / 5)
        self.assertAlmostEqual(p95["value"], stats.percentile([1.0, 2.0, 3.0, 8.0, 5.0], 95))
        self.assertIn("interval", avg)

    def test_wilson_interval_attached_to_ex(self):
        registry = default_registry()
        cell = engine.fold_metric(SAMPLES, registry.get("ex"))
        self.assertEqual(cell["avg"], 3 / 5)
        low, high = cell["interval"]
        self.assertLess(low, 3 / 5)
        self.assertGreater(high, 3 / 5)


class SliceBehaviorTests(unittest.TestCase):
    def test_fixed_values_keep_order_and_empty_groups(self):
        registry = default_registry()
        groups = slice_rows(SAMPLES, registry.get_slice("hardness"))
        self.assertEqual(list(groups), ["easy", "medium", "hard", "extra"])

    def test_discovered_labels_map_none_to_unknown(self):
        registry = default_registry()
        groups = slice_rows(SAMPLES, registry.get_slice("db_type"))
        self.assertIn("unknown", groups)
        self.assertEqual(len(groups["unknown"]), 1)

    def test_min_samples_gate_reports_count_only(self):
        registry = default_registry()
        sliced = engine.slice_metrics(SAMPLES, registry, metric_ids=["ex"], min_samples_override=2)
        hard_cell = sliced["hardness"]["hard"]
        self.assertEqual(hard_cell, {"count": 1})


class BundleSchemaTests(unittest.TestCase):
    def test_published_bundles_satisfy_published_contract(self):
        bundles = sorted(evidence_root().glob("*/scores.json"))
        self.assertTrue(bundles, "no published evidence bundles found")
        for path in bundles:
            scores = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(validate_published_bundle(scores), [], path)

    def test_full_bundle_contract_detects_missing_keys(self):
        stub = {key: {} for key in V1_REQUIRED_TOP_KEYS}
        stub["aggregate"] = {key: {} for key in
                             ("ex", "em", "sf1", "sc", "ves", "rves",
                              "cf1", "fd", "error_root_distribution", "pipeline", "token")}
        self.assertEqual(validate_bundle(stub), [])
        broken = dict(stub)
        broken.pop("by_hardness")
        self.assertTrue(any("by_hardness" in problem for problem in validate_bundle(broken)))


class PathAuthorityTests(unittest.TestCase):
    def test_roots_exist_and_are_distinct(self):
        self.assertTrue(files_root().is_dir())
        self.assertTrue(evidence_root().is_dir())
        self.assertEqual(files_root().parent, project_root())

    def test_config_output_roots_only_allow_files(self):
        roots = allowed_config_output_roots()
        self.assertEqual(roots, (files_root(),))

    def test_reproduce_contract_uses_path_authority(self):
        import importlib.util
        import sys

        spec = importlib.util.spec_from_file_location(
            "reproduce_contract", Path(project_root()) / "tools" / "reproduce_contract.py")
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        try:
            spec.loader.exec_module(module)
        finally:
            sys.modules.pop(spec.name, None)
        self.assertTrue(module._valid_workspace_output("../files/pred_sql/demo"))
        self.assertFalse(module._valid_workspace_output("../artifacts/anything"))
        self.assertFalse(module._valid_workspace_output("/absolute/path"))


if __name__ == "__main__":
    unittest.main()

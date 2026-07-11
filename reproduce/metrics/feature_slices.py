"""SQL feature slicing and QVT-style consistency metrics."""

from __future__ import annotations

from collections import defaultdict
from typing import Any, Dict, List, Optional

from reproduce.metrics.sql_parser import SQLFeatureExtractor


DEFAULT_FEATURE_FILTERS = {
    "join>0": ("join", ">", 0),
    "subquery>0": ("subquery", ">", 0),
    "set_operation>0": ("set_operation", ">", 0),
    "aggregation>0": ("aggregation", ">", 0),
    "group_by>0": ("group_by", ">", 0),
    "order_by>0": ("order_by", ">", 0),
    "predicate>2": ("predicate", ">", 2),
    "like>0": ("like", ">", 0),
    "distinct>0": ("distinct", ">", 0),
    "window>0": ("window", ">", 0),
    "control_flow>0": ("control_flow", ">", 0),
}

DEFAULT_SCENARIOS = {
    "join_and_group": [("join", ">", 0), ("group_by", ">", 0)],
    "nested_or_set": [("subquery", ">", 0), ("set_operation", ">", 0), "OR"],
    "complex_predicate": [("predicate", ">", 2), ("logical_connector", ">", 0)],
}


def enrich_sql_features(sample: dict) -> None:
    gold_sql = sample.get("gold_sql")
    pred_sql = sample.get("pred_sql")
    gold = SQLFeatureExtractor(gold_sql).extract() if gold_sql else {}
    pred = SQLFeatureExtractor(pred_sql).extract() if pred_sql else {}
    sample["sql_features"] = {
        "gold": gold,
        "pred": pred,
        "delta": SQLFeatureExtractor.compute_delta(gold, pred) if gold and pred else {},
    }


def aggregate_sql_feature_slices(per_sample: List[dict]) -> dict:
    return {
        name: _slice_stats([
            sample for sample in per_sample
            if _match_filter(sample, condition)
        ])
        for name, condition in DEFAULT_FEATURE_FILTERS.items()
    }


def aggregate_scenarios(per_sample: List[dict]) -> dict:
    return {
        name: _slice_stats([
            sample for sample in per_sample
            if _match_scenario(sample, scenario)
        ])
        for name, scenario in DEFAULT_SCENARIOS.items()
    }


def compute_qvt(per_sample: List[dict]) -> dict:
    groups: Dict[str, List[dict]] = defaultdict(list)
    for sample in per_sample:
        gold = sample.get("gold_sql")
        if gold:
            groups[str(gold).strip()].append(sample)

    eligible = {gold: rows for gold, rows in groups.items() if len(rows) >= 2}
    group_rows = []
    for gold, rows in eligible.items():
        ex_values = [row.get("ex") for row in rows if isinstance(row.get("ex"), (int, float))]
        if not ex_values:
            continue
        has_pass = any(value == 1 for value in ex_values)
        has_fail = any(value == 0 for value in ex_values)
        group_rows.append({
            "gold_sql": gold,
            "sample_count": len(rows),
            "exec_acc": sum(ex_values) / len(ex_values),
            "stable": not (has_pass and has_fail),
            "flip": has_pass and has_fail,
            "sample_ids": [row.get("instance_id") for row in rows],
        })

    return {
        "eligible_groups": len(group_rows),
        "sample_count": sum(row["sample_count"] for row in group_rows),
        "avg_group_exec_acc": _mean([row["exec_acc"] for row in group_rows]),
        "stable_group_rate": _mean([1 if row["stable"] else 0 for row in group_rows]),
        "flip_rate": _mean([1 if row["flip"] else 0 for row in group_rows]),
        "groups": group_rows,
    }


def _match_filter(sample: dict, condition: tuple[str, str, int]) -> bool:
    feature, op, value = condition
    actual = ((sample.get("sql_features") or {}).get("gold") or {}).get(feature)
    if not isinstance(actual, (int, float)):
        return False
    if op == ">":
        return actual > value
    if op == "<":
        return actual < value
    if op == "=":
        return actual == value
    return False


def _match_scenario(sample: dict, scenario: List[Any]) -> bool:
    if scenario and scenario[-1] == "OR":
        return any(_match_filter(sample, condition) for condition in scenario[:-1])
    return all(_match_filter(sample, condition) for condition in scenario)


def _slice_stats(rows: List[dict]) -> dict:
    return {
        "count": len(rows),
        "ex": _mean([row.get("ex") for row in rows if isinstance(row.get("ex"), (int, float))]),
        "em": _mean([row.get("em") for row in rows if isinstance(row.get("em"), (int, float))]),
        "sf1": _mean([row.get("sf1") for row in rows if isinstance(row.get("sf1"), (int, float))]),
        "ves": _mean([row.get("ves") for row in rows if isinstance(row.get("ves"), (int, float))]),
        "bottlenecks": _bottlenecks(rows),
    }


def _bottlenecks(rows: List[dict]) -> dict:
    counts: Dict[str, int] = defaultdict(int)
    for row in rows:
        stage = (((row.get("workflow") or {}).get("attribution") or {}).get("root_stage"))
        if stage:
            counts[str(stage)] += 1
    return dict(counts)


def _mean(values: List[Optional[float]]) -> Optional[float]:
    values = [float(value) for value in values if isinstance(value, (int, float))]
    return sum(values) / len(values) if values else None

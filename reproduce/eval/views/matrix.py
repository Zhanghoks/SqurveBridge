"""L6 cross-method comparative metrics over the eval store.

Derived from the correctness/latency matrix ``(query, method) -> (Y, t)``.
Definitions follow arXiv 2602.15564 Section 3 and Appendices B/C:

- ``EX_static  = max_i mean_q Y_i(q)``
- ``EX_dynamic = mean_q max_i Y_i(q)`` (oracle per-query selection)
- ``oracle_gap = EX_dynamic - EX_static``
- ``D_sample(i,j) = mean_q 1{Y_i(q) != Y_j(q)}``
- ``D_eff(i,j)    = mean_q |t_i - t_j| / (t_i + t_j)``
- ``N(q)`` = number of methods solving q (empirical difficulty)
- ``efficiency_headroom(N) = (mean t_max - mean t_min) / mean t_max`` over the
  correct-method latencies of queries in difficulty stratum N.

Everything is deterministic dictionary math over recorded runs; no LLM calls.
"""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional

from reproduce.eval.views.store import load_sample_metric


class MethodMatrix:
    """Correctness and latency per (method, query), on the common query set."""

    def __init__(self, correctness: Dict[str, Dict[str, float]],
                 latency: Dict[str, Dict[str, float]] | None = None) -> None:
        self.methods = sorted(correctness)
        common: set[str] | None = None
        for method in self.methods:
            ids = set(correctness[method])
            common = ids if common is None else common & ids
        self.query_ids = sorted(common or set())
        self.correct = {
            method: {qid: int(bool(correctness[method][qid])) for qid in self.query_ids}
            for method in self.methods
        }
        latency = latency or {}
        self.latency = {
            method: {
                qid: float(latency[method][qid])
                for qid in self.query_ids
                if isinstance((latency.get(method) or {}).get(qid), (int, float))
            }
            for method in self.methods
        }

    @classmethod
    def from_store(
            cls,
            db_path: str | Path,
            *,
            dataset: Optional[str] = None,
            split: Optional[str] = None,
    ) -> "MethodMatrix":
        correctness = load_sample_metric(db_path, "ex", dataset=dataset, split=split)
        latency = load_sample_metric(db_path, "act_elapsed_s", dataset=dataset, split=split)
        return cls(correctness, latency)


def oracle_gap(matrix: MethodMatrix) -> Dict[str, Any]:
    if not matrix.methods or not matrix.query_ids:
        return {"ex_static": None, "ex_dynamic": None, "gap": None, "best_static_method": None}
    per_method = {
        method: sum(matrix.correct[method].values()) / len(matrix.query_ids)
        for method in matrix.methods
    }
    best_method = max(per_method, key=per_method.get)
    dynamic = sum(
        max(matrix.correct[method][qid] for method in matrix.methods)
        for qid in matrix.query_ids
    ) / len(matrix.query_ids)
    return {
        "ex_static": per_method[best_method],
        "ex_dynamic": dynamic,
        "gap": dynamic - per_method[best_method],
        "best_static_method": best_method,
        "per_method_ex": per_method,
        "query_count": len(matrix.query_ids),
    }


def disagreement(matrix: MethodMatrix) -> Dict[str, Dict[str, Dict[str, float]]]:
    result: Dict[str, Dict[str, Dict[str, float]]] = {}
    for i, method_a in enumerate(matrix.methods):
        for method_b in matrix.methods[i + 1:]:
            sample_terms = [
                1 if matrix.correct[method_a][qid] != matrix.correct[method_b][qid] else 0
                for qid in matrix.query_ids
            ]
            efficiency_terms = []
            for qid in matrix.query_ids:
                t_a = matrix.latency.get(method_a, {}).get(qid)
                t_b = matrix.latency.get(method_b, {}).get(qid)
                if t_a is not None and t_b is not None and (t_a + t_b) > 0:
                    efficiency_terms.append(abs(t_a - t_b) / (t_a + t_b))
            d_sample = sum(sample_terms) / len(sample_terms) if sample_terms else None
            d_eff = sum(efficiency_terms) / len(efficiency_terms) if efficiency_terms else None
            combined = None
            if d_sample is not None and d_eff is not None:
                combined = (d_sample + d_eff) / 2
            result.setdefault(method_a, {})[method_b] = {
                "sample": d_sample, "efficiency": d_eff, "combined": combined,
            }
    return result


def empirical_difficulty(matrix: MethodMatrix) -> Dict[str, Any]:
    n_by_query = {
        qid: sum(matrix.correct[method][qid] for method in matrix.methods)
        for qid in matrix.query_ids
    }
    histogram: Dict[int, int] = defaultdict(int)
    for count in n_by_query.values():
        histogram[count] += 1
    return {"per_query": n_by_query, "histogram": dict(sorted(histogram.items()))}


def uniquely_solved(matrix: MethodMatrix) -> Dict[str, Any]:
    counts = {method: 0 for method in matrix.methods}
    queries: Dict[str, List[str]] = {method: [] for method in matrix.methods}
    for qid in matrix.query_ids:
        solvers = [method for method in matrix.methods if matrix.correct[method][qid]]
        if len(solvers) == 1:
            counts[solvers[0]] += 1
            queries[solvers[0]].append(qid)
    return {"counts": counts, "queries": queries}


def efficiency_headroom(matrix: MethodMatrix) -> Dict[int, Dict[str, float]]:
    """Correctness-constrained latency headroom per difficulty stratum N(q)."""
    strata: Dict[int, List[tuple[float, float]]] = defaultdict(list)
    for qid in matrix.query_ids:
        correct_latencies = [
            matrix.latency[method][qid]
            for method in matrix.methods
            if matrix.correct[method][qid] and qid in matrix.latency.get(method, {})
        ]
        if not correct_latencies:
            continue
        strata[sum(matrix.correct[method][qid] for method in matrix.methods)].append(
            (max(correct_latencies), min(correct_latencies)))
    result = {}
    for stratum, pairs in sorted(strata.items()):
        mean_max = sum(pair[0] for pair in pairs) / len(pairs)
        mean_min = sum(pair[1] for pair in pairs) / len(pairs)
        result[stratum] = {
            "query_count": len(pairs),
            "mean_t_max": mean_max,
            "mean_t_min": mean_min,
            "headroom": (mean_max - mean_min) / mean_max if mean_max else None,
        }
    return result


def matrix_report(matrix: MethodMatrix) -> Dict[str, Any]:
    """All L6 metrics in one payload (registry ids as keys)."""
    return {
        "methods": matrix.methods,
        "query_count": len(matrix.query_ids),
        "oracle_gap": oracle_gap(matrix),
        "method_disagreement": disagreement(matrix),
        "empirical_difficulty": empirical_difficulty(matrix)["histogram"],
        "uniquely_solved": uniquely_solved(matrix)["counts"],
        "efficiency_headroom": efficiency_headroom(matrix),
    }

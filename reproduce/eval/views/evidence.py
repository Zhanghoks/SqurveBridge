"""Publication view derived from the metric registry.

``tools/evidence.py`` owns the hard privacy contract (forbidden keys, secret
patterns, checksums). This module owns the *completeness* direction that the
generic sanitizer cannot know: which metrics are supposed to survive export.
Silent metric loss (cf1/token/hardness missing from published bundles,
``token_usage`` allowed but never written) is the failure mode this closes.

The completeness assertions run inside the regular unittest suite, which the
release gate (`tools/release_check.py`) executes on every run.
"""

from __future__ import annotations

from typing import Any, Dict, List

from reproduce.eval.registry import MetricRegistry, default_registry


# aggregate locations that hold registry metrics, by layer convention
_L1_IDS = ("ex", "em", "sf1", "sc", "ves", "rves")


def aggregate_metric_value(scores: Dict[str, Any], metric_id: str) -> Any:
    """Resolve a registry metric id to its aggregate value in a v1 bundle."""
    aggregate = scores.get("aggregate") or {}
    if metric_id in _L1_IDS:
        cell = aggregate.get(metric_id)
        return cell.get("avg") if isinstance(cell, dict) else cell
    if metric_id.startswith("cf1_"):
        cell = (aggregate.get("cf1") or {}).get(metric_id)
        return cell.get("avg") if isinstance(cell, dict) else cell
    if metric_id == "sl_recall":
        cell = aggregate.get("sl_recall")
        return cell.get("avg") if isinstance(cell, dict) else None
    if metric_id == "latency_avg":
        return (aggregate.get("latency") or {}).get("avg_s")
    if metric_id == "latency_p50":
        return (aggregate.get("latency") or {}).get("p50_s")
    if metric_id == "latency_p95":
        return (aggregate.get("latency") or {}).get("p95_s")
    if metric_id == "token_total":
        return (aggregate.get("token") or {}).get("total_tokens")
    if metric_id == "token_avg_per_sample":
        return (aggregate.get("token") or {}).get("avg_per_sample")
    if metric_id == "cost_per_correct":
        token_total = (aggregate.get("token") or {}).get("total_tokens")
        ex = aggregate.get("ex") or {}
        pass_count = ex.get("pass_count")
        if isinstance(token_total, (int, float)) and isinstance(pass_count, int) and pass_count > 0:
            return token_total / pass_count
        return None
    if metric_id == "error_root_distribution":
        return aggregate.get("error_root_distribution")
    return None


def publishable_metric_ids(registry: MetricRegistry | None = None) -> List[str]:
    registry = registry or default_registry()
    return [
        spec.id for spec in registry.metrics()
        if spec.publication in {"public", "aggregate_only"} and spec.layer in {"L1", "L2", "L3", "L4"}
    ]


def publication_completeness(scores: Dict[str, Any], registry: MetricRegistry | None = None) -> List[str]:
    """Declared publishable metrics that the bundle fails to provide.

    A metric counts as missing only when the bundle carries the raw material
    for it (fd and derived stage summaries are excluded from the strict set).
    """
    registry = registry or default_registry()
    missing = []
    for metric_id in publishable_metric_ids(registry):
        spec = registry.get(metric_id)
        if spec.aggregation == "derived" and metric_id not in {"error_root_distribution",
                                                               "token_total",
                                                               "token_avg_per_sample",
                                                               "cost_per_correct"}:
            continue
        if aggregate_metric_value(scores, metric_id) is None and not _legitimately_absent(scores, metric_id):
            missing.append(metric_id)
    return missing


def _legitimately_absent(scores: Dict[str, Any], metric_id: str) -> bool:
    """A metric may be absent when its raw signal was never captured."""
    per_sample = scores.get("per_sample") or []
    aggregate = scores.get("aggregate") or {}
    if metric_id == "sc":
        return True  # requires generate_num >= 2 by contract
    if metric_id == "sl_recall":
        return not any(isinstance(row.get("sl_recall"), (int, float)) for row in per_sample)
    if metric_id.startswith("latency_"):
        return not any(isinstance(row.get("act_elapsed_s"), (int, float)) for row in per_sample)
    if metric_id in {"token_total", "token_avg_per_sample", "cost_per_correct"}:
        return not (aggregate.get("token") or {}).get("total_calls")
    if metric_id.startswith("cf1_"):
        return not any(isinstance(row.get("cf1"), dict) for row in per_sample)
    if metric_id == "error_root_distribution":
        return all(row.get("ex") != 0 for row in per_sample)
    return False


def sample_diagnostics(scores: Dict[str, Any], registry: MetricRegistry | None = None) -> List[Dict[str, Any]]:
    """Publication-safe per-sample diagnostic records.

    Shape follows ``tools/evidence.ALLOWED_DIAGNOSTIC_FIELDS``; this builder
    also fills ``token_usage`` (allowed by the contract but historically never
    written by hand-rolled exports).
    """
    registry = registry or default_registry()
    records = []
    for row in scores.get("per_sample") or []:
        metrics = {}
        for metric_id in _L1_IDS:
            value = row.get(metric_id)
            if isinstance(value, (int, float)):
                metrics[metric_id] = value
        record: Dict[str, Any] = {
            "instance_id": row.get("instance_id"),
            "metrics": metrics,
            "stage_status": "completed" if row.get("exec_error") is None else "exec_error",
        }
        if row.get("error_root"):
            record["error_category"] = row["error_root"]
        if row.get("error_sub"):
            record["error_categories"] = [row["error_sub"]]
        if isinstance(row.get("act_elapsed_s"), (int, float)):
            record["latency_ms"] = round(float(row["act_elapsed_s"]) * 1000, 3)
        tokens = row.get("tokens")
        if isinstance(tokens, dict) and tokens:
            record["token_usage"] = {
                str(step): int(count)
                for step, count in tokens.items()
                if isinstance(count, (int, float))
            }
        records.append(record)
    return records

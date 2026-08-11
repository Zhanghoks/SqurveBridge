"""Registry-driven aggregation: every cell carries value, n, and interval."""

from __future__ import annotations

from collections import Counter
from typing import Any, Dict, List, Optional

from reproduce.eval.aggregate import statistics as stats
from reproduce.eval.aggregate.slicing import numeric_values, slice_rows
from reproduce.eval.registry.registry import MetricRegistry
from reproduce.eval.registry.spec import MetricSpec


def fold_metric(rows: List[dict], spec: MetricSpec, *, with_interval: bool = True) -> Dict[str, Any]:
    """Fold per-sample values into one aggregate cell."""
    kind, _, argument = spec.aggregation.partition(":")
    values = numeric_values(rows, spec.source)
    cell: Dict[str, Any] = {"n": len(values), "total": len(rows)}

    if kind in {"mean", "rate"}:
        cell["avg"] = stats.mean(values)
    elif kind == "sum":
        cell["sum"] = sum(values) if values else None
    elif kind == "percentile":
        cell["value"] = stats.percentile(values, float(argument))
    elif kind == "distribution":
        labels = [str(v) for v in (row_value for row_value in _labels(rows, spec.source)) if v is not None]
        counts = Counter(labels)
        cell["distribution"] = {
            label: {"count": count, "pct": count / len(labels) if labels else 0}
            for label, count in counts.most_common()
        }
        cell["n"] = len(labels)
    else:
        raise ValueError(f"{spec.id}: engine cannot fold aggregation {spec.aggregation!r}")

    if with_interval and spec.interval and values:
        cell["interval"] = _interval(spec, values)
    return cell


def aggregate_metrics(
        rows: List[dict],
        registry: MetricRegistry,
        *,
        layer: str | None = None,
        with_interval: bool = True,
) -> Dict[str, Dict[str, Any]]:
    result = {}
    for spec in registry.engine_metrics():
        if layer is not None and spec.layer != layer:
            continue
        result[spec.id] = fold_metric(rows, spec, with_interval=with_interval)
    return result


def slice_metrics(
        rows: List[dict],
        registry: MetricRegistry,
        *,
        metric_ids: List[str] | None = None,
        min_samples_override: int | None = None,
) -> Dict[str, Dict[str, Any]]:
    """Every sliceable engine metric folded over every registered slice axis."""
    specs = [
        spec for spec in registry.engine_metrics()
        if spec.sliceable and (metric_ids is None or spec.id in metric_ids)
    ]
    result: Dict[str, Dict[str, Any]] = {}
    for slice_spec in registry.slices():
        minimum = min_samples_override if min_samples_override is not None else slice_spec.min_samples
        axis: Dict[str, Any] = {}
        for label, group in slice_rows(rows, slice_spec).items():
            cell: Dict[str, Any] = {"count": len(group)}
            if stats.min_sample_ok(len(group), minimum):
                for spec in specs:
                    cell[spec.id] = fold_metric(group, spec, with_interval=False)
            axis[label] = cell
        result[slice_spec.id] = axis
    return result


def _interval(spec: MetricSpec, values: List[float]) -> Optional[tuple[float, float]]:
    if spec.interval == "wilson":
        return stats.wilson_interval(sum(values), len(values))
    if spec.interval == "bootstrap":
        return stats.bootstrap_interval(values)
    return None


def _labels(rows: List[dict], source: str):
    from reproduce.eval.aggregate.slicing import extract_value

    for row in rows:
        yield extract_value(row, source)

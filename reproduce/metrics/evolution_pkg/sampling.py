"""Sample manifest helpers for bounded evolution evaluations."""

from __future__ import annotations

from collections import defaultdict
from typing import Any


def build_sample_manifest(
        per_sample: list[dict[str, Any]],
        *,
        limit: int,
        group_fields: tuple[str, ...] = ("hardness", "error_root"),
) -> dict[str, Any]:
    buckets: dict[tuple[Any, ...], list[dict[str, Any]]] = defaultdict(list)
    for sample in per_sample:
        key = tuple(sample.get(field) for field in group_fields)
        buckets[key].append(sample)

    selected: list[str] = []
    ordered_keys = sorted(buckets, key=lambda item: tuple("" if value is None else str(value) for value in item))
    while len(selected) < limit and any(buckets.values()):
        for key in ordered_keys:
            bucket = buckets[key]
            if not bucket:
                continue
            sample = bucket.pop(0)
            sample_id = sample.get("instance_id")
            if sample_id is not None:
                selected.append(str(sample_id))
            if len(selected) >= limit:
                break

    return {
        "limit": limit,
        "strategy": "stratified_round_robin",
        "group_fields": list(group_fields),
        "sample_ids": selected,
        "truncated": len(selected) < len(per_sample),
    }

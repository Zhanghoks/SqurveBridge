"""The single slice implementation.

Replaces the four parallel copies previously spread across
``assembly._by_hardness``, ``assembly._by_db_type``,
``assembly._by_component_hardness``, and ``feature_slices._slice_stats``.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any, Dict, List

from reproduce.eval.registry.spec import SliceSpec


def slice_rows(rows: List[dict], spec: SliceSpec) -> Dict[str, List[dict]]:
    """Group rows by the slice field.

    Fixed ``spec.values`` keeps that label order and includes empty groups
    (matching the legacy hardness view). Discovered labels are sorted and a
    missing value maps to ``"unknown"`` (matching the legacy db_type view).
    """
    if spec.values:
        groups: Dict[str, List[dict]] = {label: [] for label in spec.values}
        for row in rows:
            label = row.get(spec.field)
            if label in groups:
                groups[label].append(row)
        return groups

    discovered: Dict[str, List[dict]] = defaultdict(list)
    for row in rows:
        discovered[str(row.get(spec.field) or "unknown")].append(row)
    return {label: discovered[label] for label in sorted(discovered)}


def extract_value(row: dict, source: str) -> Any:
    """Resolve a dot-path source ("cf1.cf1_join") against a per-sample row."""
    current: Any = row
    for part in source.split("."):
        if not isinstance(current, dict):
            return None
        current = current.get(part)
    return current


def numeric_values(rows: List[dict], source: str) -> List[float]:
    values = []
    for row in rows:
        value = extract_value(row, source)
        if isinstance(value, (int, float)):
            values.append(float(value))
    return values

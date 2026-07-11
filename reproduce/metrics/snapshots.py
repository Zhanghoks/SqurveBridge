"""Pipeline snapshot hooks for before/after SQL diagnostics."""

from __future__ import annotations

from typing import Any


def capture_pred_sql_snapshot(dataset: Any, item: int, actor: Any, results: dict) -> None:
    """Persist the previous pred_sql before another pred_sql-producing actor runs."""
    if not dataset or not isinstance(results, dict):
        return
    if getattr(actor, "output_name", None) != "pred_sql":
        return
    if "pred_sql" not in results:
        return

    key = f"pred_sql_before_{getattr(actor, 'name', actor.__class__.__name__)}"
    try:
        if hasattr(dataset, "setitem"):
            dataset.setitem(item, key, results["pred_sql"])
        else:
            dataset[item][key] = results["pred_sql"]
    except Exception:
        return

"""Pipeline before/after delta metrics from pred_sql snapshots."""

from __future__ import annotations

from typing import Any, List, Optional

from reproduce.metrics.evaluators import _dataframes_equal, _execute_sql, _resolve_sql


def compute_pipeline_delta(row: dict, dataset: Any = None) -> dict:
    before_keys = [key for key in row if key.startswith("pred_sql_before_")]
    scaler_key = _find_key(before_keys, ("scale", "scaler"))
    optimizer_key = _find_key(before_keys, ("optimiz", "optimizer"))
    selector_key = _find_key(before_keys, ("select", "selector"))
    decomposer_triggered = bool(row.get("sub_questions"))

    return {
        "scaler": _scaler_delta(row, dataset, scaler_key),
        "optimizer": _optimizer_delta(row, dataset, optimizer_key),
        "selector": _selector_delta(row, dataset, selector_key),
        "decomposer": {
            "has_decomposer": decomposer_triggered,
            "decomposition_triggered": decomposer_triggered,
            "sub_question_count": len(row.get("sub_questions") or []),
        },
    }


def _scaler_delta(row: dict, dataset: Any, before_key: Optional[str]) -> dict:
    has_scaler = before_key is not None
    result = {"has_scaler": has_scaler}
    if not has_scaler or dataset is None:
        return result

    before_sql = _first_sql(row.get(before_key))
    candidates = _sql_list(row.get("pred_sql"))
    pass_1 = _score_sql(before_sql, row, dataset)
    candidate_scores = [_score_sql(sql, row, dataset) for sql in candidates]
    pass_k = max((s for s in candidate_scores if s is not None), default=None) if candidate_scores else None
    result.update({
        "candidate_count": len(candidates),
        "candidate_diversity": _diversity(candidates),
        "pass_1": pass_1,
        "pass_k": pass_k,
        "scaler_gain": None if pass_1 is None or pass_k is None else pass_k - pass_1,
    })
    return result


def _optimizer_delta(row: dict, dataset: Any, before_key: Optional[str]) -> dict:
    has_optimizer = before_key is not None
    result = {"has_optimizer": has_optimizer}
    if not has_optimizer or dataset is None:
        return result

    before = _score_sql(_first_sql(row.get(before_key)), row, dataset)
    after_scores = [_score_sql(sql, row, dataset) for sql in _sql_list(row.get("pred_sql"))]
    after = max((s for s in after_scores if s is not None), default=None) if after_scores else None
    result.update({
        "ex_before": before,
        "ex_after": after,
        "fix_success": before == 0 and after == 1,
        "degradation": before == 1 and after == 0,
        "debug_turns": row.get("debug_turns") or row.get("optimize_debug_turns"),
    })
    return result


def _selector_delta(row: dict, dataset: Any, before_key: Optional[str]) -> dict:
    has_selector = before_key is not None
    result = {"has_selector": has_selector}
    if not has_selector or dataset is None:
        return result

    candidates = _sql_list(row.get(before_key))
    selected = _first_sql(row.get("pred_sql"))
    candidate_scores = [_score_sql(sql, row, dataset) for sql in candidates]
    selected_ex = _score_sql(selected, row, dataset)
    oracle = max((s for s in candidate_scores if s is not None), default=None) if candidate_scores else None
    first = candidate_scores[0] if candidate_scores else None
    result.update({
        "candidate_count": len(candidates),
        "oracle_ex": oracle,
        "selected_ex": selected_ex,
        "first_ex": first,
        "selection_accuracy": selected_ex,
        "selection_gain": None if selected_ex is None or first is None else selected_ex - first,
        "selection_loss": None if oracle is None or selected_ex is None else oracle - selected_ex,
    })
    return result


def _score_sql(sql: Optional[str], row: dict, dataset: Any) -> Optional[int]:
    gold_sql = _resolve_sql(row.get("query"))
    if not sql or not gold_sql or dataset is None:
        return None
    gold_df = _execute_sql(gold_sql, row, dataset)
    if gold_df is None:
        return None
    pred_df = _execute_sql(sql, row, dataset)
    if pred_df is None:
        return 0
    return 1 if _dataframes_equal(pred_df, gold_df) else 0


def _find_key(keys: List[str], needles: tuple[str, ...]) -> Optional[str]:
    for key in keys:
        lowered = key.lower()
        if any(needle in lowered for needle in needles):
            return key
    return None


def _sql_list(value: Any) -> List[str]:
    if isinstance(value, list):
        return [sql for sql in (_resolve_sql(item) for item in value) if sql]
    sql = _resolve_sql(value)
    return [sql] if sql else []


def _first_sql(value: Any) -> Optional[str]:
    sqls = _sql_list(value)
    return sqls[0] if sqls else None


def _diversity(sqls: List[str]) -> Optional[float]:
    if not sqls:
        return None
    return len(set(sqls)) / len(sqls)

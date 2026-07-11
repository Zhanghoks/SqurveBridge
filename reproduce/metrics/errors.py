"""错误根因分类器 — 对 EX=0 的样本沿决策树推断根因。

参考: 自进化反馈指标体系.md Layer 5
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from reproduce.metrics.sql_parser import SQLFeatureExtractor

# 所有可能的根因
ERROR_ROOTS = [
    "execution_error",            # SQL 无法执行
    "schema_linking_miss",        # Schema Link 漏了关键列
    "classification_error",       # 问题分类错误（仅适用时）
    "model_missing_join",         # 缺少 JOIN
    "model_extra_join",           # 多余 JOIN
    "model_missing_predicates",   # WHERE 条件不足
    "model_extra_predicates",     # 多余 WHERE 条件
    "model_missing_group_by",     # 缺少 GROUP BY
    "model_extra_group_by",       # 多余 GROUP BY
    "model_missing_columns",      # SELECT 缺少列
    "model_extra_columns",        # SELECT 多余列
    "model_avoids_subquery",      # 该用子查询但没用
    "model_substitutes_set_op",   # 用 NOT IN 替代 EXCEPT 等
    "model_wrong_order",          # ORDER BY 错误
    "model_wrong_keywords",       # 关键词使用错误
    "generation_error",           # 无法定位的生成错误
]


def classify_error(
        row: dict,
        pred_sql: Optional[str],
        gold_sql: Optional[str],
        cf1: Optional[Dict[str, float]],
        fd: Optional[Dict[str, int]],
        exec_error: Optional[str] = None,
        sl_recall: Optional[float] = None,
        pred_classification: Optional[str] = None,
        gold_classification: Optional[str] = None,
) -> Dict[str, Any]:
    """沿决策树推断单个 EX=0 样本的错误根因。

    Parameters
    ----------
    row : 样本行 dict
    pred_sql / gold_sql : 预测 SQL / gold SQL（已 resolve）
    cf1 : {"cf1_select": float, "...": float} 或 None
    fd : {"delta_join": int, ...} 或 None
    exec_error : SQL 执行错误信息（如果有）
    sl_recall : Schema Link recall（如果有）
    pred_classification / gold_classification : 分类标签（如果有）

    Returns
    -------
    {"error_root": str, "error_sub": str, "detail": dict}
    """

    detail: Dict[str, Any] = {}

    # Step 1: SQL 能否执行？
    if exec_error:
        sub = _classify_exec_error(exec_error)
        detail["exec_error"] = exec_error
        return {"error_root": "execution_error", "error_sub": sub, "detail": detail}

    # Step 2: 检查组件级匹配
    if cf1:
        # cf1_join
        join_f1 = cf1.get("cf1_join", 1.0)
        if join_f1 < 1.0:
            if fd:
                delta_join = fd.get("delta_join", 0)
                if delta_join > 0:
                    return {"error_root": "model_extra_join",
                            "error_sub": f"cf1_join={join_f1:.2f}", "detail": detail}
                elif delta_join < 0:
                    return {"error_root": "model_missing_join",
                            "error_sub": f"cf1_join={join_f1:.2f}", "detail": detail}
            return {"error_root": "model_missing_join",
                    "error_sub": f"cf1_join={join_f1:.2f}", "detail": detail}

        # cf1_select
        select_f1 = cf1.get("cf1_select", 1.0)
        if select_f1 < 1.0:
            if fd:
                delta_qf = fd.get("delta_query_fields", 0)
                if delta_qf > 0:
                    return {"error_root": "model_extra_columns",
                            "error_sub": f"cf1_select={select_f1:.2f}", "detail": detail}
                elif delta_qf < 0:
                    return {"error_root": "model_missing_columns",
                            "error_sub": f"cf1_select={select_f1:.2f}", "detail": detail}
            return {"error_root": "model_missing_columns",
                    "error_sub": f"cf1_select={select_f1:.2f}", "detail": detail}

        # cf1_where
        where_f1 = cf1.get("cf1_where", 1.0)
        if where_f1 < 1.0:
            if fd:
                delta_pred = fd.get("delta_predicate", 0)
                if delta_pred > 0:
                    return {"error_root": "model_extra_predicates",
                            "error_sub": f"cf1_where={where_f1:.2f}", "detail": detail}
                elif delta_pred < 0:
                    return {"error_root": "model_missing_predicates",
                            "error_sub": f"cf1_where={where_f1:.2f}", "detail": detail}
            return {"error_root": "model_missing_predicates",
                    "error_sub": f"cf1_where={where_f1:.2f}", "detail": detail}

        # cf1_group
        group_f1 = cf1.get("cf1_group", 1.0)
        if group_f1 < 1.0:
            # 检查 gold SQL 是否包含 GROUP BY
            if gold_sql:
                gold_parser = SQLFeatureExtractor(gold_sql)
                gold_feat = gold_parser.extract()
                if gold_feat.get("group_by", 0) > 0:
                    # gold 有 GROUP BY 但 pred 没匹配上
                    return {"error_root": "model_missing_group_by",
                            "error_sub": f"cf1_group={group_f1:.2f}", "detail": detail}
            # pred 多了 GROUP BY
            return {"error_root": "model_extra_group_by",
                    "error_sub": f"cf1_group={group_f1:.2f}", "detail": detail}

        # cf1_order
        order_f1 = cf1.get("cf1_order", 1.0)
        if order_f1 < 1.0:
            return {"error_root": "model_wrong_order",
                    "error_sub": f"cf1_order={order_f1:.2f}", "detail": detail}

        # cf1_iuen
        iuen_f1 = cf1.get("cf1_iuen", 1.0)
        if iuen_f1 < 1.0:
            if gold_sql and pred_sql:
                gold_parser = SQLFeatureExtractor(gold_sql)
                pred_parser = SQLFeatureExtractor(pred_sql)
                gold_feat = gold_parser.extract()
                pred_feat = pred_parser.extract()
                # gold 有子查询但 pred 没有
                if gold_feat.get("subquery", 0) > 0 and pred_feat.get("subquery", 0) == 0:
                    return {"error_root": "model_avoids_subquery",
                            "error_sub": f"cf1_iuen={iuen_f1:.2f}", "detail": detail}
                # gold 有集合操作但 pred 用 NOT IN 替代
                if gold_feat.get("set_operation", 0) > 0:
                    return {"error_root": "model_substitutes_set_op",
                            "error_sub": f"cf1_iuen={iuen_f1:.2f}", "detail": detail}
            return {"error_root": "model_avoids_subquery",
                    "error_sub": f"cf1_iuen={iuen_f1:.2f}", "detail": detail}

        # cf1_keywords
        kw_f1 = cf1.get("cf1_keywords", 1.0)
        if kw_f1 < 1.0:
            return {"error_root": "model_wrong_keywords",
                    "error_sub": f"cf1_keywords={kw_f1:.2f}", "detail": detail}

    # Step 3: Schema Linking 检查
    if sl_recall is not None and sl_recall < 0.5:
        detail["sl_recall"] = sl_recall
        return {"error_root": "schema_linking_miss",
                "error_sub": f"sl_recall={sl_recall:.2f}", "detail": detail}

    # Step 4: Classification 检查
    if pred_classification is not None and gold_classification is not None:
        if pred_classification != gold_classification:
            detail["pred_class"] = pred_classification
            detail["gold_class"] = gold_classification
            return {"error_root": "classification_error",
                    "error_sub": f"{pred_classification} vs {gold_classification}",
                    "detail": detail}

    # Step 5: 无法定位
    return {"error_root": "generation_error", "error_sub": "unknown", "detail": detail}


def _classify_exec_error(error_msg: str) -> str:
    """根据执行错误信息分类子类型。"""
    error_lower = error_msg.lower()
    if "syntax" in error_lower:
        return "syntax_error"
    if "no such column" in error_lower or "column" in error_lower:
        return "column_not_found"
    if "no such table" in error_lower or "table" in error_lower:
        return "table_not_found"
    if "ambiguous" in error_lower:
        return "ambiguous_column"
    if "timeout" in error_lower or "timed out" in error_lower:
        return "timeout"
    return "other_exec_error"

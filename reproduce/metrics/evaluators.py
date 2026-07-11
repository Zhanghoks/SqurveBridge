"""自定义评估函数 — 每个函数签名统一：

    eval_fn(rows: list[dict], dataset, row_index: int, **kwargs) -> float | dict | None

- `rows`：同一 question 的 generate_num 轮结果（list[dict]），rows[0] 是第一轮
- `dataset`：原始 Dataset 对象（提供 dataset.db_path, dataset.db_credential, dataset.get_db_schema）
- `row_index`：样本在 dataset 中的索引
- 返回 None 表示该样本无效
"""

from __future__ import annotations

import math
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd

from core.db_path import resolve_sqlite_file
from core.db_connect import get_sql_exec_result
from core.utils import load_dataset

from reproduce.metrics.sql_parser import SQLFeatureExtractor


# ==========================================================================
# 工具函数
# ==========================================================================

def _resolve_sql(raw: Any) -> Optional[str]:
    """Resolve SQL from a row value (string or file path)."""
    # 多候选场景（如 n_candidates > 1）：pred_sql 为路径列表，取首个候选评估
    if isinstance(raw, list):
        raw = raw[0] if raw else None
    if not isinstance(raw, str) or not raw.strip():
        return None
    try:
        path = Path(raw)
        if path.suffix in (".sql", ".txt"):
            return load_dataset(path)
        # 有时候 pred_sql 存的是相对路径但后缀不是 .sql
        if path.exists() and path.is_file():
            return load_dataset(path)
    except Exception:
        pass
    return raw


def _execute_sql(sql: str, row: dict, dataset) -> Optional[pd.DataFrame]:
    """执行一条 SQL，返回 DataFrame。失败返回 None。"""
    db_type = row.get("db_type", "sqlite")
    db_id = row.get("db_id", "")
    db_path = str(resolve_sqlite_file(dataset.db_path, db_id)) if db_type == "sqlite" else dataset.db_path
    credential = dataset.db_credential.get(db_type)

    args: Dict[str, Any] = {
        "db_type": db_type,
        "sql_query": sql,
    }
    if db_type == "sqlite":
        args["db_path"] = db_path
    else:
        args["db_id"] = db_id
    if credential:
        args["credential_path"] = credential

    df, err = get_sql_exec_result(**args)
    if err:
        return None
    return df if isinstance(df, pd.DataFrame) else None


def _dataframes_equal(a: pd.DataFrame, b: pd.DataFrame) -> bool:
    """两个 DataFrame 是否等价（copy from compare_pandas_table 的核心逻辑）。"""
    if a.shape != b.shape:
        return False
    if a.empty and b.empty:
        return True

    def _is_na(x):
        if x is None:
            return True
        try:
            return bool(pd.isna(x))
        except (ValueError, TypeError):
            return False

    # 结果行无序，但 tuple 内的列位置有语义，不能排序。
    def normalized_rows(df):
        rows = set()
        for _, row in df.iterrows():
            normalized = tuple(
                (None if _is_na(x) else round(x, 2) if isinstance(x, float) else x)
                for x in row
            )
            rows.add(normalized)
        return rows

    return normalized_rows(a) == normalized_rows(b)


# ==========================================================================
# 1. EM — Exact Set Match
# ==========================================================================

def eval_em(rows: List[dict], dataset, row_index: int = 0, **kwargs) -> Optional[int]:
    """Exact Set Match：SQL 7 组件全部精确匹配 → 1，否则 0。

    参考: MT-Teql eval_exact_match() / NL2SQL360 test_suite_sql_eval
    """
    row = rows[0]
    gold_sql = _resolve_sql(row.get("query"))
    pred_sql = _resolve_sql(row.get("pred_sql"))
    if not gold_sql or not pred_sql:
        return None

    gold_parser = SQLFeatureExtractor(gold_sql)
    pred_parser = SQLFeatureExtractor(pred_sql)

    gold_comps = gold_parser.parse_components()
    pred_comps = pred_parser.parse_components()

    if gold_comps is None or pred_comps is None:
        return None

    # 逐组件比较：是否完全相等
    all_match = True
    for comp in SQLFeatureExtractor.COMPONENTS:
        g = gold_comps.get(comp, set())
        p = pred_comps.get(comp, set())
        if g != p:
            all_match = False
            break

    return 1 if all_match else 0


# ==========================================================================
# 2. SF1 — Soft-F1（结果集列级模糊匹配）
# ==========================================================================

def _compute_soft_f1(pred_df: pd.DataFrame, gold_df: pd.DataFrame) -> float:
    """结果集的行级 + 列级模糊匹配 F1。

    参考: NL2SQL360 bird_eval/evaluation_f1.py
    """
    if pred_df.empty and gold_df.empty:
        return 1.0

    pred_rows = list({tuple(row) for _, row in pred_df.iterrows()})
    gold_rows = list({tuple(row) for _, row in gold_df.iterrows()})

    if not gold_rows:
        return 1.0 if not pred_rows else 0.0
    if not pred_rows:
        return 0.0

    def _values_match(a, b) -> bool:
        if a is None and b is None:
            return True
        try:
            if pd.isna(a) and pd.isna(b):
                return True
        except (ValueError, TypeError):
            pass
        if isinstance(a, float) and isinstance(b, float):
            return math.isclose(a, b, abs_tol=1e-2)
        return a == b

    match_scores = []
    pred_only_scores = []
    gold_only_scores = []

    for index, gold_row in enumerate(gold_rows):
        if index >= len(pred_rows):
            match_scores.append(0.0)
            gold_only_scores.append(1.0)
            continue

        pred_row = pred_rows[index]
        total_columns = len(gold_row)
        if total_columns == 0:
            match_scores.append(1.0)
            pred_only_scores.append(0.0)
            gold_only_scores.append(0.0)
            continue

        matches = sum(
            1 for pred_value in pred_row
            if any(_values_match(pred_value, gold_value) for gold_value in gold_row)
        )
        pred_only = sum(
            1 for pred_value in pred_row
            if not any(_values_match(pred_value, gold_value) for gold_value in gold_row)
        )
        gold_only = sum(
            1 for gold_value in gold_row
            if not any(_values_match(gold_value, pred_value) for pred_value in pred_row)
        )
        match_scores.append(matches / total_columns)
        pred_only_scores.append(pred_only / total_columns)
        gold_only_scores.append(gold_only / total_columns)

    for _ in range(len(pred_rows) - len(gold_rows)):
        match_scores.append(0.0)
        pred_only_scores.append(1.0)
        gold_only_scores.append(0.0)

    tp = sum(match_scores)
    fp = sum(pred_only_scores)
    fn = sum(gold_only_scores)

    precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0

    return f1


def eval_sf1(rows: List[dict], dataset, row_index: int = 0, **kwargs) -> Optional[float]:
    """Soft-F1：执行两条 SQL，对结果集计算行级/列级模糊匹配。"""
    row = rows[0]
    gold_sql = _resolve_sql(row.get("query"))
    pred_sql = _resolve_sql(row.get("pred_sql"))
    if not gold_sql or not pred_sql:
        return None

    gold_df = _execute_sql(gold_sql, row, dataset)
    if gold_df is None:
        return None

    pred_df = _execute_sql(pred_sql, row, dataset)
    if pred_df is None:
        return 0.0

    return _compute_soft_f1(pred_df, gold_df)


# ==========================================================================
# 3. VES — Valid Efficiency Score
# ==========================================================================

def _remove_outliers(values: List[float]) -> List[float]:
    """去掉超出 2σ 的异常值。"""
    if len(values) < 3:
        return values
    mean = sum(values) / len(values)
    std = math.sqrt(sum((v - mean) ** 2 for v in values) / len(values))
    if std == 0:
        return values
    return [v for v in values if abs(v - mean) <= 2 * std]


def eval_ves(rows: List[dict], dataset, row_index: int = 0, **kwargs) -> Optional[float]:
    """Valid Efficiency Score：正确 SQL 的执行效率评分。

    EX=0 → 0；EX=1 → 10 次执行测时比（去异常值 → 均值 → sqrt）。
    参考: NL2SQL360 bird_eval/bird_ves.py

    kwargs:
        ves_iterations (int): 测时轮数，默认 10
    """
    iterations = kwargs.get("ves_iterations", 10)
    row = rows[0]
    gold_sql = _resolve_sql(row.get("query"))
    pred_sql = _resolve_sql(row.get("pred_sql"))
    if not gold_sql or not pred_sql:
        return None

    db_type = row.get("db_type", "sqlite")
    db_id = row.get("db_id", "")
    db_path = str(resolve_sqlite_file(dataset.db_path, db_id)) if db_type == "sqlite" else dataset.db_path
    credential = dataset.db_credential.get(db_type)

    # 先验证正确性
    gold_df = _execute_sql(gold_sql, row, dataset)
    if gold_df is None:
        return None
    pred_df = _execute_sql(pred_sql, row, dataset)
    if pred_df is None:
        return 0.0
    if not _dataframes_equal(pred_df, gold_df):
        return 0.0

    # 多次测时
    ratios: List[float] = []
    base_args: Dict[str, Any] = {"db_type": db_type, "sql_query": ""}
    if db_type == "sqlite":
        base_args["db_path"] = db_path
    else:
        base_args["db_id"] = db_id
    if credential:
        base_args["credential_path"] = credential

    for _ in range(iterations):
        # pred 执行时间
        t1 = time.perf_counter()
        args_p = {**base_args, "sql_query": pred_sql}
        get_sql_exec_result(**args_p)
        t_pred = time.perf_counter() - t1

        # gold 执行时间
        t1 = time.perf_counter()
        args_g = {**base_args, "sql_query": gold_sql}
        get_sql_exec_result(**args_g)
        t_gold = time.perf_counter() - t1

        if t_pred > 1e-6:
            ratios.append(t_gold / t_pred)

    if not ratios:
        return 0.0

    ratios = _remove_outliers(sorted(ratios))
    if not ratios:
        return 0.0

    return math.sqrt(sum(ratios) / len(ratios))


def eval_rves(rows: List[dict], dataset, row_index: int = 0, **kwargs) -> Optional[float]:
    """Reward-based VES approximation.

    Correct and faster SQL gets higher reward; incorrect SQL gets 0. This mirrors
    the NL2SQL360/BIRD RVES role while reusing Squrve's local execution helpers.
    """
    ves = eval_ves(rows, dataset, row_index=row_index, **kwargs)
    if ves is None:
        return None
    if ves <= 0:
        return 0.0
    return min(1.0, ves)


# ==========================================================================
# 4. SC — Self-Consistency
# ==========================================================================

def eval_sc(rows: List[dict], dataset, row_index: int = 0, **kwargs) -> Optional[float]:
    """Self-Consistency：多次采样的执行结果一致性。

    SC = 两两结果一致的 pair 数 / 总 pair 数。
    generate_num < 2 时返回 None。
    """
    pred_sqls = []
    for r in rows:
        sql = _resolve_sql(r.get("pred_sql"))
        if sql:
            pred_sqls.append(sql)

    if len(pred_sqls) < 2:
        return None

    row0 = rows[0]
    # 执行所有 SQL
    results: List[Optional[pd.DataFrame]] = []
    for sql in pred_sqls:
        df = _execute_sql(sql, row0, dataset)
        results.append(df)

    valid = [(i, r) for i, r in enumerate(results) if r is not None]
    if len(valid) < 2:
        return 0.0

    matches = 0
    for i in range(len(valid)):
        for j in range(i + 1, len(valid)):
            if _dataframes_equal(valid[i][1], valid[j][1]):
                matches += 1

    # 分母用原始 pred_sqls 总数——失败的执行视为与任何其他结果不一致
    n = len(pred_sqls)
    total = n * (n - 1) / 2
    return matches / total if total > 0 else 0.0


# ==========================================================================
# 5. CF1 — Component F1
# ==========================================================================

def _f1(precision: float, recall: float) -> float:
    if precision + recall == 0:
        return 0.0
    return 2 * precision * recall / (precision + recall)


def _set_scores(gold: set, pred: set):
    """计算两个集合的 precision, recall, f1。

    两者都为空 → F1 = 1.0（都正确地产出了空集）。
    """
    if not gold and not pred:
        return 1.0, 1.0, 1.0
    intersection = gold & pred
    p = len(intersection) / len(pred) if pred else 0.0
    r = len(intersection) / len(gold) if gold else 0.0
    return p, r, _f1(p, r)


def eval_cf1(rows: List[dict], dataset, row_index: int = 0, **kwargs) -> Optional[Dict[str, float]]:
    """Component F1：7 个 SQL 组件各自独立打分。

    返回:
        {"cf1_select": float, "cf1_where": float, "cf1_group": float,
         "cf1_order": float, "cf1_join": float, "cf1_iuen": float,
         "cf1_keywords": float}
    """
    row = rows[0]
    gold_sql = _resolve_sql(row.get("query"))
    pred_sql = _resolve_sql(row.get("pred_sql"))
    if not gold_sql or not pred_sql:
        return None

    gold_parser = SQLFeatureExtractor(gold_sql)
    pred_parser = SQLFeatureExtractor(pred_sql)

    gold_comps = gold_parser.parse_components()
    pred_comps = pred_parser.parse_components()

    if gold_comps is None or pred_comps is None:
        return None

    result: Dict[str, float] = {}
    for comp in SQLFeatureExtractor.COMPONENTS:
        g = gold_comps.get(comp, set())
        p = pred_comps.get(comp, set())
        _, _, f1 = _set_scores(g, p)
        result[f"cf1_{comp}"] = f1

    return result


# ==========================================================================
# 6. FD — Feature Delta
# ==========================================================================

def eval_fd(rows: List[dict], dataset, row_index: int = 0, **kwargs) -> Optional[Dict[str, int]]:
    """Feature Delta：pred SQL 与 gold SQL 的 16 维结构差异。

    返回:
        {"delta_query_fields": int, "delta_join": int, ...}
        正值 = pred 比 gold 多，负值 = pred 比 gold 少
    """
    row = rows[0]
    gold_sql = _resolve_sql(row.get("query"))
    pred_sql = _resolve_sql(row.get("pred_sql"))
    if not gold_sql or not pred_sql:
        return None

    gold_features = SQLFeatureExtractor(gold_sql).extract()
    pred_features = SQLFeatureExtractor(pred_sql).extract()

    # 任一解析失败则跳过
    if any(v == -1 for v in gold_features.values()) or any(v == -1 for v in pred_features.values()):
        return None

    delta = SQLFeatureExtractor.compute_delta(gold_features, pred_features)
    return {f"delta_{k}": v for k, v in delta.items()}

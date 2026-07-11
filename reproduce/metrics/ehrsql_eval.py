"""EHR-SQL 2024 reliability evaluator.

Strictly ports scoring_program/scoring_utils.py and scoring_program/scoring.py
from the EHR-SQL 2024 candidate source code.

Primary metric: accuracy0 = penalize(reliability_scores, penalty=0)
  - Answerable + correct -> +1
  - Answerable + abstained (null) -> 0
  - Answerable + wrong -> -1  (floored to 0 under accuracy0)
  - Unanswerable + answered -> -1  (floored to 0 under accuracy0)
  - Unanswerable + abstained -> +1
"""

import sqlite3
import numpy as np
from ast import literal_eval
from typing import Dict, List, Tuple

from reproduce.metrics.ehrsql_postprocess import post_process_sql


# ── verbatim ports from scoring_program/scoring_utils.py ──────────────────────

def _process_item(item) -> str:
    """scoring_utils.process_item: round float, return str."""
    try:
        item = round(float(item), 3)
    except Exception:
        pass
    return str(item)


def _process_answer(ans) -> str:
    """scoring_utils.process_answer: normalise execution result to comparable string."""
    try:
        ans = literal_eval(ans)
    except Exception:
        pass
    if isinstance(ans, str):
        return ans
    # check only up to 100th record
    return str(sorted([[_process_item(c) for c in row] for row in ans])[:100])


def _execute_sql(sql: str, db_path: str):
    """scoring_utils.execute_sql."""
    con = sqlite3.connect(db_path)
    con.text_factory = lambda b: b.decode(errors='ignore')
    cur = con.cursor()
    result = cur.execute(sql).fetchall()
    con.close()
    return result


def _execute_sql_wrapper(key: str, sql: str, db_path: str, tag: str, skip_indicator: str = 'null'):
    """scoring_utils.execute_sql_wrapper."""
    assert tag in ('real', 'pred')
    if sql != skip_indicator:
        try:
            result = _execute_sql(sql, db_path)
        except Exception:
            result = f'error_{tag}'
        result = _process_answer(result)
        return (key, result)
    else:
        return (key, skip_indicator)


def execute_all(sql_dict: Dict[str, str], db_path: str, tag: str) -> Dict[str, str]:
    """scoring_utils.execute_all (sequential version)."""
    exec_result = {}
    for key, sql in sql_dict.items():
        exec_result[key] = _execute_sql_wrapper(key, sql, db_path, tag)[-1]
    return exec_result


def reliability_score(
    real_result: Dict[str, str],
    pred_result: Dict[str, str],
    return_dict: bool = False,
) -> List[int]:
    """Verbatim port of scoring_utils.reliability_score."""
    scores: List[int] = []
    scores_dict: Dict[str, int] = {}
    for key in real_result:
        ans_real = real_result[key]
        ans_pred = pred_result[key]
        exec_acc = (ans_real == ans_pred)

        if ans_real != 'null' and exec_acc:
            score = 1
        elif ans_real != 'null' and ans_pred == 'null':
            score = 0
        elif ans_real != 'null' and not exec_acc:
            score = -1
        elif ans_real == 'null' and ans_pred != 'null':
            score = -1
        elif ans_real == 'null' and ans_pred == 'null':
            score = 1
        else:
            raise NotImplementedError(f"Unhandled case: real={ans_real!r}, pred={ans_pred!r}")

        scores.append(score)
        scores_dict[key] = score

    if return_dict:
        return scores, scores_dict
    return scores


def penalize(scores: List[int], penalty: int = 1) -> float:
    """Verbatim port of scoring_utils.penalize."""
    return float(np.mean([score * penalty if score == -1 else score for score in scores]))


# ── Squrve evaluator entry point ──────────────────────────────────────────────

def ehrsql_evaluate(
    gold_dict: Dict[str, str],
    pred_dict: Dict[str, str],
    db_path: str,
) -> Dict[str, float]:
    """
    Compute EHR-SQL 2024 reliability scores.

    Args:
        gold_dict: {instance_id: gold_sql_or_null}
        pred_dict: {instance_id: pred_sql_or_null}
        db_path:   path to mimic_iv.sqlite

    Returns:
        {
          'accuracy0':  float,   # primary metric
          'accuracy5':  float,
          'accuracy10': float,
          'accuracyN':  float,
        }
    """
    # Apply source post-processing before execution (verbatim from scoring.py)
    real_dict = {k: post_process_sql(v) for k, v in gold_dict.items()}
    pred_dict = {k: post_process_sql(v) for k, v in pred_dict.items()}

    real_result = execute_all(real_dict, db_path, tag='real')
    pred_result = execute_all(pred_dict, db_path, tag='pred')

    scores = reliability_score(real_result, pred_result)
    n = len(scores)

    return {
        'accuracy0':  penalize(scores, penalty=0) * 100,
        'accuracy5':  penalize(scores, penalty=5) * 100,
        'accuracy10': penalize(scores, penalty=10) * 100,
        'accuracyN':  penalize(scores, penalty=n) * 100,
    }

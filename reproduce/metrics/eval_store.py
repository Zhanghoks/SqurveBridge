"""SQLite evaluation store for cross-run metric queries."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any, Optional


def persist_eval_store(scores: dict[str, Any], db_path: str | Path) -> Path:
    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(db_path) as conn:
        _init_schema(conn)
        _insert_run(conn, scores)
        _insert_samples(conn, scores)
        conn.commit()
    return db_path


def _init_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS runs (
            run_id TEXT PRIMARY KEY,
            method TEXT,
            dataset TEXT,
            split TEXT,
            generate_num INTEGER,
            scope TEXT,
            timestamp TEXT,
            scores_json TEXT
        );
        CREATE TABLE IF NOT EXISTS samples (
            run_id TEXT,
            instance_id TEXT,
            db_id TEXT,
            db_type TEXT,
            hardness TEXT,
            question TEXT,
            gold_sql TEXT,
            pred_sql TEXT,
            ex REAL,
            em REAL,
            sf1 REAL,
            sc REAL,
            ves REAL,
            rves REAL,
            error_root TEXT,
            workflow_root_stage TEXT,
            workflow_reason TEXT,
            PRIMARY KEY (run_id, instance_id)
        );
        CREATE TABLE IF NOT EXISTS sql_features (
            run_id TEXT,
            instance_id TEXT,
            feature TEXT,
            gold_value REAL,
            pred_value REAL,
            delta_value REAL,
            PRIMARY KEY (run_id, instance_id, feature)
        );
        CREATE TABLE IF NOT EXISTS stage_metrics (
            run_id TEXT,
            instance_id TEXT,
            stage_id TEXT,
            task_type TEXT,
            actor_class TEXT,
            status TEXT,
            metric_name TEXT,
            metric_value REAL,
            PRIMARY KEY (run_id, instance_id, stage_id, metric_name)
        );
        """
    )


def _insert_run(conn: sqlite3.Connection, scores: dict) -> None:
    conn.execute(
        """
        INSERT OR REPLACE INTO runs
        (run_id, method, dataset, split, generate_num, scope, timestamp, scores_json)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            scores.get("run_id"),
            scores.get("method"),
            scores.get("dataset"),
            scores.get("split"),
            scores.get("generate_num"),
            scores.get("scope"),
            scores.get("timestamp"),
            json.dumps({k: v for k, v in scores.items() if k != "per_sample"}, ensure_ascii=False),
        ),
    )


def _insert_samples(conn: sqlite3.Connection, scores: dict) -> None:
    run_id = scores.get("run_id")
    conn.execute("DELETE FROM samples WHERE run_id = ?", (run_id,))
    conn.execute("DELETE FROM sql_features WHERE run_id = ?", (run_id,))
    conn.execute("DELETE FROM stage_metrics WHERE run_id = ?", (run_id,))
    for sample in scores.get("per_sample") or []:
        workflow_attr = ((sample.get("workflow") or {}).get("attribution") or {})
        conn.execute(
            """
            INSERT OR REPLACE INTO samples
            (run_id, instance_id, db_id, db_type, hardness, question, gold_sql, pred_sql,
             ex, em, sf1, sc, ves, rves, error_root, workflow_root_stage, workflow_reason)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                run_id,
                sample.get("instance_id"),
                sample.get("db_id"),
                sample.get("db_type"),
                sample.get("hardness"),
                sample.get("question"),
                sample.get("gold_sql"),
                sample.get("pred_sql"),
                _num(sample.get("ex")),
                _num(sample.get("em")),
                _num(sample.get("sf1")),
                _num(sample.get("sc")),
                _num(sample.get("ves")),
                _num(sample.get("rves")),
                sample.get("error_root"),
                workflow_attr.get("root_stage"),
                workflow_attr.get("reason"),
            ),
        )
        _insert_sql_features(conn, run_id, sample)
        _insert_stage_metrics(conn, run_id, sample)


def _insert_sql_features(conn: sqlite3.Connection, run_id: str, sample: dict) -> None:
    features = sample.get("sql_features") or {}
    gold = features.get("gold") or {}
    pred = features.get("pred") or {}
    delta = features.get("delta") or {}
    for feature in sorted(set(gold) | set(pred) | set(delta)):
        conn.execute(
            """
            INSERT OR REPLACE INTO sql_features
            (run_id, instance_id, feature, gold_value, pred_value, delta_value)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                run_id,
                sample.get("instance_id"),
                feature,
                _num(gold.get(feature)),
                _num(pred.get(feature)),
                _num(delta.get(feature)),
            ),
        )


def _insert_stage_metrics(conn: sqlite3.Connection, run_id: str, sample: dict) -> None:
    stages = ((sample.get("workflow") or {}).get("stages") or {})
    for stage_id, payload in stages.items():
        metrics = payload.get("metrics") or {}
        if not metrics:
            metrics = {"__status__": None}
        for metric_name, metric_value in metrics.items():
            conn.execute(
                """
                INSERT OR REPLACE INTO stage_metrics
                (run_id, instance_id, stage_id, task_type, actor_class, status, metric_name, metric_value)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    sample.get("instance_id"),
                    stage_id,
                    payload.get("task_type"),
                    payload.get("actor_class"),
                    payload.get("status"),
                    metric_name,
                    _num(metric_value),
                ),
            )


def _num(value: Any) -> Optional[float]:
    if isinstance(value, bool):
        return 1.0 if value else 0.0
    if isinstance(value, (int, float)):
        return float(value)
    return None

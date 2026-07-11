"""RESDSQL reducer for Spider-style schemas.

Consumes RESDSQLParser scores and builds the ranked input_sequence used by the
SQL generation actor. Candidate code is treated as algorithm reference only.
"""

import json
import re
import sqlite3
from os import PathLike
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

import pandas as pd
from loguru import logger

from core.actor.reducer.BaseReduce import BaseReducer
from core.data_manage import Dataset, save_dataset, single_central_process
from core.db_path import resolve_sqlite_file
from core.utils import load_dataset


@BaseReducer.register_actor
class RESDSQLReducer(BaseReducer):
    """Build RESDSQL ranked schema sequences from parser scores."""

    NAME = "RESDSQLReducer"

    def __init__(
        self,
        dataset: Optional[Dataset] = None,
        llm: Any = None,
        output_format: str = "dict",
        is_save: bool = True,
        save_dir: Union[str, PathLike] = "../files/instance_schemas",
        db_path: Optional[Union[str, PathLike]] = None,
        top_k_tables: int = 4,
        top_k_columns: int = 5,
        use_contents: bool = True,
        add_fk_info: bool = True,
        target_type: str = "sql",
        **kwargs,
    ):
        self.dataset = dataset
        self.llm = llm
        self.output_format = output_format
        self.is_save = is_save
        self.save_dir = save_dir
        self.db_path = db_path or (getattr(dataset, "db_path", None) if dataset else None)
        self.top_k_tables = max(1, int(top_k_tables))
        self.top_k_columns = max(1, int(top_k_columns))
        self.use_contents = use_contents
        self.add_fk_info = add_fk_info
        self.target_type = target_type

    @staticmethod
    def _schema_to_records(schema: Union[pd.DataFrame, Dict, List]) -> List[Dict]:
        if isinstance(schema, dict):
            schema = single_central_process(schema)
        if isinstance(schema, pd.DataFrame):
            return schema.to_dict("records")
        return list(schema or [])

    @staticmethod
    def _filter_records_for_db(records: List[Dict], db_id: str) -> List[Dict]:
        if not db_id:
            return records
        scoped = [row for row in records if row.get("db_id") == db_id]
        return scoped if scoped else records

    def _resolve_db_file(self, db_id: str) -> Optional[Path]:
        if not self.db_path:
            return None
        path = resolve_sqlite_file(self.db_path, db_id)
        return path if path.exists() else None

    @staticmethod
    def _load_schema_links(value: Any) -> Dict[str, Any]:
        if isinstance(value, dict):
            return value
        if isinstance(value, (str, PathLike)) and Path(value).exists():
            loaded = load_dataset(value)
            return loaded if isinstance(loaded, dict) else {}
        return {}

    @staticmethod
    def _group_schema(records: List[Dict]) -> Dict[str, List[Dict]]:
        grouped: Dict[str, List[Dict]] = {}
        for row in records:
            table = str(row.get("table_name_original") or row.get("table_name") or "")
            column = str(row.get("column_name_original") or row.get("column_name") or "")
            if table and column:
                grouped.setdefault(table, []).append(row)
        return grouped

    def _get_contents(self, db_file: Optional[Path], table: str, column: str) -> List[str]:
        if not self.use_contents or not db_file:
            return []
        try:
            conn = sqlite3.connect(str(db_file))
            conn.text_factory = lambda b: b.decode(errors="ignore")
            cursor = conn.cursor()
            cursor.execute(
                f'SELECT DISTINCT "{column}" FROM "{table}" WHERE "{column}" IS NOT NULL LIMIT 2'
            )
            rows = [str(row[0]) for row in cursor.fetchall() if row[0] is not None]
            conn.close()
            return rows
        except Exception as exc:
            logger.debug(f"{self.NAME}: db contents failed for {table}.{column}: {exc}")
            return []

    @staticmethod
    def _foreign_keys(records: List[Dict], selected_tables: set) -> List[Dict[str, str]]:
        fks: List[Dict[str, str]] = []
        for row in records:
            source_table = str(row.get("table_name_original") or row.get("table_name") or "")
            source_column = str(row.get("column_name_original") or row.get("column_name") or "")
            raw = row.get("foreign_key") or ""
            if not raw or source_table not in selected_tables:
                continue
            for target in re.findall(r"\[(.*?)\]", str(raw)):
                match = re.match(r"\s*([^.()]+)[.(]([^)]+)\)?\s*", target)
                if not match:
                    continue
                target_table, target_column = match.group(1), match.group(2)
                if target_table in selected_tables:
                    fks.append(
                        {
                            "source_table_name_original": source_table,
                            "source_column_name_original": source_column,
                            "target_table_name_original": target_table,
                            "target_column_name_original": target_column,
                        }
                    )
        return fks

    def _rank_schema(
        self,
        question: str,
        db_id: str,
        records: List[Dict],
        scores: Dict[str, Any],
    ) -> Dict[str, Any]:
        grouped = self._group_schema(records)
        table_scores = scores.get("table_scores", {})
        column_scores = scores.get("column_scores", {})

        table_names = list(grouped)
        ranked_tables = sorted(
            table_names,
            key=lambda table: (-float(table_scores.get(table, 0.0)), table_names.index(table)),
        )[: self.top_k_tables]
        db_file = self._resolve_db_file(db_id)

        ranked_schema = []
        tc_original = []
        sequence = question
        for table in ranked_tables:
            rows = grouped[table]
            ranked_rows = sorted(
                rows,
                key=lambda row: (
                    -float(
                        column_scores.get(
                            f"{table}.{row.get('column_name_original') or row.get('column_name')}",
                            0.0,
                        )
                    ),
                    rows.index(row),
                ),
            )[: self.top_k_columns]

            column_entries = []
            table_info = {
                "table_name_original": table,
                "column_names_original": [],
                "db_contents": [],
            }
            for row in ranked_rows:
                column = str(row.get("column_name_original") or row.get("column_name"))
                contents = self._get_contents(db_file, table, column)
                table_info["column_names_original"].append(column)
                table_info["db_contents"].append(contents)
                tc_original.append(f"{table}.{column}")
                if contents:
                    column_entries.append(f"{table}.{column} ( {' , '.join(contents)} )")
                else:
                    column_entries.append(f"{table}.{column}")
            if self.target_type == "natsql":
                column_entries.append(f"{table}.*")
                tc_original.append(f"{table}.*")
            sequence += " | " + table + " : " + " , ".join(column_entries)
            ranked_schema.append(table_info)

        fks = self._foreign_keys(records, set(ranked_tables)) if self.add_fk_info else []
        for fk in fks:
            sequence += (
                " | "
                + fk["source_table_name_original"]
                + "."
                + fk["source_column_name_original"]
                + " = "
                + fk["target_table_name_original"]
                + "."
                + fk["target_column_name_original"]
            )
        while "  " in sequence:
            sequence = sequence.replace("  ", " ")

        return {
            "db_id": db_id,
            "input_sequence": sequence,
            "tc_original": tc_original,
            "ranked_schema": ranked_schema,
            "fk": fks,
        }

    def _save_output(self, output: Dict[str, Any], item, instance_id: Optional[str] = None):
        if not self.is_save:
            if self.dataset:
                self.dataset.setitem(item, "instance_schemas", output)
            return output
        instance_id = instance_id or str(item)
        save_path = Path(self.save_dir)
        if self.dataset and getattr(self.dataset, "dataset_index", None):
            save_path = save_path / str(self.dataset.dataset_index)
        save_path = save_path / f"{self.NAME}_{instance_id}.json"
        save_dataset(output, new_data_source=save_path)
        if self.dataset:
            self.dataset.setitem(item, "instance_schemas", str(save_path))
        return output

    def act(
        self,
        item,
        schema: Union[str, PathLike, Dict, List] = None,
        schema_links: Any = None,
        data_logger=None,
        **kwargs,
    ):
        row = self.dataset[item]
        if isinstance(schema, (str, PathLike)) and Path(schema).exists():
            schema = load_dataset(schema)
        if schema is None:
            schema = self.dataset.get_db_schema(item)
        if schema_links is None:
            schema_links = row.get("schema_links")
        scores = self._load_schema_links(schema_links)
        db_id = row.get("db_id", "")
        records = self._filter_records_for_db(self._schema_to_records(schema), db_id)
        output = self._rank_schema(row.get("question", ""), db_id, records, scores)
        if data_logger:
            data_logger.info(f"{self.NAME}.input_sequence_len={len(output['input_sequence'])}")
        return self._save_output(output, item, row.get("instance_id"))

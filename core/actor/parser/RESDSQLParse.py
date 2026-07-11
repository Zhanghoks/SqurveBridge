"""RESDSQL parser for Spider-style schemas.

This actor replaces RESDSQL's checkpoint-backed schema item classifier with a
Squrve-native LLM scoring step plus a deterministic lexical fallback. It does
not import candidate repository code.
"""

import json
import re
from os import PathLike
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

import pandas as pd
from loguru import logger

from core.actor.parser.BaseParse import BaseParser
from core.data_manage import Dataset, single_central_process
from core.utils import load_dataset


CLASSIFIER_PROMPT = """You are adapting RESDSQL schema item classification.
Score every table and column for the question.

Question: "{question}"

Schema:
{schema_text}

Return only JSON:
{{
  "tables": [{{"name": "table", "score": 0.0}}],
  "columns": [{{"name": "table.column", "score": 0.0}}]
}}"""


@BaseParser.register_actor
class RESDSQLParser(BaseParser):
    """RESDSQL schema item classifier implemented as a Squrve parser."""

    NAME = "RESDSQLParser"

    def __init__(
        self,
        dataset: Optional[Dataset] = None,
        llm: Any = None,
        output_format: str = "dict",
        is_save: bool = True,
        save_dir: Union[str, PathLike] = "../files/schema_links",
        top_k_tables: int = 4,
        top_k_columns: int = 5,
        **kwargs,
    ):
        super().__init__(dataset, llm, output_format, is_save, save_dir, **kwargs)
        self.top_k_tables = max(1, int(top_k_tables))
        self.top_k_columns = max(1, int(top_k_columns))

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

    @staticmethod
    def _tokens(text: str) -> set:
        return {tok for tok in re.split(r"[^a-z0-9]+", str(text).lower()) if tok}

    def _build_schema_text(self, records: List[Dict]) -> str:
        tables: Dict[str, List[str]] = {}
        for row in records:
            table = row.get("table_name_original") or row.get("table_name")
            column = row.get("column_name_original") or row.get("column_name")
            if table and column:
                tables.setdefault(str(table), []).append(str(column))
        return "\n".join(f"- {table}: {', '.join(cols)}" for table, cols in tables.items())

    def _lexical_scores(self, question: str, records: List[Dict]) -> Dict[str, Any]:
        q_tokens = self._tokens(question)
        table_order: List[str] = []
        column_scores: Dict[str, float] = {}
        table_scores: Dict[str, float] = {}

        for row in records:
            table = str(row.get("table_name_original") or row.get("table_name") or "")
            column = str(row.get("column_name_original") or row.get("column_name") or "")
            if not table or not column:
                continue
            if table not in table_order:
                table_order.append(table)

            haystack = " ".join(
                str(row.get(key, ""))
                for key in (
                    "table_name",
                    "table_name_original",
                    "column_name",
                    "column_name_original",
                    "column_descriptions",
                    "column_types",
                )
            )
            overlap = len(q_tokens & self._tokens(haystack))
            score = 0.01 + overlap
            if column.lower() in question.lower():
                score += 2.0
            if table.lower() in question.lower():
                score += 1.0
            column_scores[f"{table}.{column}"] = float(score)
            table_scores[table] = max(table_scores.get(table, 0.0), float(score))

        max_table = max(table_scores.values(), default=1.0)
        max_col = max(column_scores.values(), default=1.0)
        column_pairs: List[tuple] = []
        for row in records:
            table = str(row.get("table_name_original") or row.get("table_name") or "")
            column = str(row.get("column_name_original") or row.get("column_name") or "")
            if not table or not column:
                continue
            column_pairs.append((table, column))
        return {
            "table_pred_probs": [
                round(table_scores.get(table, 0.0) / max_table, 4) for table in table_order
            ],
            "column_pred_probs": [
                round(column_scores.get(f"{table}.{column}", 0.0) / max_col, 4)
                for table, column in column_pairs
            ],
            "table_scores": table_scores,
            "column_scores": column_scores,
        }

    def _llm_scores(self, question: str, records: List[Dict]) -> Optional[Dict[str, Any]]:
        llm = self.get_llm()
        if llm is None:
            return None
        prompt = CLASSIFIER_PROMPT.format(
            question=question,
            schema_text=self._build_schema_text(records),
        )
        try:
            response = llm.complete(prompt)
            text = getattr(response, "text", str(response)).strip()
            data = json.loads(text)
        except Exception as exc:
            logger.debug(f"{self.NAME}: classifier LLM output not usable: {exc}")
            return None

        table_scores = {
            str(item.get("name")): float(item.get("score", 0.0))
            for item in data.get("tables", [])
            if item.get("name")
        }
        column_scores = {
            str(item.get("name")): float(item.get("score", 0.0))
            for item in data.get("columns", [])
            if item.get("name")
        }
        if not table_scores and not column_scores:
            return None
        return {"table_scores": table_scores, "column_scores": column_scores}

    def _build_output(self, question: str, records: List[Dict]) -> Dict[str, Any]:
        lexical = self._lexical_scores(question, records)
        llm_scores = self._llm_scores(question, records)
        if llm_scores:
            lexical["table_scores"].update(llm_scores.get("table_scores", {}))
            lexical["column_scores"].update(llm_scores.get("column_scores", {}))
        lexical["top_k_tables"] = self.top_k_tables
        lexical["top_k_columns"] = self.top_k_columns
        return lexical

    def act(
        self,
        item,
        schema: Union[str, PathLike, Dict, List] = None,
        data_logger=None,
        update_dataset=True,
        **kwargs,
    ):
        row = self.dataset[item]
        question = row.get("question", "")

        if isinstance(schema, (str, PathLike)) and Path(schema).exists():
            schema = load_dataset(schema)
        if schema is None:
            schema = self.dataset.get_db_schema(item)
        records = self._filter_records_for_db(self._schema_to_records(schema), row.get("db_id", ""))
        output = self._build_output(question, records)

        if update_dataset:
            self.save_output(output, item, row.get("instance_id"), file_ext=".json")
        if data_logger:
            data_logger.info(f"{self.NAME}.schema_scores | tables={len(output.get('table_scores', {}))}")
        return output

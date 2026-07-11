"""DIN-SQL BookSQL Selector -- self-repair debug pass for BookSQL.

One LLM call: debugger prompt (7-rule self-repair) -> cleaned SQL.

The debugger prompt is ported from candidates/BookSQL-main/GPT/DIN-SQL.py lines 461-476.
Schema fields and foreign keys are built from the dataset schema using helpers
imported from DINSQLBooksqlReduce.
"""

from typing import Any, Dict, List, Union, Optional
from os import PathLike
from loguru import logger

from core.actor.selector.BaseSelect import BaseSelector
from core.data_manage import Dataset
from core.utils import sql_clean
from core.actor.reducer.DINSQLBooksqlReduce import (
    find_fields_mysql_like,
    find_foreign_keys_mysql_like,
)


@BaseSelector.register_actor
class DINSQLBooksqlSelector(BaseSelector):
    """DIN-SQL selector for BookSQL: one LLM debug/self-repair pass.

    Applies the 7-rule debugger prompt from DIN-SQL.py to the candidate SQL,
    asking the LLM to fix any issues while keeping the output SQL only.
    """

    NAME = "DINSQLBooksqlSelector"

    SKILL = """# DINSQLBooksqlSelector

DIN-SQL self-repair selector for BookSQL. One LLM call with the 7-rule debugger prompt.

## Inputs
- pred_sql: candidate SQL from DINSQLBooksqlGenerator
- schema: database schema for the item

## Output
Final corrected SQL
"""

    DEBUG_INSTRUCTION = (
        "#### For the given question, use the provided tables, columns, foreign keys, and primary keys "
        "to fix the given SQLite SQL QUERY for any issues. If there are any problems, fix them. "
        "If there are no issues, return the SQLite SQL QUERY as is.\n"
        "#### Use the following instructions for fixing the SQL QUERY:\n"
        "1) Use the database values that are explicitly mentioned in the question.\n"
        "2) Pay attention to the columns that are used for the JOIN by using the Foreign_keys.\n"
        "3) Use DESC and DISTINCT when needed.\n"
        "4) Pay attention to the columns that are used for the GROUP BY statement.\n"
        "5) Pay attention to the columns that are used for the SELECT statement.\n"
        "6) Only change the GROUP BY clause when necessary (Avoid redundant columns in GROUP BY).\n"
        "7) Use GROUP BY on one column only.\n\n"
    )

    def __init__(
        self,
        dataset: Dataset = None,
        llm: Any = None,
        is_save: bool = True,
        save_dir: Union[str, PathLike] = "../files/pred_sql",
        **kwargs,
    ):
        super().__init__(dataset, llm, is_save, save_dir, **kwargs)

    def _debug_prompt_maker(
        self,
        question: str,
        fields: str,
        foreign_keys: str,
        sql: str,
    ) -> str:
        return (
            self.DEBUG_INSTRUCTION
            + fields
            + "Foreign_keys = " + foreign_keys + "\n"
            + "#### Question: " + question + "\n"
            + "#### Original SQLite SQL QUERY\n"
            + sql + "\n"
            + "#### Output only the fixed SQL query, without any explanation or extra text:"
        )

    def act(
        self,
        item,
        schema: Union[str, PathLike, Dict, List] = None,
        pred_sql: Union[str, PathLike, List[str]] = None,
        data_logger=None,
        **kwargs,
    ) -> str:
        if data_logger:
            data_logger.info(f"{self.NAME}.act start | item={item}")

        row = self.dataset[item]
        question = row["question"]
        instance_id = row.get("instance_id", str(item))

        # Load pred_sql -- take first element from list
        sql_list = self.load_pred_sql(pred_sql, item)
        if not sql_list:
            logger.warning(f"[{self.NAME}] No pred_sql for item {item}")
            return ""
        raw_sql = sql_list[0] if isinstance(sql_list, list) else sql_list
        if not raw_sql:
            raw_sql = "SELECT 1"

        # Load actual db schema (schema kwarg carries reducer output, not db schema)
        schema_items = self.dataset.get_db_schema(item)
        if schema_items is None:
            raise ValueError(f"No schema for item {item}")
        if isinstance(schema_items, dict):
            from core.data_manage import single_central_process
            schema_items = single_central_process(schema_items)

        fields = find_fields_mysql_like(schema_items)
        foreign_keys = find_foreign_keys_mysql_like(schema_items, row)

        # Build and run debug prompt
        prompt = self._debug_prompt_maker(question, fields, foreign_keys, raw_sql)

        if data_logger:
            data_logger.info(f"{self.NAME}.debug_prompt | preview={prompt[:200]}")

        llm = self.llm
        if llm is None:
            raise ValueError("LLM not initialised")

        output = llm.complete(prompt).text.strip()

        # Normalise: collapse newlines；仅在模型未自带 SELECT 前缀时补全，避免 "SELECT SELECT ..."
        result = output.replace("\n", " ").strip()
        if not result.lower().startswith("select"):
            result = "SELECT " + result
        result = sql_clean(result)

        if data_logger:
            data_logger.info(f"{self.NAME}.final_sql | {result}")

        result = self.save_result(result, item, instance_id)

        if data_logger:
            data_logger.info(f"{self.NAME}.act end | item={item}")

        return result

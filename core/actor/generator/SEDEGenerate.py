import re
import time
from typing import Union, Dict, List, Optional
from pathlib import Path
from os import PathLike
import pandas as pd
from loguru import logger

from llama_index.core.llms.llm import LLM

from core.actor.generator.BaseGenerate import BaseGenerator
from core.data_manage import Dataset, single_central_process, load_dataset
from core.utils import save_dataset, sql_clean


@BaseGenerator.register_actor
class SEDEGenerator(BaseGenerator):
    """SEDE text-to-SQL generator for BookSQL.

    Single LLM call: source_text (NL question + schema) → SQL.
    Replaces T5ForConditionalGeneration.generate() from SEDE/src/models/t5.py:126.
    Includes inline OOV repair and SQL normalization (fix_oov + preprocess_for_jsql).
    """

    NAME = "SEDEGenerator"

    SKILL = """# SEDEGenerator

SEDE collapses schema linking and SQL generation into a single LLM call.
The NL question (with schema context) is passed directly to the LLM which
generates SQL in one forward pass. No multi-stage decomposition.

## Inputs
- `instance_schemas`: source_text string (question + schema) from SEDEReducer,
  or falls back to formatting schema inline.

## Output
`pred_sql`

## Steps
1. Load source_text from instance_schemas or format inline.
2. Build generation prompt.
3. Single LLM call → raw SQL.
4. Post-process: fix_oov + normalize SQL.
5. Save and return pred_sql.
"""

    def __init__(
        self,
        dataset: Optional[Dataset] = None,
        llm: Optional[LLM] = None,
        is_save: bool = True,
        save_dir: Union[str, PathLike] = "../files/pred_sql",
        max_retries: int = 3,
        **kwargs,
    ):
        self.dataset = dataset
        self.llm = llm
        self.is_save = is_save
        self.save_dir = save_dir
        self.max_retries = max_retries

    @staticmethod
    def fix_oov(text: str) -> str:
        """Replace T5 OOV artefacts: ⁇ and <unk> → <."""
        return text.replace("⁇", "<").replace("<unk>", "<")

    @staticmethod
    def normalize_sql(sql: str) -> str:
        """Light SQL normalization: strip trailing semicolons, collapse whitespace."""
        sql = sql.strip().rstrip(";").strip()
        # Collapse internal whitespace runs
        sql = re.sub(r"\s+", " ", sql)
        # Remove bracket-style aliases like [alias]
        sql = re.sub(r"\[(\w+)\]", r"\1", sql)
        return sql

    def build_prompt(self, source_text: str) -> str:
        """Build the generation prompt from source_text."""
        return (
            "Translate the following question to a valid SQLite SQL query.\n"
            "Return only the SQL query with no explanation.\n\n"
            f"{source_text}\n\n"
            "SQL:"
        )

    def llm_generate(self, prompt: str) -> str:
        """Call LLM with retry and exponential backoff."""
        if self.llm is None:
            raise ValueError("LLM not initialized")
        for attempt in range(self.max_retries):
            try:
                response = self.llm.complete(prompt)
                return response.text.strip()
            except Exception as e:
                logger.warning(f"{self.NAME}: LLM attempt {attempt + 1} failed: {e}")
                if attempt < self.max_retries - 1:
                    time.sleep(2 ** attempt)
                else:
                    raise

    def act(
        self,
        item,
        schema: Union[str, PathLike, Dict, List] = None,
        schema_links=None,
        sub_questions=None,
        data_logger=None,
        **kwargs,
    ) -> str:
        if data_logger:
            data_logger.info(f"{self.NAME}.act start | item={item}")

        row = self.dataset[item]

        # Load source_text from instance_schemas (set by SEDEReducer) or build inline
        source_text = None
        instance_schema_ref = row.get("instance_schemas")
        if instance_schema_ref:
            if Path(str(instance_schema_ref)).exists():
                loaded = load_dataset(instance_schema_ref)
                if isinstance(loaded, dict):
                    source_text = loaded.get("source_text")
                elif isinstance(loaded, str):
                    source_text = loaded
            elif isinstance(instance_schema_ref, str):
                source_text = instance_schema_ref

        if not source_text:
            # Fallback: format inline from schema
            question = row.get("question", "")
            if schema is None:
                schema = self.dataset.get_db_schema(item)
            if isinstance(schema, dict):
                schema = single_central_process(schema)
            if isinstance(schema, list):
                schema = pd.DataFrame(schema)
            if isinstance(schema, pd.DataFrame):
                tables: Dict[str, List[str]] = {}
                for r in schema.to_dict(orient="records"):
                    t = str(r.get("table_name", r.get("table", "")))
                    c = str(r.get("column_name", r.get("column", "")))
                    tables.setdefault(t, []).append(c)
                schema_str = "\n".join(
                    f"Table: {t} | Columns: {', '.join(cols)}"
                    for t, cols in tables.items()
                )
                source_text = f"{question}\n\nSchema:\n{schema_str}"
            else:
                source_text = question

        # Build prompt and call LLM
        prompt = self.build_prompt(source_text)
        logger.info(f"{self.NAME}: generating SQL for item {item}")
        raw_sql = self.llm_generate(prompt)

        # Post-process: fix OOV, normalize, clean
        sql = self.fix_oov(raw_sql)
        sql = self.normalize_sql(sql)
        sql = sql_clean(sql)

        if data_logger:
            data_logger.info(f"{self.NAME}.pred_sql | sql={sql}")

        sql = self.save_output(sql, item, row.get("instance_id"))

        if data_logger:
            data_logger.info(f"{self.NAME}.act end | item={item}")
        return sql

"""UNISAR BookSQL Generator — LLM-based SQL generation from SLML input.

Takes the SLML question string and alias_schema produced by UNISARBooksqlReducer
and calls the LLM once to produce SQL in table@column notation.

Replaces the original GENRE/mbart_large beam-search decoder with a single
LLM completion call. Includes post-hoc validation to strip invalid schema refs.
"""

import re
import time
from os import PathLike
from typing import Union, Dict, List, Optional

from loguru import logger

from core.actor.generator.BaseGenerate import BaseGenerator
from core.data_manage import Dataset
from core.utils import load_dataset, sql_clean


PROMPT_TEMPLATE = """\
You are a SQL generator. Given a schema-linked question and allowed schema elements, generate valid SQL.

Schema-linked question:
{slml_question}

Allowed schema elements (use @ as table.column separator, e.g. author@name):
{alias_schema_str}

Rules:
1. Only use schema elements from the allowed list above.
2. Use @ as separator between table and column (e.g. SELECT author@name FROM author).
3. Do not add tables or columns not in the allowed list.
4. Output ONLY the SQL statement, nothing else.

SQL:"""


def _extract_sql(response: str) -> str:
    """Extract SQL from LLM response.

    Handles: plain SQL, ```sql ... ```, SQL: ... prefix.
    """
    text = response.strip()

    # Strip code fences
    fence_match = re.search(r"```(?:sql)?\s*(.*?)```", text, re.DOTALL | re.IGNORECASE)
    if fence_match:
        return fence_match.group(1).strip()

    # Strip "SQL:" prefix
    if text.upper().startswith("SQL:"):
        text = text[4:].strip()

    # Take first non-empty line that looks like SQL
    for line in text.splitlines():
        line = line.strip()
        if line.upper().startswith("SELECT"):
            return line

    return text


def _validate_schema_refs(sql: str, alias_schema: List[str]) -> str:
    """Post-hoc validation: remove/replace table@col refs not in alias_schema.

    Scans for word@word patterns and drops tokens not in alias_schema.
    """
    alias_set = set(s.lower() for s in alias_schema)
    tokens = sql.split()
    cleaned = []
    for tok in tokens:
        if "@" in tok:
            tok_lower = tok.strip("(),").lower()
            if tok_lower not in alias_set:
                # Try to find a close match (same column, different table)
                col = tok_lower.split("@")[-1] if "@" in tok_lower else tok_lower
                replacement = None
                for alias in alias_schema:
                    if alias.endswith(f"@{col}"):
                        replacement = alias
                        break
                if replacement:
                    logger.debug(
                        f"[UNISARBooksqlGenerator] replaced invalid ref '{tok}' → '{replacement}'"
                    )
                    tok = replacement
                else:
                    logger.debug(
                        f"[UNISARBooksqlGenerator] dropping unknown schema ref: {tok}"
                    )
                    continue
        cleaned.append(tok)
    return " ".join(cleaned)


@BaseGenerator.register_actor
class UNISARBooksqlGenerator(BaseGenerator):
    """UNISAR BookSQL Generator.

    Single LLM call: SLML question + alias_schema → SQL in table@column notation.
    """

    NAME = "UNISARBooksqlGenerator"

    SKILL = """# UNISARBooksqlGenerator

Single LLM call using SLML question + alias_schema constraint.
Replaces GENRE mbart_large beam search with a standard LLM completion.

## Inputs
- instance_schemas["slml_question"]: SLML markup string from UNISARBooksqlReducer
- instance_schemas["alias_schema"]: list of valid table@col tokens

## Output
pred_sql (in table@column notation, @ as separator)

## Steps
1. Load slml_question and alias_schema from instance_schemas
2. Build prompt with SLML question + alias_schema list
3. LLM complete() with retry (max 3 attempts)
4. Extract SQL from response
5. Post-hoc validation: strip invalid @-ref tokens
6. Save and return pred_sql
"""

    def __init__(
        self,
        dataset: Dataset = None,
        llm=None,
        is_save: bool = True,
        save_dir: Union[str, PathLike] = "../files/pred_sql",
        max_retries: int = 3,
        **kwargs
    ):
        self.dataset = dataset
        self.llm = llm
        self.is_save = is_save
        self.save_dir = save_dir
        self.max_retries = max_retries

    def _call_llm(self, prompt: str) -> Optional[str]:
        """Call LLM with retry. Returns raw response text or None."""
        llm = self.get_llm()
        if llm is None:
            raise ValueError("LLM is not initialized")

        for attempt in range(self.max_retries):
            try:
                response = llm.complete(prompt)
                return response.text.strip()
            except Exception as e:
                logger.warning(
                    f"[{self.NAME}] LLM call failed (attempt {attempt + 1}/{self.max_retries}): {e}"
                )
                if attempt < self.max_retries - 1:
                    time.sleep(1 + attempt)

        logger.error(f"[{self.NAME}] All {self.max_retries} LLM attempts failed")
        return None

    def act(
        self,
        item,
        schema: Union[str, PathLike, Dict, List] = None,
        schema_links: Union[str, List[str]] = None,
        sub_questions: Union[str, List[str], Dict] = None,
        data_logger=None,
        **kwargs
    ) -> str:
        if data_logger:
            data_logger.info(f"{self.NAME}.act start | item={item}")

        row = self.dataset[item]
        instance_id = row.get("instance_id", str(item))

        # Load slml_question and alias_schema from instance_schemas
        slml_question = row.get("slml_question")
        alias_schema = row.get("alias_schema")

        # Fall back to loading from instance_schemas dict
        if slml_question is None or alias_schema is None:
            is_path = row.get("instance_schemas")
            if is_path:
                if isinstance(is_path, str):
                    try:
                        is_data = load_dataset(is_path)
                    except Exception:
                        is_data = {}
                else:
                    is_data = is_path

                if isinstance(is_data, dict):
                    slml_question = slml_question or is_data.get("slml_question")
                    alias_schema = alias_schema or is_data.get("alias_schema")

        if not slml_question:
            question = row.get("question", "")
            logger.warning(
                f"[{self.NAME}] No slml_question found for item {item}, "
                f"using raw question as fallback"
            )
            slml_question = question

        if not alias_schema:
            logger.warning(f"[{self.NAME}] No alias_schema found for item {item}, proceeding without constraint")
            alias_schema = []

        # Build prompt
        alias_schema_str = ", ".join(str(s) for s in alias_schema)
        prompt = PROMPT_TEMPLATE.format(
            slml_question=slml_question,
            alias_schema_str=alias_schema_str,
        )

        if data_logger:
            data_logger.info(f"{self.NAME}.prompt_preview | {prompt[:200]}...")

        # Call LLM
        response = self._call_llm(prompt)
        if response is None:
            logger.warning(f"[{self.NAME}] LLM failed for item {item}, returning SELECT fallback")
            pred_sql = "SELECT"
        else:
            pred_sql = _extract_sql(response)
            if not pred_sql or not pred_sql.strip().upper().startswith("SELECT"):
                logger.warning(f"[{self.NAME}] Could not extract valid SQL for item {item}, using raw response")
                pred_sql = response.replace("\n", " ").strip() or "SELECT"

        # Post-hoc schema validation
        if alias_schema:
            pred_sql = _validate_schema_refs(pred_sql, alias_schema)

        pred_sql = sql_clean(pred_sql)

        if data_logger:
            data_logger.info(f"{self.NAME}.pred_sql | {pred_sql[:200]}")

        pred_sql = self.save_output(pred_sql, item, instance_id)

        if data_logger:
            data_logger.info(f"{self.NAME}.act end | item={item}")

        return pred_sql

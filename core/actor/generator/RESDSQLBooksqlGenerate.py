"""RESDSQL Generator for BookSQL — n=4 LLM sampling with execution retry.

Reads instance_schemas (ranked schema string) from upstream RESDSQLBooksqlReducer,
generates n=4 SQL candidates, and returns the first one that executes successfully
against the BookSQL SQLite database.

Uses the row db_id first, with 'booksql' kept as a legacy fallback.
"""

import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Optional, Union
from os import PathLike

from loguru import logger

from core.actor.generator.BaseGenerate import BaseGenerator
from core.data_manage import Dataset
from core.db_path import resolve_sqlite_file
from core.utils import load_dataset, sql_clean


# ---------------------------------------------------------------------------
# SQL generation prompt
# ---------------------------------------------------------------------------

GENERATE_PROMPT_TEMPLATE = (
    "You are a SQLite expert. Use ONLY the tables and columns listed below to answer the question.\n"
    "Do NOT invent table names, column names, or values — use ONLY what is provided.\n"
    "Output ONLY a single valid SQLite SELECT statement. No explanation, no markdown.\n"
    "\n"
    "=== DATABASE SCHEMA (use ONLY these tables/columns) ===\n"
    "{schema_text}\n"
    "\n"
    "=== HINT (ranked relevant tables/columns) ===\n"
    "{input_sequence}\n"
    "\n"
    "SQL: SELECT"
)


# ---------------------------------------------------------------------------
# Generator actor
# ---------------------------------------------------------------------------

@BaseGenerator.register_actor
class RESDSQLBooksqlGenerator(BaseGenerator):
    """RESDSQL SQL generator for BookSQL.

    Uses ranked schema string (instance_schemas) from the reducer.
    Generates n_candidates SQL candidates in a single batched LLM call,
    then returns the first candidate that executes without error against
    the BookSQL SQLite database. Falls back to the first candidate if
    none are executable.
    """

    NAME = "RESDSQLBooksqlGenerator"

    SKILL = """# RESDSQLBooksqlGenerator

RESDSQL SQL generation for BookSQL with execution retry.

## Inputs
- instance_schemas: ranked schema string from RESDSQLBooksqlReducer
  format: "question | table: col(match) | fk: t1.c = t2.c"

## Steps
1. Read instance_schemas from dataset row
2. LLM call with n_candidates=4 samples
3. For each candidate: try executing against BookSQL SQLite
4. Return first executable; fall back to first candidate

## Output
pred_sql
"""

    DB_ID = "booksql"

    def __init__(
        self,
        dataset: Dataset = None,
        llm: Any = None,
        is_save: bool = True,
        save_dir: Union[str, PathLike] = "../files/pred_sql",
        db_path: Optional[Union[str, Path]] = None,
        n_candidates: int = 4,
        **kwargs,
    ):
        self.dataset = dataset
        self.llm = llm
        self.is_save = is_save
        self.save_dir = save_dir
        self.db_path = db_path or (getattr(dataset, "db_path", None) if dataset else None)
        self.n_candidates = max(1, int(n_candidates))

    # ------------------------------------------------------------------
    # Schema text builder (prevents LLM hallucination)
    # ------------------------------------------------------------------

    def _build_schema_text(self, item, row) -> str:
        """Build a human-readable schema listing all tables and columns.

        Uses the dataset's db schema as ground truth, so the LLM cannot
        hallucinate non-existent table or column names.
        """
        try:
            schema_items = self.dataset.get_db_schema(item)
        except Exception:
            return "(schema unavailable)"

        if isinstance(schema_items, dict):
            from core.data_manage import single_central_process
            schema_items = single_central_process(schema_items)

        tables: dict = {}
        for entry in schema_items:
            if not isinstance(entry, dict):
                continue
            tname = entry.get("table_name_original") or entry.get("table_name", "")
            cname = entry.get("column_name_original") or entry.get("column_name", "")
            if not tname or not cname:
                continue
            tables.setdefault(tname, []).append(cname)

        lines = []
        for tn, cols in tables.items():
            col_str = ", ".join(cols)
            lines.append(f"  {tn} ( {col_str} )")
        return "\n".join(lines)

    # ------------------------------------------------------------------
    # DB file resolution
    # ------------------------------------------------------------------

    def _resolve_db_file(self, db_id: Optional[str] = None) -> Optional[str]:
        """Resolve the SQLite file path for BookSQL."""
        if not self.db_path:
            return None
        db_dir = Path(self.db_path)
        if db_dir.suffix in (".sqlite", ".db"):
            return str(db_dir) if db_dir.exists() else None
        candidate = resolve_sqlite_file(db_dir, db_id or self.DB_ID, fallback_db_ids=(self.DB_ID,))
        return str(candidate) if candidate.exists() else str(db_dir)

    # ------------------------------------------------------------------
    # SQL post-processing
    # ------------------------------------------------------------------

    @staticmethod
    def _post_process_sql(raw: str) -> str:
        """Normalize a raw LLM output to a clean SQL string.

        Handles both clean SQL output and verbose LLM responses that embed SQL
        within markdown fences or multi-paragraph text.
        """
        import re

        sql = str(raw).strip()

        # 1) Try extracting from ```sql ... ``` fence
        m = re.search(r"```(?:sql|sqlite)?\s*(SELECT[\s\S]*?)```", sql, re.IGNORECASE)
        if m:
            sql = m.group(1).strip()

        # 2) Try extracting from "SQL:" prefix to end (or next double-newline)
        m2 = re.search(r"(?:SQL|sql)\s*:\s*(SELECT[\s\S]+)", sql, re.IGNORECASE)
        if m2:
            sql = m2.group(1).strip()
            # Cut at double newline if present
            cut = sql.find("\n\n")
            if cut > 0:
                sql = sql[:cut].strip()

        # 3) Try to find the first SELECT statement in the text
        if not sql.lower().startswith("select"):
            m3 = re.search(r"\b(SELECT\s[\s\S]+?)(?:;|\n\n|\Z)", sql, re.IGNORECASE)
            if m3:
                sql = m3.group(1).strip()
                # Stop at trailing natural language
                # Cut at patterns like "###", "---", "Note:", "Let me"
                for marker in ["###", "---", "Note:", "Let me", "I hope", "This query"]:
                    idx = sql.find(marker)
                    if idx > 0:
                        sql = sql[:idx].strip()

        # 4) Basic cleanup
        sql = sql.strip().strip("`").strip(";")
        if not sql.lower().startswith("select"):
            sql = "SELECT " + sql
        sql = sql.replace("SELECT SELECT", "SELECT")
        sql = sql_clean(sql)
        return sql

    # ------------------------------------------------------------------
    # Execution retry
    # ------------------------------------------------------------------

    def _try_execute(self, sql: str, db_file: str) -> bool:
        """Return True if sql executes without error against db_file."""
        try:
            conn = sqlite3.connect(db_file)
            conn.text_factory = lambda b: b.decode(errors="ignore")
            cursor = conn.cursor()
            try:
                cursor.execute(sql)
                cursor.fetchall()
                return True
            finally:
                cursor.close()
                conn.close()
        except Exception as e:
            logger.debug(f"[{RESDSQLBooksqlGenerator.NAME}] SQL execution failed: {e}")
            return False

    def _execution_retry(self, candidates: List[str], db_file: Optional[str]) -> str:
        """Return first executable candidate; fall back to candidates[0]."""
        if not candidates:
            return ""
        if not db_file:
            logger.debug(f"[{self.NAME}] No db_file available, skipping execution retry")
            return candidates[0]

        for sql in candidates:
            if sql and self._try_execute(sql, db_file):
                return sql

        logger.debug(f"[{self.NAME}] No executable candidate found, returning candidates[0]")
        return candidates[0]

    # ------------------------------------------------------------------
    # LLM generation
    # ------------------------------------------------------------------

    def _generate_candidates(self, prompt: str) -> List[str]:
        """Generate n_candidates SQL strings via a single batched LLM call.

        Uses raw OpenAI-compatible client n= parameter when available.
        Falls back to n sequential calls.
        """
        llm = self.get_llm()
        if llm is None:
            raise ValueError(f"[{self.NAME}] LLM is not initialized")

        client = getattr(llm, "client", None)
        if client is not None:
            try:
                model = getattr(llm, "model_name", "gpt-3.5-turbo")
                messages = [{"role": "user", "content": prompt}]
                response = client.chat.completions.create(
                    model=model,
                    messages=messages,
                    n=self.n_candidates,
                    max_tokens=getattr(llm, "max_tokens", 512),
                    temperature=getattr(llm, "temperature", 0.8),
                    top_p=getattr(llm, "top_p", 0.95),
                    timeout=getattr(llm, "time_out", 300.0),
                )
                return [
                    (choice.message.content or "").strip()
                    for choice in response.choices
                ]
            except Exception as e:
                logger.warning(
                    f"[{self.NAME}] batch generate failed ({e}), falling back to sequential"
                )

        # Fallback: n sequential calls
        results = []
        for _ in range(self.n_candidates):
            try:
                resp = llm.complete(prompt)
                text = getattr(resp, "text", str(resp)).strip()
                results.append(text)
            except Exception as e:
                logger.warning(f"[{self.NAME}] sequential generate failed: {e}")
        return results if results else [""]

    # ------------------------------------------------------------------
    # Main act
    # ------------------------------------------------------------------

    def act(
        self,
        item,
        schema: Union[str, PathLike, Dict, List] = None,
        schema_links: Union[str, List[str]] = None,
        sub_questions=None,
        data_logger=None,
        **kwargs,
    ) -> str:
        if data_logger:
            data_logger.info(f"{self.NAME}.act start | item={item}")

        row = self.dataset[item]
        question = row.get("question", "")

        # Read instance_schemas (ranked schema string from reducer)
        input_sequence = None
        instance_schemas_val = row.get("instance_schemas")
        if instance_schemas_val:
            # Could be a file path (saved by reducer) or the string itself
            p = Path(str(instance_schemas_val))
            if p.exists():
                loaded = load_dataset(str(p))
                if isinstance(loaded, dict):
                    input_sequence = loaded.get("instance_schemas")
                elif isinstance(loaded, str):
                    input_sequence = loaded
            else:
                # Already the serialized string or a dict
                if isinstance(instance_schemas_val, dict):
                    input_sequence = instance_schemas_val.get("instance_schemas")
                else:
                    input_sequence = str(instance_schemas_val)

        if not input_sequence:
            logger.warning(
                f"[{self.NAME}] instance_schemas not found for item {item}, "
                "falling back to question only"
            )
            input_sequence = question

        # Build real schema text to prevent hallucination
        schema_text = self._build_schema_text(item, row)

        # Build prompt
        prompt = GENERATE_PROMPT_TEMPLATE.format(
            schema_text=schema_text,
            input_sequence=input_sequence,
        )
        if data_logger:
            data_logger.info(f"{self.NAME}.prompt_len={len(prompt)}")

        # Generate n candidates
        raw_candidates = self._generate_candidates(prompt)
        if data_logger:
            data_logger.info(f"{self.NAME}.generated | n={len(raw_candidates)}")

        # Post-process each candidate
        candidates = []
        for raw in raw_candidates:
            try:
                sql = self._post_process_sql(raw)
                if sql:
                    candidates.append(sql)
            except Exception as e:
                logger.debug(f"[{self.NAME}] post_process error: {e}")

        if not candidates:
            candidates = ["SELECT 1"]

        # Execution retry: return first executable
        db_file = self._resolve_db_file(row.get("db_id"))
        sql = self._execution_retry(candidates, db_file)

        if data_logger:
            data_logger.info(f"{self.NAME}.final_sql | sql={sql}")

        # Save output
        sql = self.save_output(sql, item, row.get("instance_id"))

        if data_logger:
            data_logger.info(f"{self.NAME}.act end | item={item}")

        return sql

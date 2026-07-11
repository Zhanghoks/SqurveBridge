"""RESDSQL Reducer for BookSQL — schema ranking with bridge content encoder.

Two-stage pipeline:
  Stage 1 (rule-based): fuzzy cell matching via difflib + rapidfuzz → db_contents dict
  Stage 2 (LLM): schema ranking prompt → top-3 tables, top-5 columns/table

Output: sets item.instance_schemas to serialized ranked schema string
        (format: "question | table1: col1(match1), col2 | fk: t1.c = t2.c")
        also stores tc_original as flat list of "table.col" strings.

Uses the row db_id first, with 'booksql' kept as a legacy fallback.
"""

import json
import re
import sqlite3
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from loguru import logger

from core.actor.reducer.BaseReduce import BaseReducer
from core.data_manage import Dataset, save_dataset
from core.db_path import resolve_sqlite_file


# ---------------------------------------------------------------------------
# Bridge content encoder (ported from RESDSQL/utils/bridge_content_encoder.py)
# ---------------------------------------------------------------------------

try:
    from rapidfuzz import fuzz as _rapidfuzz_fuzz
    _HAS_RAPIDFUZZ = True
except ImportError:
    _HAS_RAPIDFUZZ = False
    logger.warning("[RESDSQLBooksqlReducer] rapidfuzz not installed; falling back to difflib only")

import difflib


@lru_cache(maxsize=1000)
def _get_column_picklist(db_path: str, table: str, column: str) -> List[str]:
    """Fetch distinct non-null string values for a column from SQLite (cached)."""
    try:
        conn = sqlite3.connect(db_path)
        conn.text_factory = lambda b: b.decode(errors="ignore")
        cursor = conn.cursor()
        cursor.execute(
            f"SELECT DISTINCT `{column}` FROM `{table}` WHERE `{column}` IS NOT NULL LIMIT 500"
        )
        rows = cursor.fetchall()
        conn.close()
        return [str(r[0]) for r in rows if r[0] is not None]
    except Exception as e:
        logger.debug(f"[bridge_content_encoder] picklist failed ({table}.{column}): {e}")
        return []


def _get_database_matches(question: str, table: str, column: str, db_path: str) -> List[str]:
    """Return top-2 fuzzy-matching cell values for a column against the question.

    Uses rapidfuzz ratio when available, falls back to difflib SequenceMatcher.
    """
    picklist = _get_column_picklist(db_path, table, column)
    if not picklist:
        return []

    question_lower = question.lower()
    scored = []
    for val in picklist:
        val_lower = str(val).lower()
        if _HAS_RAPIDFUZZ:
            score = _rapidfuzz_fuzz.ratio(question_lower, val_lower) / 100.0
        else:
            score = difflib.SequenceMatcher(None, question_lower, val_lower).ratio()
        scored.append((score, val))

    scored.sort(key=lambda x: x[0], reverse=True)
    return [v for _, v in scored[:2] if _ > 0.0]


# ---------------------------------------------------------------------------
# Schema ranking prompt
# ---------------------------------------------------------------------------

RANKING_PROMPT = """You are a database expert. Given a natural language question and a database schema, score the relevance of each table and column for answering the question.

Question: "{question}"

Database schema (table: [columns]):
{schema_text}

Return a JSON object with this exact format:
{{
  "tables": [{{"name": "table_name", "score": 0.95}}, ...],
  "columns": [{{"name": "table_name.column_name", "score": 0.90}}, ...]
}}

Score from 0.0 (irrelevant) to 1.0 (essential). Include all tables and columns in your response."""


# ---------------------------------------------------------------------------
# Reducer actor
# ---------------------------------------------------------------------------

@BaseReducer.register_actor
class RESDSQLBooksqlReducer(BaseReducer):
    """RESDSQL-style schema ranking reducer for the BookSQL dataset.

    Rule-based bridge content encoder (fuzzy cell matching) feeds into
    an LLM schema ranking step.  Outputs a serialized ranked schema string
    stored in item.instance_schemas plus tc_original for downstream actors.
    """

    NAME = "RESDSQLBooksqlReducer"

    SKILL = """# RESDSQLBooksqlReducer

RESDSQL schema ranking for BookSQL (single-database dataset).

## Steps
1. For each column, fuzzy-match question tokens against SQLite cell values → db_contents
2. LLM scores table/column relevance → JSON with scores
3. Select top-3 tables, top-5 columns per table
4. Serialize: "question | table: col(match1, match2) | fk: t1.c = t2.c"

## Outputs
- instance_schemas: serialized ranked schema string (file path saved to dataset)
- tc_original: flat list of "table.column" strings
"""

    DB_ID = "booksql"

    def __init__(
        self,
        dataset: Dataset = None,
        llm: Any = None,
        is_save: bool = True,
        save_dir: str = "../files/instance_schemas",
        db_path: Optional[Union[str, Path]] = None,
        top_k_tables: int = 3,
        top_k_columns: int = 5,
        **kwargs,
    ):
        self.dataset = dataset
        self.llm = llm
        self.is_save = is_save
        self.save_dir = save_dir
        self.db_path = db_path or (getattr(dataset, "db_path", None) if dataset else None)
        self.top_k_tables = top_k_tables
        self.top_k_columns = top_k_columns

    # ------------------------------------------------------------------
    # Schema helpers
    # ------------------------------------------------------------------

    def _build_tables_dict(self, schema_items: List[Dict]) -> Dict[str, List[str]]:
        """Convert Squrve schema items to {table_name: [col1, col2, ...]}."""
        tables: Dict[str, List[str]] = {}
        for item in schema_items:
            tname = item.get("table_name_original", item.get("table_name", ""))
            cname = item.get("column_name_original", item.get("column_name", ""))
            if tname not in tables:
                tables[tname] = []
            if cname and cname not in tables[tname]:
                tables[tname].append(cname)
        return tables

    def _build_fks_list(self, schema_items: List[Dict], row: Dict) -> List[str]:
        """Extract foreign key strings from schema items or row."""
        fks = []
        seen = set()
        for item in schema_items:
            fk = item.get("foreign_key") or item.get("fk")
            if fk and str(fk) not in seen:
                fks.append(str(fk))
                seen.add(str(fk))
        if not fks:
            fks_raw = row.get("fk") or row.get("foreign_keys") or []
            if isinstance(fks_raw, list):
                for fk in fks_raw:
                    if isinstance(fk, dict):
                        src = f"{fk.get('source_table_name_original','')}.{fk.get('source_column_name_original','')}"
                        tgt = f"{fk.get('target_table_name_original','')}.{fk.get('target_column_name_original','')}"
                        entry = f"{src} = {tgt}"
                    else:
                        entry = str(fk)
                    if entry not in seen:
                        fks.append(entry)
                        seen.add(entry)
        return fks

    # ------------------------------------------------------------------
    # Stage 1: bridge content encoder
    # ------------------------------------------------------------------

    def _build_db_contents(
        self, question: str, tables: Dict[str, List[str]], db_file: str
    ) -> Dict[str, Dict[str, List[str]]]:
        """Fuzzy-match question against column values → db_contents[table][col] = [matches]."""
        db_contents: Dict[str, Dict[str, List[str]]] = {}
        for table, columns in tables.items():
            db_contents[table] = {}
            for col in columns:
                matches = _get_database_matches(question, table, col, db_file)
                db_contents[table][col] = matches
        return db_contents

    # ------------------------------------------------------------------
    # Stage 2: LLM ranking
    # ------------------------------------------------------------------

    def _build_ranking_prompt(self, question: str, tables: Dict[str, List[str]]) -> str:
        schema_lines = []
        for tname, cols in tables.items():
            col_str = ", ".join(cols)
            schema_lines.append(f"  {tname}: [{col_str}]")
        schema_text = "\n".join(schema_lines)
        return RANKING_PROMPT.format(question=question, schema_text=schema_text)

    def _parse_ranking_response(
        self, response: str, tables: Dict[str, List[str]]
    ) -> tuple:
        """Parse LLM JSON response → (table_scores, column_scores).

        Falls back to uniform scores if parsing fails.
        """
        text = response.strip()
        # Strip markdown fences
        if text.startswith("```"):
            lines = text.split("\n")
            text = "\n".join(lines[1:])
            if text.endswith("```"):
                text = text[:-3]

        try:
            data = json.loads(text)
            table_scores = {t["name"]: float(t.get("score", 0.5)) for t in data.get("tables", [])}
            column_scores = {c["name"]: float(c.get("score", 0.5)) for c in data.get("columns", [])}
            return table_scores, column_scores
        except (json.JSONDecodeError, KeyError, TypeError):
            pass

        # Try regex extraction
        match = re.search(r'\{.*"tables".*\}', text, re.DOTALL)
        if match:
            try:
                data = json.loads(match.group())
                table_scores = {t["name"]: float(t.get("score", 0.5)) for t in data.get("tables", [])}
                column_scores = {c["name"]: float(c.get("score", 0.5)) for c in data.get("columns", [])}
                return table_scores, column_scores
            except Exception:
                pass

        logger.warning(f"[{self.NAME}] Failed to parse LLM ranking response, using fallback")
        # Fallback: uniform scores
        table_scores = {tname: 0.5 for tname in tables}
        column_scores = {}
        for tname, cols in tables.items():
            for col in cols:
                column_scores[f"{tname}.{col}"] = 0.5
        return table_scores, column_scores

    def _select_top_k(
        self,
        tables: Dict[str, List[str]],
        table_scores: Dict[str, float],
        column_scores: Dict[str, float],
    ) -> List[Dict]:
        """Select top-k tables and top-k columns per table."""
        # Sort tables by score
        sorted_tables = sorted(
            tables.keys(),
            key=lambda t: table_scores.get(t, 0.0),
            reverse=True,
        )
        selected_tables = sorted_tables[: self.top_k_tables]

        ranked = []
        for tname in selected_tables:
            cols = tables[tname]
            # Sort columns by score
            sorted_cols = sorted(
                cols,
                key=lambda c: column_scores.get(f"{tname}.{c}", 0.0),
                reverse=True,
            )
            ranked.append({"table_name": tname, "columns": sorted_cols[: self.top_k_columns]})
        return ranked

    # ------------------------------------------------------------------
    # Stage 3 + 4: serialization
    # ------------------------------------------------------------------

    def _serialize_schema(
        self,
        question: str,
        ranked: List[Dict],
        db_contents: Dict[str, Dict[str, List[str]]],
        fks: List[str],
    ) -> str:
        """Serialize ranked schema to RESDSQL input format.

        Format (verbatim from text2sql_data_generator.py):
          "question | table1 : col1(match1, match2), col2 | fk_t1.fk_c1 = fk_t2.fk_c2"
        """
        parts = [question]
        for entry in ranked:
            tname = entry["table_name"]
            col_parts = []
            for col in entry["columns"]:
                matches = db_contents.get(tname, {}).get(col, [])
                if matches:
                    match_str = ", ".join(matches[:2])
                    col_parts.append(f"{col}({match_str})")
                else:
                    col_parts.append(col)
            col_str = ", ".join(col_parts)
            parts.append(f"{tname} : {col_str}")

        if fks:
            fk_str = " , ".join(fks)
            parts.append(fk_str)

        return " | ".join(parts)

    def _build_tc_original(self, ranked: List[Dict]) -> List[str]:
        """Build flat list of 'table.column' strings from ranked selection."""
        tc_list = []
        for entry in ranked:
            tname = entry["table_name"]
            for col in entry["columns"]:
                tc_list.append(f"{tname}.{col}")
        return tc_list

    # ------------------------------------------------------------------
    # Resolve db file
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
    # Main act
    # ------------------------------------------------------------------

    def act(self, item, schema: Union[Dict, List] = None, data_logger=None, **kwargs):
        if data_logger:
            data_logger.info(f"{self.NAME}.act start | item={item}")

        row = self.dataset[item]
        question = row["question"]

        # Load schema
        schema_items = schema
        if schema_items is None:
            schema_items = self.dataset.get_db_schema(item)
        if schema_items is None:
            raise ValueError(f"[{self.NAME}] No schema available for item {item}")

        if isinstance(schema_items, dict):
            from core.data_manage import single_central_process
            schema_items = single_central_process(schema_items)

        tables = self._build_tables_dict(schema_items)
        fks = self._build_fks_list(schema_items, row)

        # Stage 1: bridge content encoder
        db_file = self._resolve_db_file(row.get("db_id"))
        if db_file:
            db_contents = self._build_db_contents(question, tables, db_file)
            if data_logger:
                data_logger.info(f"{self.NAME}.bridge_content_encoder done | db_file={db_file}")
        else:
            logger.warning(f"[{self.NAME}] db_path not resolved, skipping bridge content encoder")
            db_contents = {t: {c: [] for c in cols} for t, cols in tables.items()}

        # Stage 2: LLM ranking
        prompt = self._build_ranking_prompt(question, tables)
        if data_logger:
            data_logger.info(f"{self.NAME}.llm_ranking | prompt_len={len(prompt)}")

        try:
            llm = self.get_llm()
            if llm is None:
                raise ValueError("LLM is not initialized")
            response = llm.complete(prompt)
            response_text = getattr(response, "text", str(response)).strip()
        except Exception as e:
            logger.error(f"[{self.NAME}] LLM call failed: {e}")
            response_text = ""

        table_scores, column_scores = self._parse_ranking_response(response_text, tables)

        # Stage 3: select top-k
        ranked = self._select_top_k(tables, table_scores, column_scores)

        # Stage 4: serialize
        serialized = self._serialize_schema(question, ranked, db_contents, fks)
        tc_original = self._build_tc_original(ranked)

        if data_logger:
            data_logger.info(
                f"{self.NAME}.serialized | tables={len(ranked)} | tc_original={len(tc_original)}"
            )

        result = {
            "instance_schemas": serialized,
            "tc_original": tc_original,
        }

        # Save
        if self.is_save:
            instance_id = row.get("instance_id", str(item))
            save_path = Path(self.save_dir)
            if self.dataset and hasattr(self.dataset, "dataset_index") and self.dataset.dataset_index:
                save_path = save_path / str(self.dataset.dataset_index)
            save_path.mkdir(parents=True, exist_ok=True)
            file_path = save_path / f"{self.NAME}_{instance_id}.json"
            save_dataset(result, new_data_source=file_path)
            self.dataset.setitem(item, "instance_schemas", str(file_path))
            if data_logger:
                data_logger.info(f"{self.NAME}.saved | path={file_path}")

        if data_logger:
            data_logger.info(f"{self.NAME}.act end | item={item}")

        return result

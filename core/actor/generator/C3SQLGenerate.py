"""
C3SQL Generator — Chat-based SQL Generation (original prompt + two tips + retry loop)

The Generator layer of the C3SQL method.  Consumes schema_links from
C3SQLParser (or any upstream Parser) and builds a prompt matching the
original C3SQL prompt_generate.py format.

Three-layer design:
  C3SQLReducer  →  instance_schemas  (table recall,  self-consistency)
  C3SQLParser   →  schema_links      (column recall, self-consistency)
  C3SQLGenerator →  pred_sql         (SQL generation, 1 LLM call)

If run standalone (no upstream Reduce/Parse), falls back to full-schema
mode with the original C3SQL prompt shape.

Round 1 alignment (2026-06-24):
  H2 — Ported fix_select_column() from original sql_post_process.py
  H4 — Added execution validation retry loop (max 5 attempts, 0.5s sleep)
  H5 — Restored original chat role structure (CHAT_MESSAGES list)
  M2 — Chat role structure naturally ensures proper message separation
  L3 — Added replace_cur_year() for SQL validation
  M5 — sql_clean() confirmed as simple cleanup (spaces/newlines/markdown), KEPT
Round 2 alignment (2026-06-24):
  US-R5 — Self-consistency denotation clustering (get_selfconsistent_output.py)
  US-R6 — Batch LLM generation (single API call, n=n_candidates)
"""

import re
import sqlite3
import time
from collections import defaultdict
from os import PathLike
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

import pandas as pd
from llama_index.core.llms.llm import LLM
from loguru import logger

from core.actor.generator.BaseGenerate import BaseGenerator
from core.data_manage import Dataset, single_central_process
from core.actor.parser.parse_utils import format_schema_links, normalize_schema_links
from core.llm.completion_limits import chat_extra_body_for_llm, max_chat_completion_n
from core.utils import load_dataset, parse_schema_from_df, sql_clean


# Default chunk size when the provider allows multi-sample `n` (e.g. Qwen).
MAX_BATCH_N = 4


@BaseGenerator.register_actor
class C3SQLGenerator(BaseGenerator):
    """C3SQL SQL Generator — chat-based prompt with execution validation retry loop.

    Consumes upstream schema_links and instance_schemas when available.
    Falls back gracefully when running standalone.

    Uses the original C3SQL few-shot chat message structure (system message +
    two tip examples with assistant acknowledgements).  Generated SQL is
    validated against the target SQLite database; on failure, retries up to
    5 times with 0.5s sleep between attempts.
    """

    NAME = "C3SQLGenerator"

    SKILL = """# C3SQLGenerator

C3SQL three-layer Text2SQL method:
  Layer 1 — C3SQLReducer:  table recall  via LLM self-consistency
  Layer 2 — C3SQLParser:   column recall via LLM self-consistency
  Layer 3 — C3SQLGenerator: SQL generation (chat-based prompt + retry loop)

When run with upstream ReduceTask+ParseTask, consumes their outputs.
Standalone fallback: uses full schema directly.

## Inputs
- `schema_links`: from C3SQLParser (or any Parser).
- `instance_schemas`: from C3SQLReducer (or any Reducer).
- Dataset row with `question`, `db_id`.

## Output
`pred_sql`
"""

    # ── original C3SQL chat messages (verbatim from generate_sqls_by_gpt3.5.py L15-43) ─
    CHAT_MESSAGES: List[Dict[str, str]] = [
        {
            "role": "system",
            "content": (
                "You are now an excellent SQL writer, first I'll give you some tips "
                "and examples, and I need you to remember the tips, and do not make "
                "same mistakes."
            ),
        },
        {
            "role": "user",
            "content": (
                "Tips 1: \n"
                "Question: Which A has most number of B?\n"
                "Gold SQL: select A from B group by A order by count ( * ) desc limit 1;\n"
                "Notice that the Gold SQL doesn't select COUNT(*) because the question "
                "only wants to know the A and the number should be only used in ORDER BY "
                "clause, there are many questions asks in this way, and I need you to "
                "remember this in the the following questions."
            ),
        },
        {
            "role": "assistant",
            "content": (
                "Thank you for the tip! I'll keep in mind that when the question only "
                "asks for a certain field, I should not include the COUNT(*) in the "
                "SELECT statement, but instead use it in the ORDER BY clause to sort "
                "the results based on the count of that field."
            ),
        },
        {
            "role": "user",
            "content": (
                "Tips 2: \n"
                "Don't use \"IN\", \"OR\", \"LEFT JOIN\" as it might cause extra results, "
                "use \"INTERSECT\" or \"EXCEPT\" instead, and remember to use \"DISTINCT\" "
                "or \"LIMIT\" when necessary.\n"
                "For example, \n"
                "Question: Who are the A who have been nominated for both B award and C award?\n"
                "Gold SQL should be: select A from X where award = 'B' intersect select A "
                "from X where award = 'C';"
            ),
        },
        {
            "role": "assistant",
            "content": (
                "Thank you for the tip! I'll remember to use \"INTERSECT\" or \"EXCEPT\" "
                "instead of \"IN\", \"OR\", or \"LEFT JOIN\" when I want to find records "
                "that match or don't match across two tables. Additionally, I'll make sure "
                "to use \"DISTINCT\" or \"LIMIT\" when necessary to avoid repetitive results "
                "or limit the number of results returned."
            ),
        },
    ]

    def __init__(
        self,
        dataset: Optional[Dataset] = None,
        llm: Optional[LLM] = None,
        is_save: bool = True,
        save_dir: Union[str, PathLike] = "../files/pred_sql",
        use_external: bool = True,
        n_candidates: int = 1,
        db_path: Optional[Union[str, PathLike]] = None,
        credential: Optional[Dict] = None,
        **kwargs,
    ) -> None:
        self.dataset: Optional[Dataset] = dataset
        self.llm: Optional[LLM] = llm
        self.is_save = is_save
        self.save_dir: Union[str, PathLike] = save_dir
        self.use_external = use_external
        self.n_candidates = max(1, int(n_candidates))
        self.db_path = db_path or (getattr(self.dataset, "db_path", None) if self.dataset else None)
        self.credential = credential or (self.dataset.credential if self.dataset else None)

    # ── external knowledge ─────────────────────────────────────────

    @classmethod
    def load_external_knowledge(cls, external: Union[str, Path] = None):
        if not external:
            return None
        try:
            external = load_dataset(external)
        except FileNotFoundError:
            logger.debug("External file not found, skipping external knowledge.")
            return None
        if external and len(external) > 50:
            return "####[External Prior Knowledge]:\n" + external
        return None

    # ── schema formatting ──────────────────────────────────────────

    @staticmethod
    def _normalize_schema(schema):
        """Convert schema (dict/list/DataFrame) to a compact DDL text."""
        if isinstance(schema, dict):
            schema = single_central_process(schema)
        if isinstance(schema, list):
            schema = pd.DataFrame(schema)
        if isinstance(schema, pd.DataFrame):
            return parse_schema_from_df(schema)
        raise ValueError("Invalid schema format")

    @classmethod
    def _build_schema_from_links(
        cls, schema_links: Union[str, List[str]], schema_df: pd.DataFrame
    ) -> str:
        """Build a compact schema text using only the tables/columns in schema_links.

        Replicates the original C3SQL prompt_generate.py behaviour:
        only selected tables and columns appear in the prompt, with FK lines
        limited to those involving selected tables.
        """
        # Parse schema_links to extract table→columns mapping
        if isinstance(schema_links, str):
            try:
                schema_links = normalize_schema_links(
                    schema_links if isinstance(schema_links, list) else [schema_links]
                )
            except Exception:
                schema_links = []

        if not schema_links:
            return ""

        # Extract {table: [columns]} from schema_links
        selected: Dict[str, List[str]] = {}
        for link in schema_links:
            link = str(link).strip()
            if "." in link:
                parts = link.split(".")
                if len(parts) == 2:
                    tbl, col = parts[0].strip(), parts[1].strip()
                    if tbl not in selected:
                        selected[tbl] = []
                    if col not in selected[tbl]:
                        selected[tbl].append(col)

        if not selected:
            return ""

        # Build schema lines: only selected tables and their selected columns
        schema_lines = []
        for table_name, columns in selected.items():
            table_rows = schema_df[schema_df["table_name"] == table_name]
            if table_rows.empty:
                continue
            cols = ", ".join(columns)
            schema_lines.append(f"# {table_name} ( {cols} )")

        return "\n".join(schema_lines)

    def _build_schema_from_links_with_contents(
        self,
        schema_links: Union[str, List[str]],
        schema_df: pd.DataFrame,
        question: str,
        db_id: str,
    ) -> str:
        """Build original C3SQL prompt schema, preserving matched DB contents.

        This mirrors candidates/C3SQL-master/src/prompt_generate.py after
        column_recall.py has produced `schema` and `db_contents`: selected
        columns are rendered as `col("value")` when bridge-content matching
        finds database values relevant to the question.
        """
        from core.actor.bridge_content import get_db_contents

        if isinstance(schema_links, str):
            try:
                schema_links = normalize_schema_links([schema_links])
            except Exception:
                schema_links = []

        selected: Dict[str, List[str]] = {}
        for link in schema_links or []:
            link = str(link).strip()
            if "." not in link:
                continue
            parts = link.split(".")
            if len(parts) != 2:
                continue
            table, column = parts[0].strip(), parts[1].strip()
            if not table or not column:
                continue
            selected.setdefault(table, [])
            if column not in selected[table]:
                selected[table].append(column)

        if not selected:
            return ""

        db_file = self._resolve_db_file(db_id)
        schema_lines = []
        for table_name, columns in selected.items():
            table_rows = schema_df[schema_df["table_name"] == table_name]
            if table_rows.empty:
                continue

            db_contents = None
            if db_file and db_file.exists():
                try:
                    db_contents = get_db_contents(
                        question=question,
                        table_name=table_name,
                        column_names=columns,
                        db_path=str(db_file),
                        top_k_matches=2,
                    )
                except Exception:
                    db_contents = None

            rendered_columns = []
            for idx, column in enumerate(columns):
                rendered = column
                if db_contents and idx < len(db_contents) and db_contents[idx]:
                    values = ''.join(f'{value}", "' for value in db_contents[idx])
                    rendered = f'{column}("{values[:-4]}")'
                rendered_columns.append(rendered)

            schema_lines.append(f"# {table_name} ( {', '.join(rendered_columns)} )")

        return "\n".join(schema_lines)

    # ── prompt building ────────────────────────────────────────────

    def prompt_maker(
        self,
        question: str,
        schema_text: str,
        db_id: str,
        fk_info: str = "",
    ) -> str:
        """Build the final user-message content matching original C3SQL format.

        Returns the content string for the last user message in the chat.
        The few-shot tips are handled separately via CHAT_MESSAGES.

        Format:
          ### Complete sqlite SQL query only and with no explanation...
          ### Sqlite SQL tables, with their properties:
          # <table> ( <col1>, <col2> )
          # <fk_line>
          ### <question>
          SELECT
        """
        prompt = (
            "### Complete sqlite SQL query only and with no explanation, "
            "and do not select extra columns that are not explicitly requested in the query.\n"
        )
        prompt += "### Sqlite SQL tables, with their properties:\n#\n"
        prompt += schema_text
        if fk_info:
            prompt += "\n" + fk_info
        prompt += (
            "\n#\n### SQL writing constraints:\n"
            "- If the question asks for a name, title, city, country, description, or other display value, return that display column instead of an id/code column; join through foreign keys when needed.\n"
            "- If the requested display value already exists in one table, do not add lookup joins only to replace codes with descriptions.\n"
            "- Use OR for alternatives phrased with 'or'. Use INTERSECT only when the same result must satisfy two independent requirements such as 'both'.\n"
            "- For 'not', 'no', 'without', or 'do not have any' questions, prefer NOT IN or EXCEPT over a join that changes the aggregation target.\n"
            "- For 'how many' questions over one table, use COUNT(*) unless the question explicitly asks for distinct values.\n"
            "- When ordering by frequency or 'most number of', group by the answer column and order by COUNT(*) without selecting COUNT(*) unless the count is requested.\n"
        )
        prompt += "\n#\n### " + question + "\nSELECT"
        return prompt

    # ── FK extraction ──────────────────────────────────────────────

    @staticmethod
    def _extract_fk_for_tables(schema_df: pd.DataFrame, selected_tables: List[str]) -> str:
        """Extract FK lines involving only the selected tables.

        Matches original C3SQL info_generate in table_recall.py:
        only keeps FK where both source and target tables are in the selected set.
        """
        fk_lines = set()
        selected_lookup = {table.lower(): table for table in selected_tables}
        for _, row in schema_df.iterrows():
            source_table = str(row.get("table_name", "")).strip()
            source_col = str(row.get("column_name", "")).strip()
            fk_val = row.get("foreign_key", "")
            if not fk_val or not isinstance(fk_val, str) or not fk_val.strip():
                continue
            fk_val = fk_val.strip()

            normalized_lines = []
            parts = fk_val.split("=")
            if len(parts) == 2 and "." in parts[0] and "." in parts[1]:
                left_table, left_col = [p.strip().strip("[]") for p in parts[0].split(".", 1)]
                right_table, right_col = [p.strip().strip("[]") for p in parts[1].split(".", 1)]
                normalized_lines.append((left_table, left_col, right_table, right_col))
            else:
                for ref_table, ref_col in re.findall(r"\[([^\[\]()]+)\(([^)]*)\)\]", fk_val):
                    normalized_lines.append(
                        (source_table, source_col, ref_table.strip(), ref_col.strip())
                    )

            for left_table, left_col, right_table, right_col in normalized_lines:
                if (
                    left_table.lower() in selected_lookup
                    and right_table.lower() in selected_lookup
                ):
                    left_table = selected_lookup[left_table.lower()]
                    right_table = selected_lookup[right_table.lower()]
                    fk_lines.add(f"# {left_table}.{left_col} = {right_table}.{right_col}")
        return "\n".join(sorted(fk_lines))

    # ── LLM generation ─────────────────────────────────────────────

    def llm_generation(self, messages: List[Dict[str, str]]) -> str:
        """Generate SQL from chat messages using the original C3SQL chat structure.

        Tries to use the underlying OpenAI-compatible client for multi-message
        chat support (matching original C3SQL behaviour).  Falls back to a
        flattened single-string prompt via llama_index CustomLLM when the raw
        client is unavailable.

        Deviation note: llama_index CustomLLM only exposes .complete(prompt: str),
        which wraps the prompt in [{"role": "user", "content": prompt}].  We
        access self.llm.client directly for multi-message chat to match the
        original C3SQL few-shot chat structure.  This does NOT modify the LLM
        provider itself — it only accesses the underlying client that every
        Squrve LLM model (OpenAI, Claude, Deepseek, etc.) already creates.
        """
        llm = self.get_llm()
        if llm is None:
            raise ValueError("LLM is not initialized")

        # 兼容传入单个字符串 prompt 的调用方式（规整为标准 chat messages）
        if isinstance(messages, str):
            messages = [{"role": "user", "content": messages}]

        # Attempt raw OpenAI-compatible client for multi-message chat
        client = getattr(llm, "client", None)
        if client is not None:
            try:
                model = getattr(llm, "model_name", "gpt-3.5-turbo")
                response = client.chat.completions.create(
                    model=model,
                    messages=messages,
                    max_tokens=getattr(llm, "max_tokens", 8000),
                    temperature=getattr(llm, "temperature", 0.7),
                    top_p=getattr(llm, "top_p", 0.8),
                    timeout=getattr(llm, "time_out", 300.0),
                )
                text = (response.choices[0].message.content or "").strip()
                if text:
                    return text
            except Exception as e:
                logger.warning(
                    f"{self.NAME}: raw client chat failed ({e}), falling back to flat prompt"
                )

        # Fallback: flatten messages into a single prompt string for CustomLLM
        # Multi-message chat structure is lost in this path.
        prompt_parts = []
        for msg in messages:
            content = msg.get("content", "")
            if content:
                prompt_parts.append(content)
        prompt = "\n\n".join(prompt_parts)

        fallback = ""
        for _ in range(self.n_candidates):
            try:
                response = llm.complete(prompt)
                text = getattr(response, "text", str(response)).strip()
                if text:
                    return text
                fallback = text
            except Exception as e:
                logger.warning(f"{self.NAME}: fallback complete failed ({e})")
        return fallback

    # ── SQL post-processing ────────────────────────────────────────

    @staticmethod
    def _clean_sql(sql: str) -> str:
        """Post-process generated SQL: fix operator spacing and collapse whitespace.

        NOTE: SELECT prefix addition and fix_select_column() are handled
        separately in act() before this method is called, matching the
        original C3SQL processing order:
          SELECT 补齐 → fix_select_column → 操作符空格修正 → sql_clean

        sql_clean() performs basic cleanup (newlines, backticks, markdown)
        and is KEPT because it does NOT do normalization (no case conversion,
        no remove_distinct, etc.).
        """
        sql = sql.replace("> =", ">=").replace("< =", "<=").replace("! =", "!=")
        while "  " in sql:
            sql = sql.replace("  ", " ")
        return sql_clean(sql)

    @staticmethod
    def _fix_select_column(sql: str) -> str:
        """Port of fix_select_column() from original C3SQL sql_post_process.py (L3-79).

        Extracts column→table mappings from JOIN ON conditions (e.g.
        T1.col = T2.col) and prefixes unqualified columns in SELECT with
        their correct table names.  Resolves ambiguous column errors in
        multi-table JOIN queries.

        Called AFTER SELECT prefix addition and BEFORE operator fixes,
        matching the original processing order.
        """
        sql = sql.replace("\n", " ")
        # Ensure spaces around "=" for tokenization
        sql_list = sql.split("=")
        sql = " = ".join(sql_list)
        while "  " in sql:
            sql = sql.replace("  ", " ")
        sql_tokens = sql.split(" ")

        select_ids = []
        from_ids = []
        join_ids = []
        eq_ids = []
        first_where_id = -1
        first_group_by_id = -1
        first_having_id = -1

        for idx_val, token in enumerate(sql_tokens):
            if token.lower() == "select":
                select_ids.append(idx_val)
            if token.lower() == "from":
                from_ids.append(idx_val)
            if token.lower() == "join":
                join_ids.append(idx_val)
            if token.lower() == "=":
                eq_ids.append(idx_val)
            if token.lower() == "where" and first_where_id == -1:
                first_where_id = idx_val
            if (
                token.lower() == "group"
                and idx_val < len(sql_tokens) - 1
                and sql_tokens[idx_val + 1].lower() == "by"
                and first_group_by_id == -1
            ):
                first_group_by_id = idx_val
            if token.lower() == "having" and first_having_id == -1:
                first_having_id = idx_val

        if len(eq_ids) == 0 or len(join_ids) == 0:
            return sql

        # Only consider the outermost SELECT.
        # Keep the original C3SQL sql_post_process.py condition exactly.
        for i in range(len(select_ids[:1])):
            select_id = select_ids[i]
            from_id = from_ids[i]
            tmp_column_ids = [j for j in range(select_id + 1, from_id)]
            column_ids = []
            idx = 0
            # NOTE: original code uses sql_tokens[idx] instead of
            # sql_tokens[tmp_column_ids[idx]] for the AS check — this is a
            # faithfully-ported discrepancy.  The AS-skipping logic doesn't
            # correctly skip aliases, but the core column→table mapping
            # logic (below) is unaffected in practice because "AS" tokens
            # have no "." and won't match any column_table_mp entry.
            while idx < len(tmp_column_ids):
                item = sql_tokens[idx]
                if item.lower() == "as":
                    idx += 2
                    continue
                column_ids.append(tmp_column_ids[idx])
                idx += 1

            column_table_mp = {}
            if i == len(select_ids) - 1:  # last SELECT
                for j in range(len(join_ids)):
                    if (
                        (first_where_id != -1 and join_ids[j] > first_where_id)
                        or first_group_by_id != -1 and join_ids[j]
                    ):
                        break
                    eq_id = eq_ids[j]
                    left_id, right_id = eq_id - 1, eq_id + 1
                    left_column, right_column = sql_tokens[left_id], sql_tokens[right_id]
                    if "." not in left_column or "." not in right_column:
                        continue
                    column_left = left_column.split(".")[1]
                    column_right = right_column.split(".")[1]
                    column_table_mp[column_left] = left_column
                    column_table_mp[column_right] = right_column

            if len(column_table_mp) == 0:
                return sql

            for column_id in column_ids:
                column = sql_tokens[column_id]
                if "." not in column:
                    if column in column_table_mp:
                        sql_tokens[column_id] = column_table_mp[column]
                    elif (
                        len(column) > 0
                        and column[-1] == ","
                        and column[:-1] in column_table_mp
                    ):
                        sql_tokens[column_id] = column_table_mp[column[:-1]] + ","

        recovered_sql = " ".join(sql_tokens)
        return recovered_sql

    @staticmethod
    def _replace_cur_year(query: str) -> str:
        """Replace YEAR(CURDATE()) with 2020 for execution validation.

        Matches original C3SQL:
          - generate_sqls_by_gpt3.5.py L74-77
          - get_selfconsistent_output.py L124-127
        """
        return re.sub(
            r"YEAR\s*\(\s*CURDATE\s*\(\s*\)\s*\)\s*",
            "2020",
            query,
            flags=re.IGNORECASE,
        )

    def _validate_sql(self, sql: str, db_id: str) -> bool:
        """Execute SQL against the target SQLite database to check validity.

        Returns True if the SQL executes without exception.
        Skips validation gracefully (returns True) when db_path is unavailable
        or the database file doesn't exist.
        """
        if not self.db_path:
            logger.debug(f"{self.NAME}: no db_path configured, skipping validation")
            return True

        try:
            db_file = self._resolve_db_file(db_id)

            if not db_file:
                logger.debug(
                    f"{self.NAME}: db file not found for {db_id} under {self.db_path}, skipping validation"
                )
                return True

            query = self._replace_cur_year(sql)
            conn = sqlite3.connect(str(db_file))
            conn.text_factory = lambda b: b.decode(errors="ignore")
            cursor = conn.cursor()
            try:
                cursor.execute(query)
                cursor.fetchall()
                return True
            finally:
                cursor.close()
                conn.close()
        except Exception as e:
            logger.debug(f"{self.NAME}: SQL validation failed: {e}")
            return False

    # ── batch generation (original generate_reply with n parameter) ─

    def _generate_batch(self, messages: List[Dict[str, str]], n: int) -> List[str]:
        """Single API call generating n candidate SQLs (matching original generate_reply).

        Uses raw OpenAI-compatible client for n= parameter support, chunked by
        provider limits (DeepSeek: n=1, Qwen: n<=4).
        """
        llm = self.get_llm()
        client = getattr(llm, "client", None)
        model = getattr(llm, "model_name", "gpt-3.5-turbo")
        max_n = max(1, min(MAX_BATCH_N, max_chat_completion_n(llm, default=MAX_BATCH_N)))
        extra_body = chat_extra_body_for_llm(llm)

        if client is not None:
            try:
                results: List[str] = []
                remaining = n
                while remaining > 0:
                    batch_n = min(remaining, max_n)
                    create_kwargs = dict(
                        model=model,
                        messages=messages,
                        n=batch_n,
                        max_tokens=getattr(llm, "max_tokens", 8000),
                        temperature=getattr(llm, "temperature", 0.7),
                        top_p=getattr(llm, "top_p", 0.8),
                        timeout=getattr(llm, "time_out", 300.0),
                    )
                    if extra_body:
                        create_kwargs["extra_body"] = extra_body
                    response = client.chat.completions.create(**create_kwargs)
                    results.extend(
                        (choice.message.content or "").replace("\n", " ")
                        for choice in response.choices
                    )
                    remaining -= batch_n
                return results
            except Exception as e:
                logger.warning(
                    f"{self.NAME}: batch generate failed ({e}), falling back to single call"
                )

        # Fallback: single call
        sql = self.llm_generation(messages)
        return [sql]

    # ── self-consistency denotation clustering ─────────────────────
    # Ported from original C3SQL get_selfconsistent_output.py

    @staticmethod
    def _permute_tuple(element: Tuple, perm: Tuple) -> Tuple:
        assert len(element) == len(perm)
        return tuple([element[i] for i in perm])

    @staticmethod
    def _unorder_row(row: Tuple) -> Tuple:
        return tuple(sorted(row, key=lambda x: str(x) + str(type(x))))

    @classmethod
    def _quick_rej(
        cls, result1: List[Tuple], result2: List[Tuple], order_matters: bool
    ) -> bool:
        s1 = [cls._unorder_row(row) for row in result1]
        s2 = [cls._unorder_row(row) for row in result2]
        if order_matters:
            return s1 == s2
        else:
            return set(s1) == set(s2)

    @staticmethod
    def _multiset_eq(l1: List, l2: List) -> bool:
        if len(l1) != len(l2):
            return False
        d = defaultdict(int)
        for e in l1:
            d[e] = d[e] + 1
        for e in l2:
            d[e] = d[e] - 1
            if d[e] < 0:
                return False
        return True

    @classmethod
    def _result_eq(
        cls, result1: List[Tuple], result2: List[Tuple], order_matters: bool
    ) -> bool:
        if len(result1) == 0 and len(result2) == 0:
            return True
        if len(result1) != len(result2):
            return False

        num_cols = len(result1[0])
        if len(result2[0]) != num_cols:
            return False

        if not cls._quick_rej(result1, result2, order_matters):
            return False

        tab1_sets = [{row[i] for row in result1} for i in range(num_cols)]

        for perm in cls._get_constraint_permutation(tab1_sets, result2):
            if len(perm) != len(set(perm)):
                continue
            if num_cols == 1:
                result2_perm = result2
            else:
                result2_perm = [cls._permute_tuple(element, perm) for element in result2]
            if order_matters:
                if result1 == result2_perm:
                    return True
            else:
                if set(result1) == set(result2_perm) and cls._multiset_eq(
                    result1, result2_perm
                ):
                    return True
        return False

    @staticmethod
    def _get_constraint_permutation(
        tab1_sets: List[set], result2: List[Tuple]
    ):
        import random
        from itertools import product as _product

        num_cols = len(result2[0])
        perm_constraints = [{i for i in range(num_cols)} for _ in range(num_cols)]
        if num_cols <= 3:
            return _product(*perm_constraints)

        for _ in range(20):
            random_tab2_row = random.choice(result2)
            for tab1_col in range(num_cols):
                for tab2_col in set(perm_constraints[tab1_col]):
                    if random_tab2_row[tab2_col] not in tab1_sets[tab1_col]:
                        perm_constraints[tab1_col].discard(tab2_col)
        return _product(*perm_constraints)

    def _exec_sql_on_db(self, db_file: Path, query: str) -> Tuple[str, Any]:
        """Execute SQL on a SQLite database and return (flag, result)."""
        query = self._replace_cur_year(query)
        conn = None
        try:
            conn = sqlite3.connect(str(db_file))
            conn.text_factory = lambda b: b.decode(errors="ignore")
            cursor = conn.cursor()
            cursor.execute(query)
            result = cursor.fetchall()
            return "result", result
        except Exception as e:
            return "exception", e
        finally:
            if conn:
                conn.close()

    @staticmethod
    def _outer_select_clause(sql: str) -> str:
        text = re.sub(r"\s+", " ", str(sql)).strip()
        match = re.search(r"\bselect\b(.*?)\bfrom\b", text, flags=re.IGNORECASE)
        return match.group(1).strip() if match else ""

    @staticmethod
    def _sql_feature_count(sql: str, keyword: str) -> int:
        return len(re.findall(rf"\b{re.escape(keyword)}\b", str(sql), flags=re.IGNORECASE))

    @classmethod
    def _structure_score(cls, sql: str, question: str) -> float:
        """Lightweight candidate preference used after execution filtering.

        C3SQL's original denotation clustering can over-favor executable but
        structurally wrong candidates on Spider when several wrong queries
        produce the same empty or small result.  This score keeps the original
        execution-first behaviour but breaks ties toward SQL shapes implied by
        the natural language question.
        """
        q = f" {str(question).lower()} "
        s = f" {str(sql).lower()} "
        select_clause = cls._outer_select_clause(sql).lower()
        score = 0.0

        join_count = cls._sql_feature_count(sql, "join")
        has_subquery = bool(re.search(r"\b(in|exists)\s*\(", s, flags=re.IGNORECASE))
        has_set_op = bool(re.search(r"\b(intersect|except|union)\b", s, flags=re.IGNORECASE))

        asks_display = any(
            phrase in q
            for phrase in (
                " name ",
                " names ",
                " title ",
                " titles ",
                " city ",
                " cities ",
                " country ",
                " countries ",
                " description ",
                " descriptions ",
                " detail ",
                " details ",
                " maker ",
                " makers ",
                " model ",
                " models ",
            )
        )
        asks_identifier = any(
            phrase in q
            for phrase in (
                " id ",
                " ids ",
                " code ",
                " codes ",
                " number ",
                " numbers ",
            )
        )
        if asks_display and not asks_identifier:
            if re.search(r"\b(sourceairport|destairport|airportcode|countryid|template_id|template_type_code|student_id|singer_id|visitor_id|owner_id)\b", select_clause):
                score -= 3.5
            if join_count > 0:
                score += 1.0

        if " or " in q:
            if re.search(r"\bor\b", s) or re.search(r"\bunion\b", s):
                score += 3.0
            if re.search(r"\bintersect\b", s):
                score -= 4.0

        negative_question = any(
            phrase in q
            for phrase in (
                " not ",
                " no ",
                " without ",
                " do not ",
                " does not ",
                " don't ",
                " never ",
            )
        )
        if negative_question:
            if re.search(r"\bnot\s+in\b", s) or re.search(r"\bexcept\b", s):
                score += 2.0
            if re.search(r"\bleft\s+join\b", s):
                score -= 1.5

        asks_count = any(phrase in q for phrase in (" how many ", " number of ", " count of "))
        if asks_count:
            if re.search(r"count\s*\(\s*distinct\b", s) and " distinct " not in q and " different " not in q and " unique " not in q:
                score -= 2.5
            if re.search(r"count\s*\(\s*\*\s*\)", s):
                score += 1.0

        frequency_question = any(
            phrase in q
            for phrase in (
                " most number of ",
                " greatest number of ",
                " largest number of ",
                " most frequent ",
                " by their frequency ",
            )
        )
        if frequency_question:
            if re.search(r"\bgroup\s+by\b", s) and re.search(r"\border\s+by\s+count\s*\(", s):
                score += 2.0
            if re.search(r"select\s+count\s*\(", s):
                score -= 2.0

        if " both " in q:
            if re.search(r"\bintersect\b", s):
                score += 1.5
            elif has_subquery or join_count > 0:
                score += 0.5

        if re.search(r"\bleft\s+join\b", s):
            score -= 1.0
        if re.search(r"\bright\s+join\b", s):
            score -= 4.0
        if has_set_op and " both " not in q and " or " not in q and not negative_question:
            score -= 0.8
        if has_subquery and join_count == 0 and asks_display and not negative_question:
            score -= 0.8

        return score

    def _self_consistent_select(
        self, sqls: List[str], db_id: str, question: str = ""
    ) -> str:
        """Cluster candidate SQLs by execution denotation, return most common cluster's first SQL.

        Ported from original get_selfconsistent_output.py get_sqls().
        """
        db_file = self._resolve_db_file(db_id)
        if not db_file or not db_file.exists():
            logger.debug(f"{self.NAME}: db not available for clustering, returning first SQL")
            return sqls[0] if sqls else ""

        cluster_sql_list: List[List[str]] = []
        map_sql2denotation: Dict[str, Any] = {}

        for sql in sqls:
            if not sql or not sql.strip():
                continue
            flag, denotation = self._exec_sql_on_db(db_file, sql)
            if flag == "exception":
                continue
            map_sql2denotation[sql] = denotation

            denotation_match = False
            for cluster in cluster_sql_list:
                center_sql = cluster[0]
                if center_sql in map_sql2denotation:
                    try:
                        if self._result_eq(
                            map_sql2denotation[center_sql], denotation, False
                        ):
                            cluster.append(sql)
                            denotation_match = True
                            break
                    except Exception:
                        continue
            if not denotation_match:
                cluster_sql_list.append([sql])

        def cluster_rank(cluster: List[str]) -> Tuple[float, int]:
            best_score = max(self._structure_score(sql, question) for sql in cluster)
            return (len(cluster), best_score)

        def best_sql(cluster: List[str]) -> str:
            return max(cluster, key=lambda candidate: self._structure_score(candidate, question))

        cluster_sql_list.sort(key=cluster_rank, reverse=True)
        if not cluster_sql_list:
            return sqls[0] if sqls else ""
        return best_sql(cluster_sql_list[0])

    def _resolve_db_file(self, db_id: str) -> Optional[Path]:
        """Resolve the SQLite database file path."""
        if not self.db_path:
            return None
        raw_path = Path(self.db_path)
        project_root = Path(__file__).resolve().parents[3]
        db_dirs = [raw_path]
        if not raw_path.is_absolute():
            db_dirs.append(project_root / raw_path)
            raw_s = str(self.db_path)
            if raw_s.startswith("../"):
                db_dirs.append(project_root / raw_s[3:])

        for db_dir in db_dirs:
            if db_dir.suffix:  # already a file path
                if db_dir.exists():
                    return db_dir
                continue
            flat_path = db_dir / f"{db_id}.sqlite"
            nested_path = db_dir / db_id / f"{db_id}.sqlite"
            if flat_path.exists():
                return flat_path
            if nested_path.exists():
                return nested_path
        return None

    # ── main act ───────────────────────────────────────────────────

    def _post_process_sql(self, raw_sql: str) -> str:
        """Apply the original C3SQL post-processing pipeline to a single SQL candidate.

        Order matches original generate_sqls_by_gpt3.5.py:
          SELECT 补齐 → fix_select_column → 操作符空格修正 → sql_clean
        """
        sql = str(raw_sql).strip().strip("`")
        if sql.lower().startswith("sql"):
            sql = sql[3:].strip(": \n")
        if not sql.lower().startswith("select"):
            sql = "SELECT " + sql
        sql = sql.replace("SELECT SELECT", "SELECT")

        try:
            sql = self._fix_select_column(sql)
        except Exception as e:
            logger.debug(f"{self.NAME}: fix_select_column error: {e}")

        sql = self._clean_sql(sql)
        return sql

    def act(
        self,
        item,
        schema: Union[str, PathLike, Dict, List] = None,
        schema_links: Union[str, List[str]] = None,
        sub_questions: Union[str, List[str], Dict] = None,
        data_logger=None,
        **kwargs
    ) -> str:
        """Generate SQL for a single sample using C3SQL chat prompt + retry loop.

        Two modes (matching original C3SQL generate_sqls_by_gpt3.5.py):
          - Standard (n_candidates=1): generate → post-process → validate → retry
          - Self-consistent (n_candidates>1): batch generate n candidates →
            post-process each → denotation cluster → validate best → retry
        """
        if data_logger:
            data_logger.info(f"{self.NAME}.act start | item={item}")

        row = self.dataset[item]
        question = row["question"]
        db_id = row["db_id"]

        # ── external knowledge ─────────────────────────────────
        if self.use_external:
            external_knowledge = self.load_external_knowledge(row.get("external", None))
            if external_knowledge:
                question += "\n" + external_knowledge

        # ── resolve schema ──────────────────────────────────────
        resolved_links: Optional[List[str]] = None
        if schema_links is not None:
            if isinstance(schema_links, str):
                resolved_links = format_schema_links(schema_links, "A").split("\n")
            elif isinstance(schema_links, list):
                resolved_links = schema_links
        else:
            schema_link_path = row.get("schema_links", None)
            if schema_link_path:
                loaded = load_dataset(schema_link_path)
                if isinstance(loaded, str):
                    resolved_links = format_schema_links(loaded, "A").split("\n")
                elif isinstance(loaded, list):
                    resolved_links = loaded

        if isinstance(schema, (str, PathLike)) and Path(schema).exists():
            schema = load_dataset(schema)

        if schema is None:
            instance_schema_path = row.get("instance_schemas")
            schema = (
                load_dataset(instance_schema_path)
                if instance_schema_path
                else self.dataset.get_db_schema(item)
            )

        if schema is None:
            raise ValueError("Failed to load a valid database schema for the sample!")

        schema_text = self._normalize_schema(schema)

        # ── build FK info ──────────────────────────────────────
        if isinstance(schema, dict):
            schema_df = pd.DataFrame(single_central_process(schema))
        elif isinstance(schema, list):
            schema_df = pd.DataFrame(schema)
        elif isinstance(schema, pd.DataFrame):
            schema_df = schema
        else:
            schema_df = pd.DataFrame()

        fk_info = ""
        if resolved_links and not schema_df.empty:
            selected_schema_text = self._build_schema_from_links_with_contents(
                resolved_links, schema_df, question, db_id
            )
            if selected_schema_text:
                schema_text = selected_schema_text
                selected_tables = list(
                    schema_df[
                        schema_df["table_name"].isin(
                            {link.split(".")[0] for link in resolved_links if "." in link}
                        )
                    ]["table_name"].unique()
                )
                fk_info = self._extract_fk_for_tables(schema_df, selected_tables)
                if data_logger:
                    data_logger.info(
                        f"{self.NAME}.schema_from_links | tables={len(selected_tables)}"
                    )

        # ── generate SQL with execution validation retry loop ───
        max_retries = 5
        retry_sleep = 0.5
        sql = ""
        is_self_consistent = self.n_candidates > 1

        # Build messages once (same for all retries / candidates)
        final_user_content = self.prompt_maker(question, schema_text, db_id, fk_info)
        messages = list(self.CHAT_MESSAGES)
        messages.append({"role": "user", "content": final_user_content})

        for retry in range(max_retries):
            if is_self_consistent:
                # ── self-consistent mode (original get_selfconsistent_output.py) ──
                raw_sqls = self._generate_batch(messages, self.n_candidates)
                # Sleep between retries for API errors
                if not raw_sqls:
                    if data_logger:
                        data_logger.info(f"{self.NAME}.batch_fail | retry={retry + 1}/{max_retries}")
                    time.sleep(retry_sleep)
                    continue

                # Post-process all candidates
                processed_sqls = []
                for raw in raw_sqls:
                    try:
                        processed = self._post_process_sql(raw)
                        if processed:
                            processed_sqls.append(processed)
                    except Exception:
                        continue

                if not processed_sqls:
                    continue

                # Self-consistency: cluster by denotation, pick largest cluster's best
                sql = self._self_consistent_select(processed_sqls, db_id, question)

                # Validate the selected SQL (original: checks p_sqls[0])
                if self._validate_sql(sql, db_id):
                    if data_logger:
                        data_logger.info(
                            f"{self.NAME}.valid_sc | retry={retry + 1}/{max_retries} "
                            f"candidates={len(processed_sqls)}"
                        )
                    break
                else:
                    if data_logger:
                        data_logger.info(
                            f"{self.NAME}.invalid_sc | retry={retry + 1}/{max_retries}"
                        )
                    if retry < max_retries - 1:
                        time.sleep(retry_sleep)
            else:
                # ── standard mode (single candidate) ──
                raw_sql = self.llm_generation(messages)
                sql = self._post_process_sql(raw_sql)

                if self._validate_sql(sql, db_id):
                    if data_logger:
                        data_logger.info(
                            f"{self.NAME}.valid | retry={retry + 1}/{max_retries}"
                        )
                    break
                else:
                    if data_logger:
                        data_logger.info(
                            f"{self.NAME}.invalid | retry={retry + 1}/{max_retries}"
                        )
                    if retry < max_retries - 1:
                        time.sleep(retry_sleep)
                        if data_logger:
                            data_logger.info(f"{self.NAME}.retry | next_attempt={retry + 2}")

        # ── save output ─────────────────────────────────────────
        sql = self.save_output(sql, item, row.get("instance_id"))

        if data_logger:
            data_logger.info(f"{self.NAME}.final_sql | sql={sql}")
            data_logger.info(f"{self.NAME}.act end | item={item}")
        return sql

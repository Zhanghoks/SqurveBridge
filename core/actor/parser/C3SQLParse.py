"""
C3SQL Parser — Column Recall via LLM Self-Consistency

Reproduces the column_recall.py logic from the original C3SQL method:
  - For each selected table, LLM ranks columns by relevance
  - Self-consistency: sample sc_num times via single batch API call (n=sc_num)
  - Vote: top-4 columns per ranking → Counter.most_common(5)
  - Auto-add FK columns
  - Output schema_links as a list of "table.column" strings
  - API failure triggers retry loop (matching original while tabs_cols_all is None)

Alignments from original column_recall.py:
  - generate_schema(): includes db_contents in column format
  - generate_reply(): single ChatCompletion.create with n=sc_num
  - column_sc(): top-4 per ranking → Counter.most_common(5) → append FK
  - Question prompt: "### " prefix matching original
"""

import json
import re
import time
from collections import Counter
from os import PathLike
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Union

import pandas as pd
from llama_index.core.llms.llm import LLM
from loguru import logger

from core.actor.parser.BaseParse import BaseParser
from core.data_manage import Dataset
from core.llm.completion_limits import chat_extra_body_for_llm, max_chat_completion_n
from core.utils import load_dataset


# Default chunk size when the provider allows multi-sample `n` (e.g. Qwen).
MAX_BATCH_N = 4

# ── original C3SQL column-recall instruction (verbatim) ───────────────────
COLUMN_RECALL_INSTRUCTION = """Given the database tables and question, perform the following actions:
1 - Rank the columns in each table based on the possibility of being used in the SQL, Column that matches more with the question words or the foreign key is highly relevant and must be placed ahead. You should output them in the order of the most relevant to the least relevant.
Explain why you choose each column.
2 - Output a JSON object that contains all the columns in each table according to your explanation. The format should be like:
{
    "table_1": ["column_1", "column_2", ......],
    "table_2": ["column_1", "column_2", ......],
    "table_3": ["column_1", "column_2", ......],
     ......
}

"""


@BaseParser.register_actor
class C3SQLParser(BaseParser):
    """C3SQL Column Recall: LLM ranks columns → self-consistency voting → schema_links."""

    NAME = "C3SQLParser"

    SKILL = """# C3SQLParser

C3SQL Column Recall — LLM ranks columns per table by relevance,
self-consistency voting picks the most frequent top-k columns per table,
FK columns are auto-added. Outputs schema_links.

Matches original column_recall.py: batch LLM call (n=sc_num),
retry loop on API failure, column_sc() top-4→Counter.most_common(5).

## Inputs
- `schema`: already-reduced schema (from Reducer or dataset).
- Dataset row with `question`, `fk` info.

## Output
`schema_links` — list of "table.column" strings.
"""

    def __init__(
        self,
        dataset: Optional[Dataset] = None,
        llm: Optional[LLM] = None,
        output_format: str = "list",
        is_save: bool = True,
        save_dir: Union[str, PathLike] = "../files/schema_links",
        use_external: bool = False,
        sc_num: int = 10,          # self-consistency sample count
        top_k: int = 5,            # columns per table to keep (original column_sc: 5)
        add_fk: bool = True,       # auto-add FK columns
        db_path: Optional[Union[str, PathLike]] = None,
        use_db_contents: bool = True,
        max_retry_times: int = 3,
        temperature: Optional[float] = None,
        **kwargs,
    ):
        super().__init__(dataset, llm, output_format, is_save, save_dir, use_external, **kwargs)
        self.sc_num = max(1, int(sc_num))
        self.top_k = max(1, int(top_k))
        self.add_fk = add_fk
        self.db_path = db_path or (getattr(dataset, "db_path", None) if dataset else None)
        self.use_db_contents = use_db_contents
        self.max_retry_times = max(1, int(max_retry_times))
        self.temperature = temperature

    # ── prompt helpers ───────────────────────────────────────────────

    def _schema_to_text(self, schema_df: pd.DataFrame, question: str = "") -> str:
        """Convert schema DataFrame to C3SQL column-recall text with db_contents.

        Matches original column_recall.py generate_schema():
          # table_name ( col1, col2 ( "val1", "val2" ), col3 )
        """
        from core.actor.bridge_content import get_db_contents

        lines = []
        grouped = schema_df.groupby("table_name")
        for table_name, group in grouped:
            col_names = list(group["column_name"])

            # Fetch db_contents if enabled
            db_contents_per_col = None
            if self.use_db_contents and self.db_path and question:
                try:
                    db_id = getattr(self, "_act_db_id", None) or ""
                    db_file = self._resolve_db_file_for_id(db_id)
                    if db_file and Path(db_file).exists():
                        db_contents_per_col = get_db_contents(
                            question=question,
                            table_name=table_name,
                            column_names=col_names,
                            db_path=str(db_file),
                            top_k_matches=2,
                        )
                except Exception:
                    db_contents_per_col = None

            # Build line with optional contents
            parts = [f"# {table_name} ( "]
            for i, col in enumerate(col_names):
                col_str = col
                if db_contents_per_col and i < len(db_contents_per_col):
                    contents = db_contents_per_col[i]
                    if contents:
                        quoted = ", ".join(f'"{v}"' for v in contents[:2])
                        col_str = f"{col} ( {quoted} )"
                parts.append(f"{col_str}, ")
            line = "".join(parts).rstrip(", ") + " )"
            lines.append(line)

        return "\n".join(lines)

    def _resolve_db_file_for_id(self, db_id: str) -> Optional[Path]:
        """Resolve SQLite DB path for a specific db_id."""
        if not self.db_path:
            return None
        db_path = Path(self.db_path)
        if db_path.suffix == ".sqlite":
            return db_path
        flat_candidate = db_path / f"{db_id}.sqlite"
        if flat_candidate.exists():
            return flat_candidate
        candidate = db_path / db_id / f"{db_id}.sqlite"
        if candidate.exists():
            return candidate
        return None

    @staticmethod
    def _parse_fk_edges(schema_df: pd.DataFrame) -> List[Tuple[str, str, str, str]]:
        """Return FK edges as (src_table, src_col, ref_table, ref_col).

        Squrve schemas store FK on the child column as ``[ref_table(ref_col)]``.
        Some candidate-style intermediate data may already use
        ``src_table.src_col = ref_table.ref_col``.  Normalize both to the
        candidate C3SQL FK line format used in prompts.
        """
        edges: List[Tuple[str, str, str, str]] = []
        for _, row in schema_df.iterrows():
            src_table = str(row.get("table_name", "")).strip()
            src_col = str(row.get("column_name", "")).strip()
            fk_val = row.get("foreign_key", "")
            if not fk_val or not isinstance(fk_val, str) or not fk_val.strip():
                continue

            fk_val = fk_val.strip()
            if "=" in fk_val:
                parts = fk_val.split("=")
                if len(parts) == 2 and "." in parts[0] and "." in parts[1]:
                    left_table, left_col = [p.strip().strip("[]") for p in parts[0].split(".", 1)]
                    right_table, right_col = [p.strip().strip("[]") for p in parts[1].split(".", 1)]
                    edges.append((left_table, left_col, right_table, right_col))
                continue

            for ref_table, ref_col in re.findall(r"\[([^\[\]()]+)\(([^)]*)\)\]", fk_val):
                ref_table = ref_table.strip()
                ref_col = ref_col.strip()
                if src_table and src_col and ref_table and ref_col:
                    edges.append((src_table, src_col, ref_table, ref_col))
        return edges

    @staticmethod
    def _extract_fk_info(schema_df: pd.DataFrame) -> Tuple[str, Dict[str, List[str]]]:
        """Extract FK strings and a dict of table→[fk_columns] from schema_df.

        Matches original column_recall.py extract_fks().
        """
        fk_lines = []
        fk_columns: Dict[str, List[str]] = {}

        for left_table, left_col, right_table, right_col in C3SQLParser._parse_fk_edges(schema_df):
            fk_lines.append(f"{left_table}.{left_col} = {right_table}.{right_col}")
            for tbl, col in ((left_table, left_col), (right_table, right_col)):
                if tbl not in fk_columns:
                    fk_columns[tbl] = []
                if col not in fk_columns[tbl]:
                    fk_columns[tbl].append(col)

        fk_str = "\n".join(fk_lines) if fk_lines else ""
        return fk_str, fk_columns

    @staticmethod
    def _parse_column_json(raw: str) -> Dict[str, List[str]]:
        """Parse LLM output into {table_name: [col1, col2, ...]} dict.

        Matches original column_recall.py generate_reply parsing:
          '{' + raw.split('{', 1)[1], rsplit('}', 1)[0] + '}', json.loads()
        """
        text = raw.strip()
        try:
            if "{" in text:
                text = "{" + text.split("{", 1)[1]
                text = text.rsplit("}", 1)[0] + "}"
            return json.loads(text)
        except json.JSONDecodeError:
            logger.warning(f"C3SQLParser: failed to parse JSON from LLM output")
            return {}

    @classmethod
    def _build_column_recall_prompt(
        cls, question: str, schema_text: str, fk_str: str
    ) -> str:
        """Build column recall prompt matching original column_recall.py format.

        Original format:
          instruction + "Schema:\n" + schema
          + "Foreign keys:\n# " + fk_str
          + "\nQuestion:\n### " + question
        """
        prompt = COLUMN_RECALL_INSTRUCTION + "Schema:\n" + schema_text
        prompt += "Foreign keys:\n"
        if fk_str:
            for fk_line in fk_str.split("\n"):
                prompt += f"# {fk_line}\n"
        prompt += "\nQuestion:\n### " + question
        return prompt

    # ── LLM batch generation (original generate_reply) ─────────────

    def _generate_reply_batch(self, prompt: str, n: int) -> Optional[List[str]]:
        """Generate n responses via OpenAI-compatible batch API.

        Uses raw client with n=sc_num when supported; splits into provider-safe
        chunks (DeepSeek: n=1, Qwen: n<=4).
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
                        messages=[{"role": "user", "content": prompt}],
                        temperature=(
                            self.temperature
                            if self.temperature is not None
                            else getattr(llm, "temperature", 0.7)
                        ),
                        n=batch_n,
                        max_tokens=getattr(llm, "max_tokens", 8000),
                        timeout=getattr(llm, "time_out", 300.0),
                    )
                    if extra_body:
                        create_kwargs["extra_body"] = extra_body
                    response = client.chat.completions.create(**create_kwargs)
                    results.extend(
                        choice.message.content for choice in response.choices
                    )
                    remaining -= batch_n
                return results
            except Exception as e:
                logger.warning(
                    f"{self.NAME}: batch generate failed ({e}), falling back to sequential"
                )

        # Fallback: sequential calls
        results = []
        for _ in range(n):
            try:
                response = llm.complete(prompt)
                text = getattr(response, "text", str(response)).strip()
                if text:
                    results.append(text)
            except Exception as e:
                logger.warning(f"{self.NAME}: single generate failed: {e}")
        return results if results else None

    # ── self-consistency voting ──────────────────────────────────────

    @classmethod
    def _vote_columns(
        cls,
        all_results: List[Dict[str, List[str]]],
        table_columns: Dict[str, List[str]],
        top_k: int,
    ) -> Dict[str, List[str]]:
        """Self-consistency voting matching original column_sc().

        Original logic:
          1. For each ranking, take first 4 columns that exist in schema.
          2. Aggregate all surviving columns.
          3. Counter.most_common(5) → pick top 5.
        """
        if not all_results:
            return {}

        # Collect per-table column candidates (original: filter to top 4 per ranking)
        candidates: Dict[str, List[str]] = {}
        for result in all_results:
            for table, cols in result.items():
                if table not in table_columns:
                    continue
                if table not in candidates:
                    candidates[table] = []
                cols_ori_lower = [c.lower() for c in table_columns[table]]
                cols_exist = []
                for col in cols:
                    if col.lower() in cols_ori_lower:
                        # Map back to original casing
                        idx = cols_ori_lower.index(col.lower())
                        cols_exist.append(table_columns[table][idx])
                    if len(cols_exist) == 4:  # original passes top 4 per ranking
                        break
                if cols_exist:
                    candidates[table].append(cols_exist)

        # Per table: flatten all ranking results, Counter.most_common(5)
        selected: Dict[str, List[str]] = {}
        for table, col_rankings in candidates.items():
            cols_add = []
            for cols in col_rankings:
                cols_add.extend(cols)
            counter = Counter(cols_add)
            most_common = counter.most_common(top_k)
            selected[table] = [value for value, _ in most_common]

        return selected

    # ── main act ─────────────────────────────────────────────────────

    def act(self, item, schema=None, data_logger=None, update_dataset=True, **kwargs):
        """Execute C3SQL column recall for a single sample.

        Matches original column_recall.py: batch LLM call, retry loop,
        pass-4 per ranking → Counter.most_common(5), FK auto-add.
        """
        if data_logger:
            data_logger.info(f"{self.NAME}.act start | item={item}")

        row = self.dataset[item]
        question = row["question"]
        db_id = row.get("db_id", "")
        self._act_db_id = db_id

        # ── load schema (prefer instance_schemas from Reducer) ────
        schema_df = self.process_schema(item, schema)
        if not isinstance(schema_df, pd.DataFrame):
            raise ValueError(f"Expected DataFrame, got {type(schema_df)}")

        # ── resolve db_file for db_contents ───────────────────────
        db_file = None
        if self.use_db_contents:
            db_file = self._resolve_db_file_for_id(db_id)

        # ── build schema text with db_contents ────────────────────
        original_db_path = self.db_path
        if db_file:
            self.db_path = str(db_file)
        schema_text = self._schema_to_text(schema_df, question)
        self.db_path = original_db_path

        fk_str, fk_columns = self._extract_fk_info(schema_df)

        # Build table→columns lookup
        table_columns: Dict[str, List[str]] = {}
        for table_name, group in schema_df.groupby("table_name"):
            table_columns[table_name] = list(group["column_name"])

        if data_logger:
            data_logger.info(
                f"{self.NAME}.context | tables={len(table_columns)} "
                f"cols={sum(len(v) for v in table_columns.values())}"
            )

        # ── self-consistency sampling with retry loop ─────────────
        prompt = self._build_column_recall_prompt(question, schema_text, fk_str)
        sc_num = self.sc_num if self.sc_num > 1 else 1

        raw_replies = None
        for retry_idx in range(self.max_retry_times):
            try:
                raw_replies = self._generate_reply_batch(prompt, sc_num)
                if raw_replies is not None:
                    break
                logger.warning(
                    f"{self.NAME}: batch generate returned None "
                    f"({retry_idx + 1}/{self.max_retry_times})"
                )
                time.sleep(3)
            except Exception as e:
                logger.warning(
                    f"{self.NAME}: API error ({e}), waiting 3s "
                    f"({retry_idx + 1}/{self.max_retry_times})"
                )
                time.sleep(3)
        if raw_replies is None:
            logger.warning(f"{self.NAME}: retry limit reached, using all-column fallback")
            raw_replies = []

        all_results = []
        for reply in raw_replies:
            parsed = self._parse_column_json(reply)
            if parsed:
                all_results.append(parsed)

        if data_logger:
            data_logger.info(
                f"{self.NAME}.sample | parsed={len(all_results)}/{len(raw_replies)}"
            )

        if not all_results:
            logger.warning("C3SQLParser: all LLM calls failed, returning all columns")
            # Fallback: return all columns
            selected: Dict[str, List[str]] = {}
            for tbl, cols in table_columns.items():
                selected[tbl] = cols[: self.top_k]
        else:
            selected = self._vote_columns(all_results, table_columns, self.top_k)

        # ── auto-add FK columns (original: add_fk=True) ───────────
        if self.add_fk and fk_columns:
            for table, fk_cols in fk_columns.items():
                if table in selected:
                    for col in fk_cols:
                        if col not in selected[table]:
                            selected[table].append(col)

        # ── format output as schema_links ─────────────────────────
        schema_links = []
        for table, cols in selected.items():
            for col in cols:
                schema_links.append(f"{table}.{col}")

        self.log_schema_links(data_logger, schema_links, stage="final")
        output = self.format_output(schema_links)

        if update_dataset:
            file_ext = ".txt" if self.output_format == "str" else ".json"
            self.save_output(output, item, file_ext=file_ext)

        if data_logger:
            data_logger.info(f"{self.NAME}.act end | links={len(schema_links)}")
        return output

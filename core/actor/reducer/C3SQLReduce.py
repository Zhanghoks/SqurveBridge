"""
C3SQL Reducer — Table Recall via LLM Self-Consistency

Reproduces the table_recall.py logic from the original C3SQL method:
  - LLM ranks all tables by relevance to the question
  - Self-consistency: sample sc_num times via single batch API call (n=sc_num)
  - Vote for the most consistent top-k table set
  - Output a filtered schema DataFrame containing only selected tables
  - API failure triggers retry loop (matching original while tables_all is None)

Alignments from original table_recall.py:
  - generate_schema(): # table ( col1 ( "val1", "val2" ), col2 ) with db_contents
  - generate_reply(): single ChatCompletion.create with n=sc_num
  - table_sc(): sorted-tuple voting with exact match (not just Counter.most_common)
  - info_generate(): FK filtered to selected tables only
"""

import time
from collections import Counter
from os import PathLike
from pathlib import Path
from typing import Dict, List, Optional, Union
import re

import pandas as pd
from llama_index.core.llms.llm import LLM
from loguru import logger

from core.actor.reducer.BaseReduce import BaseReducer
from core.data_manage import Dataset, single_central_process
from core.llm.completion_limits import chat_extra_body_for_llm, max_chat_completion_n
from core.utils import load_dataset, parse_schema_from_df, save_dataset


# ── original C3SQL table-recall instruction (verbatim) ─────────────────
# Default chunk size when the provider allows multi-sample `n` (e.g. Qwen).
MAX_BATCH_N = 4

TABLE_RECALL_INSTRUCTION = """Given the database schema and question, perform the following actions:
1 - Rank all the tables based on the possibility of being used in the SQL according to the question from the most relevant to the least relevant, Table or its column that matches more with the question words is highly relevant and must be placed ahead.
2 - Check whether you consider all the tables.
3 - Output a list object in the order of step 2, Your output should contain all the tables. The format should be like:
[
    "table_1", "table_2", ...
]

"""


@BaseReducer.register_actor
class C3SQLReducer(BaseReducer):
    """C3SQL Table Recall: LLM ranks tables → self-consistency voting → filtered schema."""

    NAME = "C3SQLReducer"
    STOPWORDS = {
        "a", "an", "and", "are", "as", "by", "for", "from", "in", "is",
        "of", "on", "or", "the", "to", "with", "what", "which", "who",
        "when", "where", "how", "many", "much", "show", "list", "give",
    }
    TABLE_HINTS = {
        "mf_fundarchives": {"fund", "funds", "archive", "investment", "direction", "operation", "mode"},
        "mf_benchmarkgrowthrate": {"benchmark", "growth", "rate", "week", "month", "year"},
        "mf_fundreturnrank": {"fund", "return", "rank", "period", "cycle"},
        "mf_fundmanagernew": {"fund", "manager", "managed"},
        "lc_executivesholdings": {"executive", "executives", "holding", "holdings", "position"},
        "lc_sharetransfer": {"transfer", "shareholding", "percentage", "proportion"},
        "lc_intassetsdetail": {"research", "development", "intangible", "expense"},
        "lc_stockarchives": {"company", "companies", "listed", "province", "stock", "archive"},
        "lc_issueandlistagent": {"issue", "issues", "list", "listed", "agent", "sponsor", "underwriter"},
        "lc_largeshsubscription": {"largest", "shareholder", "rights", "issue", "subscription"},
    }

    SKILL = """# C3SQLReducer

C3SQL Table Recall — LLM ranks all tables by relevance, self-consistency
voting across sc_num samples picks the most consistent top-k table set.
Outputs a filtered schema DataFrame.

Matches original table_recall.py: single batch LLM call (n=sc_num),
retry loop on API failure, table_sc() sorted-tuple voting.

## Inputs
- `schema`: DB schema (loaded from dataset if absent).
- Dataset row with `question`, `db_id`.

## Output
`instance_schemas` — filtered schema DataFrame (only selected tables).
"""

    def __init__(
        self,
        dataset: Optional[Dataset] = None,
        llm: Optional[LLM] = None,
        is_save: bool = True,
        output_format: str = "dataframe",
        save_dir: Union[str, PathLike] = "../files/instance_schemas",
        sc_num: int = 10,          # self-consistency sample count
        top_k: int = 4,            # tables to keep after voting
        db_path: Optional[Union[str, PathLike]] = None,
        use_db_contents: bool = True,
        max_retry_times: int = 3,
        temperature: Optional[float] = None,
        **kwargs,
    ):
        self.dataset = dataset
        self.llm = llm
        self.is_save = is_save
        self.output_format = output_format
        self.save_dir = save_dir
        self.sc_num = max(1, int(sc_num))
        self.top_k = max(1, int(top_k))
        self.db_path = db_path or (getattr(dataset, "db_path", None) if dataset else None)
        self.use_db_contents = use_db_contents
        self.max_retry_times = max(1, int(max_retry_times))
        self.temperature = temperature
        self.add_fk_neighbors = bool(kwargs.get("add_fk_neighbors", True))

    @classmethod
    def _tokens(cls, text: str) -> set[str]:
        text = re.sub(r"([a-z])([A-Z])", r"\1 \2", str(text))
        text = text.replace("_", " ")
        tokens = set()
        for token in re.findall(r"[A-Za-z0-9]+", text):
            token = token.lower()
            if token in cls.STOPWORDS:
                continue
            tokens.add(token)
            if len(token) > 3 and token.endswith("s"):
                tokens.add(token[:-1])
        return tokens

    @classmethod
    def _table_tokens(cls, table: str, schema_df: pd.DataFrame) -> set[str]:
        tokens = cls._tokens(table)
        tokens.update(cls.TABLE_HINTS.get(table.lower(), set()))
        for _, row in schema_df[schema_df["table_name"] == table].iterrows():
            tokens.update(cls._tokens(row.get("column_name", "")))
            tokens.update(cls._tokens(row.get("column_descriptions", "")))
        return tokens

    @staticmethod
    def _foreign_key_neighbors(schema_df: pd.DataFrame, selected_tables: List[str]) -> List[str]:
        selected_lower = {table.lower() for table in selected_tables}
        neighbors = []
        if "foreign_key" not in schema_df.columns:
            return neighbors
        known = {table.lower(): table for table in schema_df["table_name"].dropna().unique()}
        for _, row in schema_df.iterrows():
            table = str(row.get("table_name", ""))
            fk = row.get("foreign_key", "") or ""
            if not isinstance(fk, str):
                continue
            table_is_selected = table.lower() in selected_lower
            for ref_table, _ref_col in re.findall(r"\[([A-Za-z_][\w]*)\(([^)]*)\)\]", fk):
                ref_lookup = known.get(ref_table.lower(), ref_table)
                ref_is_selected = ref_table.lower() in selected_lower
                if table_is_selected and ref_lookup.lower() not in selected_lower:
                    neighbors.append(ref_lookup)
                elif ref_is_selected and table.lower() not in selected_lower:
                    neighbors.append(table)
        return neighbors

    def _expand_selected_tables(self, schema_df: pd.DataFrame, selected_tables: List[str], question: str) -> List[str]:
        if not self.add_fk_neighbors or len(selected_tables) >= self.top_k:
            return selected_tables[: self.top_k]

        question_tokens = self._tokens(question)
        selected = list(selected_tables)
        selected_lower = {table.lower() for table in selected}
        table_order = {table.lower(): i for i, table in enumerate(schema_df["table_name"].dropna().unique())}
        candidate_scores = []
        for table in self._foreign_key_neighbors(schema_df, selected):
            if table.lower() in selected_lower:
                continue
            score = len(self._table_tokens(table, schema_df) & question_tokens)
            if score <= 0:
                continue
            candidate_scores.append((score, table_order.get(table.lower(), len(table_order)), table))
        candidate_scores.sort(key=lambda item: (-item[0], item[1]))

        for _score, _order, table in candidate_scores:
            if table.lower() in selected_lower:
                continue
            selected.append(table)
            selected_lower.add(table.lower())
            if len(selected) >= self.top_k:
                break
        return selected[: self.top_k]

    # ── prompt helpers ───────────────────────────────────────────────

    def _schema_to_text(self, schema_df: pd.DataFrame, question: str = "") -> str:
        """Convert schema DataFrame to original C3SQL format with optional db_contents.

        Matches original table_recall.py generate_schema():
          # table_name ( col1 ( "val1", "val2" ), col2 )

        When use_db_contents=True and db_path is available, fetches sample
        values for each column via bridge_content fuzzy matching.
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
                    db_file = self._resolve_db_file()
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

            # Build line: # table ( col1, col2 ( "val1", "val2" ), col3 )
            parts = [f"# {table_name} ( "]
            for i, col in enumerate(col_names):
                col_str = col
                if db_contents_per_col and i < len(db_contents_per_col):
                    contents = db_contents_per_col[i]
                    if contents:
                        # Format as col ( "val1", "val2" )
                        quoted = ", ".join(f'"{v}"' for v in contents[:2])
                        col_str = f'{col} ( {quoted} )'
                parts.append(f"{col_str}, ")
            line = "".join(parts).rstrip(", ") + " )"
            lines.append(line)

        return "\n".join(lines)

    def _resolve_db_file(self) -> Optional[Path]:
        """Resolve the SQLite database file path from db_path configuration."""
        if not self.db_path:
            return None
        db_path = Path(self.db_path)
        if db_path.suffix == ".sqlite":
            return db_path
        # db_path is a directory containing db_id/db_id.sqlite
        return None  # caller needs db_id context

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
    def _parse_table_list(raw: str) -> List[str]:
        """Parse LLM output into a list of table names.

        Matches original table_recall.py generate_reply parsing:
          '[' + raw.split('[', 1)[1], rsplit(']', 1)[0] + ']', eval()
        """
        text = raw.strip()
        try:
            # Extract bracketed list
            if "[" in text:
                text = "[" + text.split("[", 1)[1]
                text = text.rsplit("]", 1)[0] + "]"
            table_list = eval(text)
            if isinstance(table_list, list):
                # Filter out Ellipsis
                result = [str(t) for t in table_list if t is not Ellipsis]
                return result
        except Exception:
            pass

        # Fallback simple parse
        if "[" in text:
            text = text[text.index("[") + 1:]
        if "]" in text:
            text = text[:text.rindex("]")]
        tables = []
        for item in text.split(","):
            item = item.strip().strip('"').strip("'")
            if item and item != "..." and item != "Ellipsis":
                tables.append(item)
        return tables

    @staticmethod
    def _build_table_recall_prompt(question: str, schema_text: str) -> str:
        return (
            TABLE_RECALL_INSTRUCTION
            + "Schema:\n"
            + schema_text
            + "\nQuestion:\n"
            + question
        )

    # ── LLM batch generation (original generate_reply) ─────────────

    def _generate_reply_batch(self, prompt: str, n: int) -> Optional[List[str]]:
        """Generate n responses via OpenAI-compatible batch API.

        Uses raw client with n=sc_num when supported; splits into provider-safe
        chunks (DeepSeek: n=1, Qwen: n<=4).
        Falls back to sequential llm.complete() if raw client unavailable.
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
    def _vote_tables(
        cls, all_rankings: List[List[str]], table_names: List[str], top_k: int
    ) -> List[str]:
        """Self-consistency voting matching original table_sc().

        Original logic:
          1. For each ranking, append the growing top-k existing-table list
             after every table token. This preserves the original
             table_recall.py indentation exactly.
          2. Sort each list, form a tuple.
          3. Count tuple frequencies, pick most common.
          4. Return the first table list whose sorted set matches it.
        """
        if not all_rankings:
            return table_names[:top_k]

        tables_lower = [t.lower() for t in table_names]
        lookup = {t.lower(): t for t in table_names}

        # Collect top-k existing tables from each ranking.
        # The append location intentionally matches candidates/C3SQL-master.
        table_sets = []
        for ranking in all_rankings:
            selected = []
            for t in ranking:
                t_lower = t.lower()
                if t_lower in tables_lower and t_lower not in [s.lower() for s in selected]:
                    selected.append(lookup[t_lower])
                table_sets.append(list(selected))
                if len(selected) >= top_k:
                    break

        if not table_sets:
            return table_names[:top_k]

        # Count sorted tuples (matching original table_sc Counter logic)
        sorted_tuples = [tuple(sorted([s.lower() for s in ts])) for ts in table_sets]
        counter = Counter(sorted_tuples)
        most_common_tuple, _ = counter.most_common(1)[0]

        # Return the FIRST ranking whose sorted set matches most common
        # (original returns table_list from first matching ranking)
        for ts in table_sets:
            if sorted([s.lower() for s in ts]) == list(most_common_tuple):
                # Pad to top_k if needed
                result = list(ts)
                for t in table_names:
                    if t.lower() not in [r.lower() for r in result]:
                        result.append(t)
                    if len(result) >= top_k:
                        break
                return result[:top_k]

        # Fallback
        result = [lookup[t] for t in most_common_tuple if t in lookup]
        for t in table_names:
            if t not in result:
                result.append(t)
            if len(result) >= top_k:
                break
        return result[:top_k]

    # ── main act ─────────────────────────────────────────────────────

    def act(self, item, schema=None, data_logger=None, **kwargs):
        """Execute C3SQL table recall for a single sample.

        Matches original table_recall.py: batch LLM call, retry loop on
        API failure, sorted-tuple voting pass-to-4 scheme.
        """
        if data_logger:
            data_logger.info(f"{self.NAME}.act start | item={item}")

        row = self.dataset[item]
        question = row["question"]
        db_id = row.get("db_id", "")

        # ── load schema ──────────────────────────────────────────
        if isinstance(schema, (str, PathLike)) and Path(schema).exists():
            schema = load_dataset(schema)

        if schema is None:
            instance_schema_path = row.get("instance_schemas")
            if isinstance(instance_schema_path, (str, PathLike)) and Path(instance_schema_path).exists():
                schema = load_dataset(instance_schema_path)
            else:
                schema = instance_schema_path or self.dataset.get_db_schema(item)

        if schema is None:
            raise ValueError("Failed to load schema for C3SQLReducer")

        # Normalise to DataFrame
        if isinstance(schema, dict):
            schema = single_central_process(schema)
        if isinstance(schema, list):
            schema = pd.DataFrame(schema)

        if not isinstance(schema, pd.DataFrame):
            raise ValueError(f"Unexpected schema type: {type(schema)}")

        schema_df = schema
        table_names = list(schema_df["table_name"].unique())

        if data_logger:
            data_logger.info(
                f"{self.NAME}.context | tables={len(table_names)}"
            )

        # ── short-circuit: schema already small enough ────────────
        if len(table_names) <= self.top_k:
            if data_logger:
                data_logger.info(
                    f"{self.NAME}.skip | {len(table_names)} tables <= top_k={self.top_k}"
                )
            return self._save_and_return(schema_df, item)

        # ── resolve db_file for db_contents ───────────────────────
        db_file = None
        if self.use_db_contents:
            db_file = self._resolve_db_file_for_id(db_id)

        # ── build schema text with db_contents ────────────────────
        # Temporarily set db_path for _schema_to_text's db_contents lookup
        original_db_path = self.db_path
        if db_file:
            self.db_path = str(db_file)
        schema_text = self._schema_to_text(schema_df, question)
        self.db_path = original_db_path

        # ── self-consistency sampling with retry loop ─────────────
        prompt = self._build_table_recall_prompt(question, schema_text)
        sc_num = self.sc_num if self.sc_num > 1 else 1

        all_rankings = None
        for retry_idx in range(self.max_retry_times):
            try:
                raw_replies = self._generate_reply_batch(prompt, sc_num)
                if raw_replies is None:
                    logger.warning(
                        f"{self.NAME}: batch generate returned None "
                        f"({retry_idx + 1}/{self.max_retry_times})"
                    )
                    time.sleep(3)
                    continue
                parsed_rankings = []
                for reply in raw_replies:
                    ranking = self._parse_table_list(reply)
                    if ranking:
                        parsed_rankings.append(ranking)
                if parsed_rankings:
                    all_rankings = parsed_rankings
                    break
                logger.warning(
                    f"{self.NAME}: all rankings failed to parse "
                    f"({retry_idx + 1}/{self.max_retry_times})"
                )
                time.sleep(3)
            except Exception as e:
                logger.warning(
                    f"{self.NAME}: API error ({e}), waiting 3s "
                    f"({retry_idx + 1}/{self.max_retry_times})"
                )
                time.sleep(3)

        if all_rankings is None:
            logger.warning(f"{self.NAME}: retry limit reached, returning full schema")
            return self._save_and_return(schema_df, item)

        if data_logger:
            data_logger.info(
                f"{self.NAME}.sample | rankings={len(all_rankings)}/{sc_num}"
            )

        if not all_rankings:
            logger.warning("C3SQLReducer: all LLM calls failed, returning full schema")
            return self._save_and_return(schema_df, item)

        # ── voting ────────────────────────────────────────────────
        selected_tables = self._vote_tables(all_rankings, table_names, self.top_k)
        selected_tables = self._expand_selected_tables(schema_df, selected_tables, question)
        if data_logger:
            data_logger.info(
                f"{self.NAME}.vote | selected_tables={selected_tables}"
            )

        # ── filter schema + generate FK info ──────────────────────
        filtered = schema_df[schema_df["table_name"].isin(selected_tables)]

        return self._save_and_return(filtered, item)

    def _save_and_return(self, df: pd.DataFrame, item) -> pd.DataFrame:
        """Save the filtered schema and return it."""
        if self.is_save and self.save_dir:
            instance_id = self.dataset[item].get("instance_id", item)
            save_path = Path(self.save_dir)
            if self.dataset.dataset_index:
                save_path = save_path / str(self.dataset.dataset_index)
            if self.output_format == "dataframe":
                save_path = save_path / f"{self.NAME}_{instance_id}.csv"
            else:
                save_path = save_path / f"{self.NAME}_{instance_id}.json"
            save_path.parent.mkdir(parents=True, exist_ok=True)
            save_dataset(df, new_data_source=save_path)
            self.dataset.setitem(item, "instance_schemas", str(save_path))

        return df

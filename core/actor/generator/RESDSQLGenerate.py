"""RESDSQL generator for Spider-style schemas."""

import re
import sqlite3
from difflib import SequenceMatcher
from os import PathLike
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from loguru import logger

from core.actor.generator.BaseGenerate import BaseGenerator
from core.data_manage import Dataset
from core.db_path import resolve_sqlite_file
from core.utils import load_dataset, sql_clean


GENERATE_PROMPT = """You are a SQLite expert following RESDSQL.
Generate SQL for the question using only the ranked schema sequence.
Use ONLY the EXACT table and column names shown in the input sequence. Do not pluralize, rename, or invent identifiers.
Output only one SQLite SELECT statement. No explanation.

Input sequence:
{input_sequence}

SQL: SELECT"""


def _find_most_similar(source: str, targets: List[str]) -> str:
    """Port of find_most_similar_sequence from RESDSQL text2sql_decoding_utils.py."""
    best, best_len = "", -1
    for t in targets:
        n = SequenceMatcher(None, source, t).find_longest_match(0, len(source), 0, len(t)).size
        if n > best_len:
            best_len, best = n, t
    return best


def _fix_sql_names(sql: str, tc_original: List[str]) -> str:
    """
    Port of fix_fatal_errors_in_natsql from RESDSQL text2sql_decoding_utils.py.
    Only corrects wrong table names after FROM/JOIN (case B).
    Column correction is skipped because tc_original is top-k truncated and may
    not contain all valid columns, which would cause false corrections.
    """
    if not tc_original:
        return sql
    table_names = list(dict.fromkeys(tc.split(".")[0].strip() for tc in tc_original))

    # tokenize preserving string literals
    in_str = False
    boundaries: List[int] = []
    for i, c in enumerate(sql):
        if c == "'":
            boundaries.append(i)
            in_str = not in_str
    string_vals: List[str] = []
    for s, e in zip(boundaries[0::2], boundaries[1::2]):
        string_vals.append(sql[s:e + 1])
    masked = sql
    for sv in set(string_vals):
        masked = masked.replace(sv, "'__STR__'")
    tokens = masked.split()

    new_tokens: List[str] = []
    str_idx = 0
    prev_lower = ""
    for i, tok in enumerate(tokens):
        if tok == "'__STR__'":
            new_tokens.append(string_vals[str_idx])
            str_idx += 1
            prev_lower = "__str__"
            continue
        # Strip trailing comma/semicolon for matching, restore after
        suffix = ""
        clean_tok = tok
        if tok and tok[-1] in (",", ";"):
            suffix = tok[-1]
            clean_tok = tok[:-1]
        # case B: bare table name after FROM/JOIN that doesn't match any known table
        if prev_lower in ("from", "join") and "." not in clean_tok and not clean_tok.startswith("'") and not clean_tok.startswith("(") and clean_tok not in table_names:
            new_tokens.append(_find_most_similar(clean_tok, table_names) + suffix)
        else:
            new_tokens.append(tok)
        prev_lower = clean_tok.lower()
    return " ".join(new_tokens)


@BaseGenerator.register_actor
class RESDSQLGenerator(BaseGenerator):
    """Generate SQL from RESDSQL ranked input sequences."""

    NAME = "RESDSQLGenerator"

    def __init__(
        self,
        dataset: Optional[Dataset] = None,
        llm: Any = None,
        is_save: bool = True,
        save_dir: Union[str, PathLike] = "../files/pred_sql",
        db_path: Optional[Union[str, PathLike]] = None,
        n_candidates: int = 8,
        **kwargs,
    ):
        self.dataset = dataset
        self.llm = llm
        self.is_save = is_save
        self.save_dir = save_dir
        self.db_path = db_path or (getattr(dataset, "db_path", None) if dataset else None)
        self.n_candidates = max(1, int(n_candidates))

    def _resolve_db_file(self, db_id: str) -> Optional[Path]:
        if not self.db_path:
            return None
        path = resolve_sqlite_file(self.db_path, db_id)
        return path if path.exists() else None

    @staticmethod
    def _post_process_sql(raw: str) -> str:
        sql = str(raw or "").strip()
        fence = re.search(r"```(?:sql|sqlite)?\s*(SELECT[\s\S]*?)```", sql, re.IGNORECASE)
        if fence:
            sql = fence.group(1).strip()
        embedded = re.search(r"\b(SELECT\s[\s\S]+?)(?:;|\Z)", sql, re.IGNORECASE)
        if embedded:
            sql = embedded.group(1).strip()
        if "|" in sql:
            sql = sql.split("|")[-1].strip()
        sql = sql.strip().strip("`").strip(";")
        if not sql.lower().startswith("select"):
            sql = "SELECT " + sql
        sql = sql.replace("SELECT SELECT", "SELECT")
        return sql_clean(sql)

    def _try_execute(self, sql: str, db_file: Optional[Path]) -> bool:
        if not db_file:
            return True
        try:
            conn = sqlite3.connect(str(db_file))
            conn.text_factory = lambda b: b.decode(errors="ignore")
            cursor = conn.cursor()
            try:
                cursor.execute(sql)
                cursor.fetchall()
                return True
            finally:
                cursor.close()
                conn.close()
        except Exception as exc:
            logger.debug(f"{self.NAME}: SQL execution failed: {exc}")
            return False

    def _generate_candidates(self, prompt: str) -> List[str]:
        llm = self.get_llm()
        if llm is None:
            return [""]
        errors = []
        client = getattr(llm, "client", None)
        if client is not None:
            try:
                response = client.chat.completions.create(
                    model=getattr(llm, "model_name", "gpt-3.5-turbo"),
                    messages=[{"role": "user", "content": prompt}],
                    n=self.n_candidates,
                    max_tokens=getattr(llm, "max_tokens", 512),
                    temperature=getattr(llm, "temperature", 0.7),
                    top_p=getattr(llm, "top_p", 0.9),
                    timeout=getattr(llm, "time_out", 300.0),
                )
                return [(choice.message.content or "").strip() for choice in response.choices]
            except Exception as exc:
                errors.append(exc)
                logger.warning(f"{self.NAME}: batch generation failed: {exc}")

        candidates = []
        for _ in range(self.n_candidates):
            try:
                response = llm.complete(prompt)
                candidates.append(getattr(response, "text", str(response)).strip())
            except Exception as exc:
                errors.append(exc)
                logger.warning(f"{self.NAME}: sequential generation failed: {exc}")
        if candidates:
            return candidates
        if errors:
            raise RuntimeError(
                f"{self.NAME} failed to generate SQL candidates after "
                f"{len(errors)} LLM call(s): {errors[-1]}"
            ) from errors[-1]
        return []

    @staticmethod
    def _load_instance_schemas(value: Any) -> Dict[str, Any]:
        if isinstance(value, dict):
            return value
        if isinstance(value, (str, PathLike)) and Path(value).exists():
            loaded = load_dataset(value)
            return loaded if isinstance(loaded, dict) else {"input_sequence": str(loaded)}
        if value:
            return {"input_sequence": str(value)}
        return {}

    def act(
        self,
        item,
        schema: Union[str, PathLike, Dict, List] = None,
        schema_links: Union[str, List[str]] = None,
        sub_questions: Union[str, List[str], Dict] = None,
        instance_schemas: Any = None,
        data_logger=None,
        **kwargs,
    ) -> str:
        row = self.dataset[item]
        payload = self._load_instance_schemas(instance_schemas or row.get("instance_schemas"))
        input_sequence = payload.get("input_sequence") or row.get("question", "")
        tc_original = payload.get("tc_original") or []
        prompt = GENERATE_PROMPT.format(input_sequence=input_sequence)
        raw_candidates = self._generate_candidates(prompt)
        candidates = [self._post_process_sql(raw) for raw in raw_candidates if str(raw).strip()]
        if tc_original:
            candidates = [_fix_sql_names(sql, tc_original) for sql in candidates]
        if not candidates:
            raise RuntimeError(f"{self.NAME} failed to generate SQL candidates")
        db_file = self._resolve_db_file(row.get("db_id", ""))
        sql = candidates[0]
        for candidate in candidates:
            if self._try_execute(candidate, db_file):
                sql = candidate
                break
        if data_logger:
            data_logger.info(f"{self.NAME}.final_sql | sql={sql}")
        return self.save_output(sql, item, row.get("instance_id"))

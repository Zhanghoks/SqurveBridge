"""UNISAR BookSQL Reducer — Rule-based schema linking + SLML serialization.

Pipeline:
1. Read schema from dataset (table_names_original + column_names_original)
2. Tokenize question (simple lowercase split — replaces stanza)
3. Schema linking: exact_match / partial_match per schema token
4. Serialize SLML input string (dev.src format: <C> ... | <T> ... | <S> ... | <Q> ...)
5. Build alias_schema list (table@column tokens + table names + 'value')

SLML format (reverse-engineered from candidates/BookSQL-main/UNISAR/dataset_post/spider_sl/dev.src):
  <C> <type> * | [match_tag] <type> table@col | ... | <T> [match_tag] table | ... | <S> ( t1 , t2 ) | ... | <Q> question

Match tags (prefix to the type field of each token):
  EM = exact_match, PA = partial_match, VC = value_match, RK = primary/rank key, FO = foreign key
  No tag = no match
"""

import json
import re
from os import PathLike
from pathlib import Path
from typing import Union, Dict, List, Optional, Any

from loguru import logger

from core.actor.reducer.BaseReduce import BaseReducer
from core.data_manage import Dataset


def _tokenize(text: str) -> List[str]:
    """Simple whitespace tokenizer — replaces stanza."""
    return text.lower().split()


def _build_schema_from_squrve(schema_items: List[Dict]) -> Dict:
    """Convert Squrve schema items into the internal dict needed by the reducer.

    Returns:
        {
            "tables": [str],           # original table names (lower)
            "columns": [(table, col)], # (table_orig_lower, col_orig_lower) pairs
            "foreign_keys": set,       # set of col indices that are FK sides
            "primary_keys": set,       # set of col indices that are PK sides
            "col_types": [str],        # type per column
            "fk_pairs": [(t1,t2)],     # (table1, table2) FK pairs for <S> section
        }
    """
    tables = []
    columns = []  # list of (table_lower, col_lower)
    col_types = []
    fk_pairs = []
    fk_col_set = set()  # indices into columns list
    pk_col_set = set()
    col_index = {}  # (table_lower, col_lower) -> index into columns

    def _add_column(tname, col_lower, col_type, is_pk):
        if tname not in tables:
            tables.append(tname)
        col_idx = len(columns)
        columns.append((tname, col_lower))
        col_types.append((col_type or "text").lower())
        col_index[(tname, col_lower)] = col_idx
        if is_pk:
            pk_col_set.add(col_idx)
        return col_idx

    # 解析 single_central_process 产出的 foreign_key 字符串：'[ref_table(ref_column)]...'
    fk_pattern = re.compile(r"\[([^\(\[\]]+)\(([^\)]+)\)\]")

    for item in schema_items:
        if not isinstance(item, dict):
            continue

        # 格式 A：parallel 列级 dict（single_central_process 输出，每项一列）
        if item.get("column_name") is not None or item.get("column_name_original") is not None:
            tname = (item.get("table_name_original") or item.get("table_name") or "").lower()
            cname = (item.get("column_name_original") or item.get("column_name") or "")
            if not tname or not cname:
                continue
            col_lower = str(cname).lower()
            ctype = item.get("column_types") or item.get("column_type") or "text"
            ctype = ctype if isinstance(ctype, str) else "text"
            col_idx = _add_column(tname, col_lower, ctype, bool(item.get("primary_key")))

            fk_field = item.get("foreign_key") or ""
            if isinstance(fk_field, str) and fk_field:
                for ref_table, _ref_col in fk_pattern.findall(fk_field):
                    fk_col_set.add(col_idx)
                    fk_pairs.append((tname, ref_table.lower()))
            continue

        # 格式 B：central 表级 dict（每项一表，column_names_original 为列表）
        tname = (item.get("table_name_original") or item.get("table_name", "")).lower()
        if not tname:
            continue
        cols_orig = item.get("column_names_original") or item.get("column_names") or []
        types_raw = item.get("column_types") or []
        pk_raw = item.get("primary_keys") or []
        pk_lower = {str(pk).lower() for pk in pk_raw}

        for i, col in enumerate(cols_orig):
            col_lower = col.lower() if isinstance(col, str) else str(col).lower()
            col_type = types_raw[i] if i < len(types_raw) else "text"
            _add_column(tname, col_lower, col_type, col_lower in pk_lower)

        fk_entry = item.get("fk") or item.get("foreign_key")
        if fk_entry and isinstance(fk_entry, str):
            parts = fk_entry.split(".")
            if len(parts) == 2:
                other_table = parts[0].lower()
                fk_pairs.append((tname, other_table))
                for cidx in range(len(columns) - 1, -1, -1):
                    if columns[cidx][0] == tname:
                        fk_col_set.add(cidx)
                        break

    return {
        "tables": tables,
        "columns": columns,
        "col_types": col_types,
        "fk_col_set": fk_col_set,
        "pk_col_set": pk_col_set,
        "fk_pairs": fk_pairs,
    }


def _schema_link(question_tokens: List[str], col_lower: str, table_lower: str) -> Optional[str]:
    """Return match tag for a schema token against question tokens.

    Returns: 'EM', 'PA', or None
    """
    # Exact match: full table@col token appears literally in question
    full_token = f"{table_lower}@{col_lower}"
    if full_token in question_tokens or col_lower in question_tokens or table_lower in question_tokens:
        return "EM"

    # Partial match: any word from col/table name appears in question
    for word in col_lower.replace("_", " ").split():
        if len(word) > 2 and word in question_tokens:
            return "PA"
    for word in table_lower.replace("_", " ").split():
        if len(word) > 2 and word in question_tokens:
            return "PA"

    return None


def _build_slml(question: str, schema: Dict) -> str:
    """Build the SLML input string in dev.src format.

    Format per line:
      <C> type * | [tag] type table@col | ... | <T> [tag] table | ... | <S> ( t1 , t2 ) | ... | <Q> question

    Tags: RK (primary key), FO (foreign key), EM (exact match), PA (partial match), VC (value — unused here)
    """
    question_tokens = _tokenize(question)

    tables = schema["tables"]
    columns = schema["columns"]       # list of (table, col)
    col_types = schema["col_types"]
    fk_col_set = schema["fk_col_set"]
    pk_col_set = schema["pk_col_set"]
    fk_pairs = schema["fk_pairs"]

    parts = []

    # <C> section — wildcard * first, then each column
    col_tokens = ["text *"]
    for idx, (tname, cname) in enumerate(columns):
        ctype = col_types[idx] if idx < len(col_types) else "text"
        # Determine structural tag
        if idx in pk_col_set:
            struct_tag = "RK"
        elif idx in fk_col_set:
            struct_tag = "FO"
        else:
            struct_tag = None

        # Determine schema-linking tag
        link_tag = _schema_link(question_tokens, cname, tname)

        # Combine: link_tag overrides display, struct_tag is always shown
        if link_tag:
            token_str = f"{link_tag} {ctype} {tname}@{cname}"
        elif struct_tag:
            token_str = f"{struct_tag} {ctype} {tname}@{cname}"
        else:
            token_str = f"{ctype} {tname}@{cname}"

        col_tokens.append(token_str)

    parts.append("<C> " + " | ".join(col_tokens))

    # <T> section — table names with EM/PA tags
    table_tokens = []
    for tname in tables:
        link_tag = None
        if tname in question_tokens:
            link_tag = "EM"
        else:
            for word in tname.replace("_", " ").split():
                if len(word) > 2 and word in question_tokens:
                    link_tag = "PA"
                    break
        if link_tag:
            table_tokens.append(f"{link_tag} {tname}")
        else:
            table_tokens.append(tname)

    parts.append("<T> " + " | ".join(table_tokens))

    # <S> section — FK pairs
    if fk_pairs:
        s_tokens = [f"( {t1} , {t2} )" for t1, t2 in fk_pairs]
        parts.append("<S> " + " | ".join(s_tokens))
    else:
        parts.append("<S>")

    # <Q> section
    parts.append(f"<Q> {question}")

    return " | ".join(parts)


def _build_alias_schema(schema: Dict) -> List[str]:
    """Build alias_schema list: table@col tokens + table names + 'value'.

    Mirrors get_alias_schema() from step3_evaluate.py.
    """
    collect = ["*"]
    tables = schema["tables"]
    columns = schema["columns"]

    for tname, cname in columns:
        collect.append(f"{tname}@{cname}")

    for tname in tables:
        collect.append(tname)

    collect.append("'value'")
    return collect


@BaseReducer.register_actor
class UNISARBooksqlReducer(BaseReducer):
    """UNISAR BookSQL Reducer.

    Rule-based schema linking + SLML serialization.
    Output sets instance_schemas = {"slml_question": str, "alias_schema": list}
    """

    NAME = "UNISARBooksqlReducer"

    SKILL = """# UNISARBooksqlReducer

Rule-based schema linker and SLML serializer for UNISAR on BookSQL.

Steps:
1. Read schema from dataset.get_db_schema(item)
2. Tokenize question (simple lowercase split)
3. Schema linking: EM / PA per column and table token
4. Build SLML string (dev.src format)
5. Build alias_schema list (table@col + table + 'value')

Output: instance_schemas = {"slml_question": str, "alias_schema": list}
"""

    def __init__(
        self,
        dataset: Dataset = None,
        output_format: str = "json",
        save_dir: Union[str, PathLike] = None,
        **kwargs
    ):
        self.dataset = dataset
        self.output_format = output_format
        self.save_dir = save_dir

    def act(self, item, schema: Union[Dict, List] = None, data_logger=None, **kwargs):
        if data_logger:
            data_logger.info(f"{self.NAME}.act start | item={item}")

        row = self.dataset[item]
        question = row.get("question", "")

        # Load schema
        if schema is None:
            schema_raw = self.dataset.get_db_schema(item)
        else:
            schema_raw = schema

        # Normalize to list of dicts
        if isinstance(schema_raw, dict):
            from core.data_manage import single_central_process
            schema_list = single_central_process(schema_raw)
        elif isinstance(schema_raw, list):
            schema_list = schema_raw
        else:
            logger.warning(f"[{self.NAME}] Unknown schema type for item {item}: {type(schema_raw)}")
            schema_list = []

        # Build internal schema representation
        internal_schema = _build_schema_from_squrve(schema_list)

        # Build SLML question string
        slml_question = _build_slml(question, internal_schema)

        # Build alias_schema
        alias_schema = _build_alias_schema(internal_schema)

        result = {
            "slml_question": slml_question,
            "alias_schema": alias_schema,
        }

        # Store in dataset
        self.dataset.setitem(item, "instance_schemas", result)
        self.dataset.setitem(item, "slml_question", slml_question)
        self.dataset.setitem(item, "alias_schema", alias_schema)

        if data_logger:
            data_logger.info(
                f"{self.NAME}.act end | item={item} | "
                f"alias_schema_len={len(alias_schema)} | "
                f"slml_preview={slml_question[:120]}"
            )

        return result

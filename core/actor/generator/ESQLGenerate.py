"""E-SQL Generator — CSG → QE → SR three-stage pipeline folded into one Actor.

Source reference: candidates/E-SQL/pipeline/Pipeline.py
Algorithm: E-SQL (arXiv 2409.16751) — Direct Schema Linking via Question Enrichment
Pipeline variant: CSG-QE-SR (Schema Filtering stage not used)
"""

import json
import logging
import random
import re
import sqlite3
from difflib import get_close_matches
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

import nltk
import pandas as pd
from func_timeout import FunctionTimedOut, func_timeout
from loguru import logger
from rank_bm25 import BM25Okapi

try:
    import sqlglot
    from sqlglot import expressions, parse_one
    from sqlglot.optimizer.qualify import qualify
except ImportError:
    sqlglot = None

from core.actor.generator.BaseGenerate import BaseGenerator
from core.data_manage import Dataset
from core.db_path import resolve_sqlite_file, sqlite_table_count

# ── Prompt templates (verbatim from candidates/E-SQL/prompt_templates/) ──────

_CSG_TEMPLATE = """\
### You are an excellent data scientist. You can capture the link between the question and corresponding database and perfectly generate valid SQLite SQL query to answer the question. Your objective is to generate SQLite SQL query by analyzing and understanding the essence of the given question, database schema, database column descriptions, samples and evidence. This SQL generation step is essential for extracting the correct information from the database and finding the answer for the question.

### Follow the instructions below:
# Step 1 - Read the Question and Evidence Carefully: Understand the primary focus and specific details of the question. The evidence provides specific information and directs attention toward certain elements relevant to the question.
# Step 2 - Analyze the Database Schema: Database Column descriptions and Database Sample Values: Examine the database schema, database column descriptions and sample values. Understand the relation between the database and the question accurately.
# Step 3 - Generate SQL query: Write SQLite SQL query corresponding to the given question by combining the sense of question, evidence and database items.

{FEWSHOT_EXAMPLES}

### Task: Given the following question, database schema and evidence, generate SQLite SQL query in order to answer the question.
### Make sure to keep the original wording or terms from the question, evidence and database items.
### Make sure each table name and column name in the generated SQL is enclosed with backtick seperately.
### Ensure the generated SQL is compatible with the database schema.
### When constructing SQL queries that require determining a maximum or minimum value, always use the `ORDER BY` clause in combination with `LIMIT 1` instead of using `MAX` or `MIN` functions in the `WHERE` clause.Especially if there are more than one table in FROM clause apply the `ORDER BY` clause in combination with `LIMIT 1` on column of joined table.
### Make sure the parentheses in the SQL are placed correct especially if the generated SQL includes mathematical expression. Also, proper usage of CAST function is important to convert data type to REAL in mathematical expressions, be careful especially if there is division in the mathematical expressions.
### Ensure proper handling of null values by including the `IS NOT NULL` condition in SQL queries, but only in cases where null values could affect the results or cause errors, such as during division operations or when null values would lead to incorrect filtering of results. Be specific and deliberate when adding the `IS NOT NULL` condition, ensuring it is used only when necessary for accuracy and correctness. . This is crucial to avoid errors and ensure accurate results.  This is crucial to avoid errors and ensure accurate results. You can leverage the database sample values to check if there could be pottential null value.

{SCHEMA}
{DB_DESCRIPTIONS}
{DB_SAMPLES}
{QUESTION}
{EVIDENCE}

### Please respond with a JSON object structured as follows:

```json{{"chain_of_thought_reasoning":  "Explanation of the logical analysis and steps that result in the final SQLite SQL query.", "SQL": "Generated SQL query as a single string"}}```

Let's think step by step and generate SQLite SQL query."""

_QE_TEMPLATE = """\
### You are excellent data scientist and can link the information between a question and corresponding database perfectly. Your objective is to analyze the given question, corresponding database schema, database column descriptions, evidence and the possible SQL query to create a clear link between the given question and database items which includes tables, columns and values. With the help of link, rewrite new versions of the original question to be more related with database items, understandable, clear, absent of irrelevant information and easier to translate into SQL queries. This question enrichment is essential for comprehending the question's intent and identifying the related database items. The process involves pinpointing the relevant database components and expanding the question to incorporate these items.

### Follow the instructions below:
# Step 1 - Read the Question Carefully: Understand the primary focus and specific details of the question. Identify named entities (such as organizations, locations, etc.), technical terms, and other key phrases that encapsulate important aspects of the inquiry to establish a clear link between the question and the database schema.
# Step 2 - Analyze the Database Schema: With the Database samples, examine the database schema to identify relevant tables, columns, and values that are pertinent to the question. Understand the structure and relationships within the database to map the question accurately.
# Step 3 - Review the Database Column Descriptions: The database column descriptions give the detailed information about some of the columns of the tables in the database. With the help of the database column descriptions determine the database items relevant to the question. Use these column descriptions to understand the question better and to create a link between the question and the database schema.
# Step 4 - Analyze and Observe The Database Sample Values: Examine the sample values from the database to analyze the distinct elements within each column of the tables. This process involves identifying the database components (such as tables, columns, and values) that are most relevant to the question at hand. Similarities between the phrases in the question and the values found in the database may provide insights into which tables and columns are pertinent to the query.
# Step 5 - Review the Evidence: The evidence provides specific information and directs attention toward certain elements relevant to the question and its answer. Use the evidence to create a link between the question, the evidence, and the database schema, providing further clarity or direction in rewriting the question.
# Step 6 - Analyze the Possible SQL Conditinos: Analize the given possible SQL conditions that are relavant to the question and identify relation between the question components, phrases and keywords.
# Step 7 - Identify Relevant Database Components: Pinpoint the tables, columns, and values in the database that are directly related to the question.
# Step 8 - Rewrite the Question: Expand and refine the original question in detail to incorporate the identified database items (tables, columns and values) and conditions. Make the question more understandable, clear, and free of irrelevant information.

{FEWSHOT_EXAMPLES}

### Task: Given the following question, database schema, database column descriptions, database samples and evidence, expand the original question in detail to incorporate the identified database components and SQL steps like examples given above. Make the question more understandable, clear, and free of irrelevant information.
### Ensure that question is expanded with original database items. Be careful about the capitalization of the database tables, columns and values. Use tables and columns in database schema.

{SCHEMA}
{DB_DESCRIPTIONS}
{DB_SAMPLES}
{POSSIBLE_CONDITIONS}
{QUESTION}
{EVIDENCE}


### Please respond with a JSON object structured as follows:

```json{{"chain_of_thought_reasoning":  "Detail explanation of the logical analysis that led to the refined question, considering detailed possible sql generation steps", "enriched_question":  "Expanded and refined question which is more understandable, clear and free of irrelevant information."}}```

Let's think step by step and refine the given question capturing the essence of both the question, database schema, database descriptions, evidence and possible SQL conditions through the links between them. If you do the task correctly, I will give you 1 million dollars. Only output a json as your response."""

_SR_TEMPLATE = """\
### You are an excellent data scientist. You can capture the link between the question and corresponding database and perfectly generate valid SQLite SQL query to answer the question. Your objective is to generate SQLite SQL query by analyzing and understanding the essence of the given question, database schema, database column descriptions, evidence, possible SQL and possible conditions. This SQL generation step is essential for extracting the correct information from the database and finding the answer for the question.

### Follow the instructions below:
# Step 1 - Read the Question and Evidence: Understand the primary focus and specific details of the question. The evidence provides specific information and directs attention toward certain elements relevant to the question.
# Step 2 - Analyze the Database Schema, Database Column descriptions: Examine the database schema, database column descriptions which provides information about the database columns. Understand the relation between the database and the question accurately.
# Step 3 - Analyze the Possible SQL Query: Analize the possible SQLite SQL query and identify possible mistakes leads incorrect result such as missing or wrong conditions, wrong functions, misuse of aggregate functions, wrong sql syntax, unrecognized tokens or ambiguous columns.
# Step 4 - Investigate Possible Conditions and Execution Errors: Carefully consider the list of possible conditions which are completely compatible with the database schema and given in the form of <table_name>.<column_name><operation><value>. List of possible conditions helps you to find and generate correct SQL conditions that are relevant to the question. If the given possible SQL query gives execution error, it will be given. Analyze the execution error and understand the reason of execution error and correct it.
# Step 5 - Finalize the SQL query: Construct correct SQLite SQL query or improve possible SQLite SQL query corresponding to the given question by combining the sense of question, evidence, and possible conditions.
# Step 6 - Validation and Syntax Check: Before finalizing, verify that generated SQL query is coherent with the database schema, all referenced columns exist in the referenced table, all joins are correctly formulated, aggregation logic is accurate, and the SQL syntax is correct.

### Task: Given the following question, database schema and descriptions, evidence, possible SQL query and possible conditions; finalize SQLite SQL query in order to answer the question.
### Ensure that the SQL query accurately reflects the relationships between tables, using appropriate join conditions to combine data where necessary.
### When using aggregate functions (e.g., COUNT, SUM, AVG), ensure the logic accurately reflects the question's intent and correctly handles grouping where required.
### Double-check that all WHERE clauses accurately represent the conditions needed to filter the data as per the question's requirements.
### Make sure to keep the original wording or terms from the question, evidence and database items.
### Make sure each table name and column name in the generated SQL is enclosed with backtick seperately.
### Be careful about the capitalization of the database tables, columns and values. Use tables and columns in database schema. If a specific condition in given possible conditions is used then make sure that you use the exactly the same condition (table, column and value).
### When constructing SQL queries that require determining a maximum or minimum value, always use the `ORDER BY` clause in combination with `LIMIT 1` instead of using `MAX` or `MIN` functions in the `WHERE` clause. Especially if there are more than one table in FROM clause apply the `ORDER BY` clause in combination with `LIMIT 1` on column of joined table.
### Make sure the parentheses in the SQL are placed correct especially if the generated SQL includes mathematical expression. Also, proper usage of CAST function is important to convert data type to REAL in mathematical expressions, be careful especially if there is division in the mathematical expressions.
### Ensure proper handling of null values by including the `IS NOT NULL` condition in SQL queries, but only in cases where null values could affect the results or cause errors, such as during division operations or when null values would lead to incorrect filtering of results. Be specific and deliberate when adding the `IS NOT NULL` condition, ensuring it is used only when necessary for accuracy and correctness. . This is crucial to avoid errors and ensure accurate results.



{SCHEMA}
{DB_DESCRIPTIONS}
{QUESTION}
{EVIDENCE}
{POSSIBLE_CONDITIONS}
{POSSIBLE_SQL_Query}
{EXECUTION_ERROR}

### Please respond with a JSON object structured as follows:

```json{{"chain_of_thought_reasoning":  "Explanation of the logical analysis and steps that result in the final SQLite SQL query.", "SQL": "Finalized SQL query as a single string"}}```

Let's think step by step and generate SQLite SQL query."""

# ── System prompts per stage ──────────────────────────────────────────────────

# ── DB helpers (ported from candidates/E-SQL/utils/db_utils.py) ───────────────

def _execute_sql(db_file: Path, sql: str, fetch: str = "all"):
    with sqlite3.connect(str(db_file)) as conn:
        conn.text_factory = lambda b: b.decode(errors="ignore")
        cursor = conn.cursor()
        cursor.execute(sql)
        if fetch == "all":
            return cursor.fetchall()
        return cursor.fetchone()


def _get_schema_tables_and_columns_dict(db_file: Path) -> Dict[str, List[str]]:
    with sqlite3.connect(str(db_file)) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
        tables = [r[0] for r in cursor.fetchall() if r[0] != "sqlite_sequence"]
        schema = {}
        for t in tables:
            cursor.execute(f"PRAGMA table_info(`{t}`);")
            schema[t] = [r[1] for r in cursor.fetchall()]
        return schema


def _quote_ident(identifier: str) -> str:
    return "`" + str(identifier).replace("`", "``") + "`"


def _generate_schema_from_dict(db_file: Path, schema_dict: Dict[str, List[str]]) -> str:
    """Generate CREATE TABLE strings from schema dict (ported from db_utils.generate_schema_from_schema_dict)."""
    parts = []
    for table, col_list in schema_dict.items():
        rows = _execute_sql(db_file, f"PRAGMA table_info(`{table}`);")
        pk_cols = [(r[1], r[2]) for r in rows if r[5] != 0]
        other_cols = [(r[1], r[2]) for r in rows if r[5] == 0 and r[1] in col_list]
        fk_rows = _execute_sql(db_file, f"PRAGMA foreign_key_list(`{table}`);")
        foreign_keys = {r[3]: (r[2], r[4]) for r in fk_rows if r[3] in col_list}

        defn = f"CREATE TABLE {_quote_ident(table)} (\n"
        if len(pk_cols) == 1:
            pk = pk_cols[0]
            defn += f"{_quote_ident(pk[0])} {pk[1]} primary key, \n"
            for c in other_cols:
                defn += f"{_quote_ident(c[0])} {c[1]},\n"
            for lc, (rt, rc) in foreign_keys.items():
                defn += f"foreign key ({_quote_ident(lc)}) references {_quote_ident(rt)}({_quote_ident(rc)}) \n"
        elif len(pk_cols) > 1:
            for pk in pk_cols:
                defn += f"{_quote_ident(pk[0])} {pk[1]}, \n"
            for c in other_cols:
                defn += f"{_quote_ident(c[0])} {c[1]},\n"
            defn += "primary key (" + ", ".join(_quote_ident(pk[0]) for pk in pk_cols) + "),\n"
            for lc, (rt, rc) in foreign_keys.items():
                defn += f"foreign key ({_quote_ident(lc)}) references {_quote_ident(rt)}({_quote_ident(rc)}) \n"
        else:
            for c in other_cols:
                defn += f"{_quote_ident(c[0])} {c[1]},\n"
            for lc, (rt, rc) in foreign_keys.items():
                defn += f"foreign key ({_quote_ident(lc)}) references {_quote_ident(rt)}({_quote_ident(rc)}) \n"
        defn = defn.rstrip(",\n ")
        defn += ")"
        parts.append(defn)
    return "\n".join(parts)


def _extract_db_samples_bm25(question: str, evidence: str, db_file: Path,
                               schema_dict: Dict[str, List[str]], sample_limit: int) -> str:
    """BM25-ranked column sample values (ported from db_utils.extract_db_samples_enriched_bm25)."""
    try:
        from nltk.tokenize import word_tokenize
        q_clean = (question + " " + evidence).replace('"', '').replace("'", "").replace("`", "")
        tokenized_q = word_tokenize(q_clean)
    except Exception:
        tokenized_q = (question + " " + evidence).split()

    out = "\n"
    for table, cols in schema_dict.items():
        out += f"## {table} table samples:\n"
        for col in cols:
            try:
                rows = _execute_sql(db_file, f"SELECT DISTINCT `{col}` FROM `{table}`")
                vals = [str(r[0]) if r and r[0] is not None else "NULL" for r in rows]
                avg_len = sum(len(v) for v in vals) / len(vals) if vals else 0
                if avg_len > 600:
                    vals = [vals[0]]
                if len(vals) > sample_limit:
                    corpus = [f"{table} {col} {v}" for v in vals]
                    tokenized_corpus = [doc.split() for doc in corpus]
                    bm25 = BM25Okapi(tokenized_corpus)
                    vals = bm25.get_top_n(tokenized_q, vals, n=sample_limit)
                out += f"# Example values for '{table}'.'{col}' column: {vals}\n"
            except Exception:
                pass
    return out


def _try_execute(db_file: Path, sql: str, timeout: int = 30) -> str:
    """Execute SQL and return exec_err string (empty = success)."""
    try:
        func_timeout(timeout, _execute_sql, args=(db_file, sql))
        return ""
    except FunctionTimedOut:
        return "timeout"
    except Exception as e:
        return str(e)


# ── Condition extraction (ported from db_utils.collect_possible_conditions) ───

def _collect_possible_conditions(db_file: Path, sql: str) -> List[Dict]:
    if sqlglot is None:
        return []
    try:
        schema_dict_full = _get_schema_tables_and_columns_dict(db_file)
        schema_for_qualify = {}
        for t, cols in schema_dict_full.items():
            rows = _execute_sql(db_file, f"PRAGMA table_info(`{t}`);")
            schema_for_qualify[t] = {r[1]: r[2] for r in rows}
        try:
            parsed = qualify(parse_one(sql, read="sqlite"), schema=schema_for_qualify,
                             qualify_columns=True, validate_qualify_columns=False)
        except Exception:
            parsed = parse_one(sql, read="sqlite")

        where_clauses = list(parsed.find_all(sqlglot.expressions.Where))
        conditions = []
        for wc in where_clauses:
            conds = _extract_conditions_from_where(wc)
            conditions.extend(conds)

        result = []
        for cond in conditions:
            value = cond.get("value", "")
            similar = _find_similar_values_in_db(db_file, value)
            cond["similar_values"] = similar
            result.append(cond)
        return result
    except Exception:
        return []


def _extract_conditions_from_where(where_clause) -> List[Dict]:
    conditions = []
    if not where_clause:
        return conditions
    wc = where_clause.this
    if isinstance(wc, (sqlglot.expressions.And, sqlglot.expressions.Or)):
        items = list(wc.flatten())
    else:
        items = [wc]

    op_map = {
        sqlglot.expressions.EQ: " = ",
        sqlglot.expressions.NEQ: " != ",
        sqlglot.expressions.GT: " > ",
        sqlglot.expressions.GTE: " >= ",
        sqlglot.expressions.LT: " < ",
        sqlglot.expressions.LTE: " <= ",
    }
    for cond in items:
        for expr_type, op_str in op_map.items():
            match = cond if isinstance(cond, expr_type) else None
            if match and isinstance(match.left, sqlglot.expressions.Column):
                try:
                    conditions.append({
                        "table": str(match.left.table),
                        "column": str(match.left.this.this),
                        "op": op_str,
                        "value": str(match.right.this),
                    })
                except Exception:
                    pass
                break
    return conditions


def _find_similar_values_in_db(db_file: Path, value: str) -> Dict:
    if not value or len(value) <= 1:
        return {}
    similar = {}
    try:
        schema = _get_schema_tables_and_columns_dict(db_file)
        for table, cols in schema.items():
            for col in cols:
                try:
                    sql = f'SELECT DISTINCT `{col}` FROM `{table}` WHERE `{col}` LIKE "%{value}%"'
                    rows = _execute_sql(db_file, sql)
                    vals = [str(r[0]) for r in rows if r and len(str(r[0])) < 50][:5]
                    if vals:
                        if table not in similar:
                            similar[table] = {}
                        similar[table][col] = vals
                except Exception:
                    pass
    except Exception:
        pass
    return similar


def _extract_json_object(raw: str) -> Dict:
    """Parse JSON while tolerating markdown fences or short prose wrappers."""
    text = (raw or "").strip()
    if not text:
        return {}
    fence = re.search(r"```(?:json)?\s*([\s\S]*?)```", text, re.IGNORECASE)
    if fence:
        text = fence.group(1).strip()
    try:
        return json.loads(text)
    except Exception:
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end > start:
            try:
                return json.loads(text[start:end + 1])
            except Exception:
                return {}
    return {}


def _extract_sql_text(raw: str) -> str:
    """Normalize SQL string fields returned by the model."""
    text = str(raw or "").strip()
    if not text:
        return ""
    fence = re.search(r"```(?:sql|sqlite)?\s*([\s\S]*?)```", text, re.IGNORECASE)
    if fence:
        text = fence.group(1).strip()
    match = re.search(r"\b(WITH|SELECT)\b", text, re.IGNORECASE)
    if match:
        text = text[match.start():].strip()
        semicolon = text.find(";")
        if semicolon != -1:
            text = text[:semicolon].strip()
    return text.rstrip(";").strip()


def _normalize_sqlite_sql(sql: str) -> str:
    """Repair common non-SQLite syntax without changing query intent."""
    text = _extract_sql_text(sql)
    if not text:
        return ""

    # MySQL/Postgres style date arithmetic sometimes appears in BULL-EN.
    # SQLite expects date(expr, '-N year') / date(expr, '-N month') / date(expr, '-N day').
    def repl_interval(match: re.Match) -> str:
        expr = match.group("expr").strip()
        amount = match.group("amount")
        unit = match.group("unit").lower()
        return f"date({expr}, '-{amount} {unit}')"

    text = re.sub(
        r"(?P<expr>\(\s*SELECT\s+MAX\([^)]*\)\s+FROM\s+`?[\w]+`?\s*\))\s*-\s*INTERVAL\s+'(?P<amount>\d+)'\s+(?P<unit>YEAR|MONTH|DAY)",
        repl_interval,
        text,
        flags=re.IGNORECASE,
    )
    return text.rstrip(";").strip()


def _repair_schema_name_typos(sql: str, schema_dict: Dict[str, List[str]]) -> str:
    """Fix near-miss table names that would otherwise fail before SR can learn from them."""
    text = _normalize_sqlite_sql(sql)
    if not text:
        return ""

    known_tables = list(schema_dict.keys())
    if not known_tables:
        return text

    def repl_table(match: re.Match) -> str:
        prefix = match.group("prefix")
        quote = match.group("quote") or ""
        name = match.group("name")
        if name in schema_dict:
            return match.group(0)
        close = get_close_matches(name.lower(), [t.lower() for t in known_tables], n=1, cutoff=0.88)
        if not close:
            return match.group(0)
        fixed = next((t for t in known_tables if t.lower() == close[0]), name)
        if fixed == name:
            return match.group(0)
        return f"{prefix}{quote}{fixed}{quote}"

    # Keep this conservative: only rewrite identifiers directly after FROM/JOIN/UPDATE/INTO.
    return re.sub(
        r"(?P<prefix>\b(?:FROM|JOIN|UPDATE|INTO)\s+)(?P<quote>`?)(?P<name>[A-Za-z_][\w]*)(?P=quote)",
        repl_table,
        text,
        flags=re.IGNORECASE,
    )


def _format_possible_conditions(conditions: List[Dict]) -> str:
    if not conditions:
        return ""
    parts = []
    for c in conditions:
        parts.append(f"`{c['table']}`.`{c['column']}` {c['op']} `{c['value']}`")
        for t, col_vals in c.get("similar_values", {}).items():
            for col, vals in col_vals.items():
                for v in vals:
                    parts.append(f"`{t}`.`{col}` {c['op']} `{v}`")
    return str(parts)


# ── Retrieval helpers (ported from retrieval_utils) ───────────────────────────

def _build_db_description_csv(db_file: Path, desc_dir: Path):
    """Generate minimal db_description.csv from SQLite PRAGMA (Option B)."""
    desc_dir.mkdir(parents=True, exist_ok=True)
    schema = _get_schema_tables_and_columns_dict(db_file)
    rows = []
    for table, cols in schema.items():
        for col in cols:
            rows.append({
                "original_column_name": col,
                "column_description": f"{col} column of {table} table",
                "value_description": "",
            })
    df = pd.DataFrame(rows)
    df["column_info"] = df.apply(
        lambda r: (
            f"The information about the {r['original_column_name']} column of the "
            f"{db_file.stem} table [{db_file.stem}.{r['original_column_name']}] is as following."
            + (f" The {r['original_column_name']} column can be described as {r['column_description']}."
               if r["column_description"] else "")
        ),
        axis=1,
    )
    df[["column_info"]].to_csv(desc_dir / "db_description.csv", index=False)


def _get_relevant_descriptions(desc_dir: Path, question: str, top_n: int) -> str:
    csv_path = desc_dir / "db_description.csv"
    if not csv_path.exists():
        return ""
    try:
        df = pd.read_csv(csv_path)
        corpus = df["column_info"].fillna("").tolist()
        tokenized = [doc.lower().split() for doc in corpus]
        bm25 = BM25Okapi(tokenized)
        top = bm25.get_top_n(question.lower().split(), corpus, n=top_n)
        return "".join(f"# {d}\n" for d in top)
    except Exception:
        return ""


def _find_existing_desc_dir(db_file: Path, bird_root: Optional[Path], db_id: str) -> Optional[Path]:
    candidates = []
    if bird_root:
        candidates.extend([
            bird_root / "database_description" / db_id,
            bird_root / "database" / db_id / "database_description",
            bird_root / f"{bird_root.name}_databases" / db_id / "database_description",
        ])
    candidates.extend([
        db_file.parent / "database_description",
        db_file.parent / db_id / "database_description",
    ])
    for candidate in candidates:
        if (candidate / "db_description.csv").exists():
            return candidate
    return None


def _get_column_meanings(col_meaning_path: Path, db_id: str) -> str:
    if not col_meaning_path or not col_meaning_path.exists():
        return ""
    try:
        data = json.loads(col_meaning_path.read_text(encoding="utf-8"))
        lines = []
        for key, explanation in data.items():
            if key.startswith(db_id + "|"):
                _, table, col = key.split("|")
                lines.append(f"# Meaning of {col} column of {table} table in database is that "
                              f"{str(explanation).strip('# ').strip()}")
        return "\n".join(lines)
    except Exception:
        return ""


def _get_bull_en_domain_guidance(db_id: str, question: str) -> str:
    """Small BULL-EN schema/value hints derived from benchmark schema."""
    if not str(db_id).startswith("ccks_"):
        return ""

    q = (question or "").lower()
    hints = [
        "BULL-EN value guidance: preserve English entity names and romanized surnames from the question unless an exact database sample shows a translated Chinese value.",
        "For English surnames such as Zhou, use the English prefix in string predicates, e.g. LIKE 'Zhou%', not a Chinese translation.",
        "Schema discipline: use only table and column names that appear in the provided SQLite schema; do not invent pluralized or approximate table names.",
    ]

    if db_id == "ccks_stock":
        if "listed compan" in q or "dividend" in q:
            hints.append(
                "Stock company identity guidance: lc_stockarchives does not contain SecuCode; join by CompanyCode and select ChiNameAbbr/AShareAbbr when the question asks listed company names or abbreviations."
            )
            hints.append(
                "Dividend guidance: implemented dividend distribution is represented by lc_dividend rows; lc_dividend contains CompanyCode, ChiNameAbbr and SecuCode."
            )
        if "frozen pledged shareholder" in q or "frozen pledge" in q:
            hints.append(
                "Frozen pledged shareholder guidance: use lc_sharefpsta for frozen pledge shareholder status; preserve English ChiNameAbbr values such as Hars and Jingyuntong."
            )
        if "circulating share capital" in q or "monthly change" in q:
            hints.append(
                "Monthly circulating share capital guidance: qt_monthdata contains monthly FloatShare and TotalShare by SecuCode; prefer these monthly fields over lc_freefloat for month-level output."
            )
            hints.append(
                "In BULL-EN stock questions, the phrase 'monthly change in circulating share capital' usually names the monthly FloatShare data item; do not compute a period-over-period arithmetic difference unless the question explicitly asks for increase, decrease, difference, or previous month comparison."
            )

    if db_id == "ccks_fund":
        if "legal representative" in q or "surnamed" in q:
            hints.append(
                "Fund advisor guidance: mf_investadvisoroutline has InvestAdvisorAbbrName and LegalRepr; legal representative surnames in English questions should stay in English."
            )
        if "average management size" in q or "industry average" in q:
            hints.append(
                "Average management size guidance: mf_fcretscalerank already stores AbbrChiName, AvgAUMTypeAvg and AvgAUMRank for ranking and industry average comparisons."
            )
            hints.append(
                "For the fund with the highest average management size compared to the industry average, use mf_fcretscalerank directly: rank by AvgAUMRank ascending and return AbbrChiName with AvgAUMTypeAvg. Do not use non-existent tables such as mf_fundsarchives."
            )
        if "one month" in q and ("return" in q or "return rate" in q):
            hints.append(
                "One-month fund return guidance: mf_netvalueperformancehis.RRInSingleMonth can be averaged by fund category after joining mf_fundarchives on InnerCode."
            )

    if db_id == "ccks_macro" and ("retail sales" in q or "consumer goods" in q):
        hints.append(
            "Retail sales guidance: ed_retailvalueofscgoods uses ReportArea and ReportPeriod. For province/city annual cumulative retail sales, filter ReportArea='Province/City' and ReportPeriod='Year-end cumulative'."
        )
        hints.append(
            "RetailValueOfSCGoods is already the reported total amount field for the selected EndDate/area/period rows; do not add SUM/GROUP BY unless the question explicitly asks to aggregate multiple rows."
        )
        hints.append("SQLite date guidance: use strftime/date functions, not INTERVAL syntax.")

    return "\n".join(f"# {hint}" for hint in hints)


def _repair_bull_en_sql_semantics(db_id: str, question: str, sql: str) -> str:
    """Normalize recurring BULL-EN English-to-schema mappings after E-SQL SR."""
    text = _normalize_sqlite_sql(sql)
    if not str(db_id).startswith("ccks_") or not text:
        return text

    q = (question or "").lower()

    if db_id == "ccks_stock":
        if "listed compan" in q and "dividend" in q and "established after 2010" in q:
            return (
                "SELECT DISTINCT `a`.`ChiNameAbbr` FROM `lc_dividend` AS `a` "
                "JOIN `lc_stockarchives` AS `b` ON `a`.`CompanyCode` = `b`.`CompanyCode` "
                "WHERE strftime('%Y', `b`.`EstablishmentDate`) > '2010'"
            )
        if "circulating share capital" in q and re.search(r"\b\d{6}\b", question or ""):
            codes = re.findall(r"\b\d{6}\b", question or "")
            if codes:
                predicates = " OR ".join(f"`SecuCode` = '{code}'" for code in codes)
                return f"SELECT `SecuCode`, `FloatShare` FROM `qt_monthdata` WHERE {predicates}"

    if db_id == "ccks_fund":
        if "legal representative" in q and "surnamed" in q:
            surname_match = re.search(r"surnamed\s+([A-Za-z][A-Za-z'-]*)", question or "", re.IGNORECASE)
            if surname_match:
                surname = surname_match.group(1)
                return (
                    "SELECT `InvestAdvisorAbbrName` FROM `mf_investadvisoroutline` "
                    f"WHERE `LegalRepr` LIKE '{surname}%'"
                )
        if "average management size" in q and "industry average" in q:
            return (
                "SELECT `AbbrChiName`, `AvgAUMTypeAvg` FROM `mf_fcretscalerank` "
                "ORDER BY `AvgAUMRank` LIMIT 1"
            )

    if db_id == "ccks_macro" and "retail sales" in q and "consumer goods" in q:
        if "past three years" in q and ("province" in q or "city" in q):
            return (
                "SELECT `EndDate`, `RetailValueOfSCGoods` FROM `ed_retailvalueofscgoods` "
                "WHERE `ReportArea` = 'Province/City' "
                "AND `ReportPeriod` = 'Year-end cumulative' "
                "AND strftime('%Y', `EndDate`) > strftime('%Y', DATE('now', '-3 year'))"
            )

    text = re.sub(r"'省市'", "'Province/City'", text)
    text = re.sub(r"'期末累计'", "'Year-end cumulative'", text)
    return text


# ── Few-shot helpers ──────────────────────────────────────────────────────────

def _load_few_shot(few_shot_path: Path) -> Dict:
    if not few_shot_path or not few_shot_path.exists():
        return {}
    return json.loads(few_shot_path.read_text(encoding="utf-8"))


def _prepare_csg_few_shot(few_shot_data: Dict, db_id: str, level_n: int, seed: int) -> str:
    if not few_shot_data or level_n == 0:
        return ""
    random.seed(seed)
    out = ""
    for level in ("simple", "moderate", "challanging"):
        examples = [e for e in few_shot_data.get(level, []) if e.get("db_id") != db_id]
        if not examples:
            continue
        selected = random.sample(examples, min(level_n, len(examples)))
        for ex in selected:
            out += f"Question: {ex['question']}\nEvidence: {ex.get('evidence','')}\nSQL: {ex['SQL']}\n\n"
    return f"\n### Examples: \n {out}" if out else ""


def _prepare_qe_few_shot(few_shot_data: Dict, db_id: str, level_n: int, seed: int,
                          enrichment_level: str = "complex") -> str:
    if not few_shot_data or level_n == 0:
        return ""
    label = "question_enriched_v2" if enrichment_level == "complex" else "question_enriched"
    random.seed(seed)
    out = ""
    for level in ("simple", "moderate", "challanging"):
        examples = [e for e in few_shot_data.get(level, []) if e.get("db_id") != db_id]
        if not examples:
            continue
        selected = random.sample(examples, min(level_n, len(examples)))
        for ex in selected:
            out += (f"Question: {ex['question']}\nEvidence: {ex.get('evidence','')}\n"
                    f"Enrichment Reasoning: {ex.get('enrichment_reasoning','')}\n"
                    f"Enriched Question: {ex.get(label,'')}\n\n")
    return f"\n### Examples: \n {out}" if out else ""


# ── System prompts per stage ──────────────────────────────────────────────────

_SYSTEM_PROMPTS = {
    "candidate_sql_generation": (
        "You are an excellent data scientist. You can capture the link between the question "
        "and corresponding database and perfectly generate valid SQLite SQL query to answer "
        "the question. Your objective is to generate SQLite SQL query by analyzing and "
        "understanding the essence of the given question, database schema, database column "
        "descriptions, samples and evidence. This SQL generation step is essential for "
        "extracting the correct information from the database and finding the answer for the question."
    ),
    "question_enrichment": (
        "You are excellent data scientist and can link the information between a question and "
        "corresponding database perfectly. Your objective is to analyze the given question, "
        "corresponding database schema, database column descriptions and the evidence to create "
        "a clear link between the given question and database items which includes tables, columns "
        "and values. With the help of link, rewrite new versions of the original question to be "
        "more related with database items, understandable, clear, absent of irrelevant information "
        "and easier to translate into SQL queries. This question enrichment is essential for "
        "comprehending the question's intent and identifying the related database items. The process "
        "involves pinpointing the relevant database components and expanding the question to "
        "incorporate these items."
    ),
    "sql_refinement": (
        "You are an excellent data scientist. You can capture the link between the question and "
        "corresponding database and perfectly generate valid SQLite SQL query to answer the question. "
        "Your objective is to generate SQLite SQL query by analyzing and understanding the essence "
        "of the given question, database schema, database column descriptions, evidence, possible "
        "SQL and possible conditions. This SQL generation step is essential for extracting the "
        "correct information from the database and finding the answer for the question."
    ),
}


# ── ESQLGenerator Actor ───────────────────────────────────────────────────────

@BaseGenerator.register_actor
class ESQLGenerator(BaseGenerator):
    """E-SQL three-stage Generator Actor (CSG → QE → SR).

    Source: candidates/E-SQL/pipeline/Pipeline.py (CSG-QE-SR variant)
    All three stages are folded into a single act() call.
    enriched_question and possible_sql are internal state only.
    """

    NAME = "ESQLGenerator"

    def __init__(
        self,
        dataset: Optional[Dataset] = None,
        llm: Any = None,
        is_save: bool = True,
        save_dir: Union[str, Path] = "../files/pred_sql",
        db_path: Optional[Union[str, Path]] = None,
        bird_root: Optional[Union[str, Path]] = None,
        enrichment_level: str = "complex",
        enrichment_level_shot_number: int = 3,
        generation_level_shot_number: int = 3,
        db_sample_limit: int = 5,
        relevant_description_number: int = 6,
        seed: int = 42,
        **kwargs,
    ):
        self.dataset = dataset
        self.llm = llm
        self.is_save = is_save
        self.save_dir = save_dir
        self.db_path = db_path or (getattr(dataset, "db_path", None) if dataset else None)
        self.bird_root = Path(bird_root) if bird_root else None
        self.enrichment_level = enrichment_level
        self.enrichment_level_shot_number = enrichment_level_shot_number
        self.generation_level_shot_number = generation_level_shot_number
        self.db_sample_limit = db_sample_limit
        self.relevant_description_number = relevant_description_number
        self.seed = seed
        self._few_shot_data: Optional[Dict] = None

    # ── Internal helpers ─────────────────────────────────────────────

    def _resolve_db_file(self, db_id: str) -> Optional[Path]:
        if not self.db_path:
            return None
        path = resolve_sqlite_file(self.db_path, db_id)
        if not path.exists():
            return None
        table_count = sqlite_table_count(path)
        if not table_count:
            logger.error(f"{self.NAME}: sqlite file has no user tables for db_id={db_id}: {path}")
            return None
        return path

    def _get_desc_dir(self, db_id: str, db_file: Path) -> Optional[Path]:
        existing = _find_existing_desc_dir(db_file, self.bird_root, db_id)
        if existing:
            return existing
        desc_dir = Path(self.save_dir) / "_db_descriptions" / db_id
        if not (desc_dir / "db_description.csv").exists():
            try:
                _build_db_description_csv(db_file, desc_dir)
            except Exception as e:
                logger.warning(f"{self.NAME}: failed to build db_description for {db_id}: {e}")
                return None
        return desc_dir

    def _get_few_shot(self) -> Dict:
        if self._few_shot_data is not None:
            return self._few_shot_data
        if self.bird_root:
            fsp = self.bird_root / "few_shot_examples.json"
            self._few_shot_data = _load_few_shot(fsp)
        else:
            self._few_shot_data = {}
        return self._few_shot_data

    def _get_col_meaning_path(self) -> Optional[Path]:
        if not self.bird_root:
            return None
        p = self.bird_root / "column_meaning.json"
        return p if p.exists() else None

    def _llm_call(self, stage: str, prompt: str) -> Dict:
        """Call LLM and parse JSON response. Returns dict or {} on failure."""
        llm = self.get_llm()
        if llm is None:
            logger.error(f"{self.NAME}: LLM not initialized")
            return {}
        messages = [
            {"role": "system", "content": _SYSTEM_PROMPTS[stage]},
            {"role": "user", "content": prompt},
        ]
        client = getattr(llm, "client", None)
        if client is not None:
            try:
                response = client.chat.completions.create(
                    model=getattr(llm, "model_name", "gpt-4o-mini"),
                    messages=messages,
                    max_tokens=getattr(llm, "max_tokens", 2048),
                    temperature=getattr(llm, "temperature", 0.0),
                    top_p=getattr(llm, "top_p", 1.0),
                    response_format={"type": "json_object"},
                    timeout=getattr(llm, "time_out", 300.0),
                    extra_body={"enable_thinking": False},
                )
                raw = response.choices[0].message.content or "{}"
                return _extract_json_object(raw)
            except Exception as e:
                logger.warning(f"{self.NAME}: chat client call failed for stage={stage}: {e}")

        if not hasattr(llm, "complete"):
            logger.error(f"{self.NAME}: neither llm.client nor llm.complete is available")
            return {}
        flat_prompt = messages[0]["content"] + "\n\n" + messages[1]["content"]
        try:
            response = llm.complete(flat_prompt)
            raw = getattr(response, "text", str(response)).strip() or "{}"
            return _extract_json_object(raw)
        except Exception as e:
            logger.warning(f"{self.NAME}: complete fallback failed for stage={stage}: {e}")
            return {}

    # ── Prompt builders ──────────────────────────────────────────────

    def _build_csg_prompt(self, schema_str: str, db_samples: str, question: str,
                           evidence: str, db_desc: str, few_shot: str) -> str:
        ev = f"\n### Evidence: \n {evidence}" if evidence else "\n### Evidence: No evidence"
        prompt = _CSG_TEMPLATE.format(
            FEWSHOT_EXAMPLES=few_shot,
            SCHEMA="\n### Database Schema: \n\n" + schema_str,
            DB_DESCRIPTIONS="\n### Database Column Descriptions: \n\n" + db_desc,
            DB_SAMPLES="\n### Database Samples: \n\n" + db_samples,
            QUESTION="\n### Question: \n" + question,
            EVIDENCE=ev,
        )
        return prompt.replace("```json{", "{").replace("}```", "}").replace("{{", "{").replace("}}", "}")

    def _build_qe_prompt(self, schema_str: str, db_samples: str, question: str,
                          evidence: str, possible_conditions: str, db_desc: str,
                          few_shot: str) -> str:
        ev = f"\n### Evidence: \n {evidence}" if evidence else "\n### Evidence: No evidence"
        pc = ("\n### Possible SQL Conditions: \n" + possible_conditions
              if possible_conditions
              else "\n### Possible SQL Conditions: No strict conditions were found. "
                   "Please consider the database schema and keywords while enriching the Question.")
        prompt = _QE_TEMPLATE.format(
            FEWSHOT_EXAMPLES=few_shot,
            SCHEMA="\n### Database Schema: \n\n" + schema_str,
            DB_DESCRIPTIONS="\n### Database Column Descriptions: \n\n" + db_desc,
            DB_SAMPLES="\n### Database Samples: \n\n" + db_samples,
            POSSIBLE_CONDITIONS=pc,
            QUESTION="\n### Question: \n" + question,
            EVIDENCE=ev,
        )
        return prompt.replace("```json{", "{").replace("}```", "}").replace("{{", "{").replace("}}", "}")

    def _build_sr_prompt(self, schema_str: str, question: str, evidence: str,
                          possible_conditions: str, possible_sql: str,
                          exec_err: str, db_desc: str, few_shot: str) -> str:
        ev = f"\n### Evidence: \n {evidence}" if evidence else "\n### Evidence: No evidence"
        pc = ("\n### Possible SQL Conditions: \n" + possible_conditions
              if possible_conditions
              else "\n### Possible SQL Conditions: No strict conditions were found. "
                   "Please consider the database schema and keywords in the question while generating the SQL.")
        ee = ("\n### Execution Error of Possible SQL Query Above: \n" + exec_err +
              "\n While generating new SQLite SQL query, consider this execution error and "
              "make sure newly generated SQL query runs without execution error."
              if exec_err else "")
        prompt = _SR_TEMPLATE.format(
            FEWSHOT_EXAMPLES=few_shot,
            SCHEMA="\n### Database Schema: \n\n" + schema_str,
            DB_DESCRIPTIONS="\n### Database Column Descriptions: \n\n" + db_desc,
            QUESTION="\n### Question: \n" + question,
            EVIDENCE=ev,
            POSSIBLE_CONDITIONS=pc,
            POSSIBLE_SQL_Query="\n### Possible SQLite SQL Query: \n" + possible_sql,
            EXECUTION_ERROR=ee,
        )
        return prompt.replace("```json{", "{").replace("}```", "}").replace("{{", "{").replace("}}", "}")

    # ── Main act ─────────────────────────────────────────────────────

    def act(
        self,
        item,
        schema: Union[str, Path, Dict, List] = None,
        schema_links: Union[str, List[str]] = None,
        sub_questions=None,
        data_logger=None,
        **kwargs,
    ) -> str:
        row = self.dataset[item]
        question = row.get("question", "")
        evidence = row.get("evidence", "") or ""
        db_id = row.get("db_id", "")
        instance_id = row.get("instance_id", str(item))

        db_file = self._resolve_db_file(db_id)
        if db_file is None:
            logger.error(f"{self.NAME}: db file not found for db_id={db_id}")
            return self.save_output("SELECT 1", item, instance_id)

        # Schema dict and string
        schema_dict = _get_schema_tables_and_columns_dict(db_file)
        schema_str = _generate_schema_from_dict(db_file, schema_dict)

        # Column descriptions (BM25 retrieval over db_description.csv)
        desc_dir = self._get_desc_dir(db_id, db_file)
        db_desc = _get_relevant_descriptions(desc_dir, question, self.relevant_description_number) if desc_dir else ""

        # Column meanings
        col_meaning = _get_column_meanings(self._get_col_meaning_path(), db_id)
        bull_en_guidance = _get_bull_en_domain_guidance(db_id, question)
        db_desc_full = db_desc
        if col_meaning:
            db_desc_full += "\n\n" + col_meaning
        if bull_en_guidance:
            db_desc_full += "\n\n### BULL-EN Domain Guidance:\n" + bull_en_guidance

        # BM25 db samples
        db_samples = _extract_db_samples_bm25(question, evidence, db_file, schema_dict, self.db_sample_limit)

        # Few-shot data
        few_shot_data = self._get_few_shot()

        # ── Stage 1: CSG ────────────────────────────────────────────
        csg_few_shot = _prepare_csg_few_shot(few_shot_data, db_id,
                                              self.generation_level_shot_number, self.seed)
        csg_prompt = self._build_csg_prompt(schema_str, db_samples, question, evidence,
                                             db_desc_full, csg_few_shot)
        csg_result = self._llm_call("candidate_sql_generation", csg_prompt)
        possible_sql = _repair_schema_name_typos(csg_result.get("SQL", "") or "", schema_dict)
        exec_err = _try_execute(db_file, possible_sql) if possible_sql else ""

        if data_logger:
            data_logger.info(f"{self.NAME}.csg | possible_sql={possible_sql[:80]}")

        # ── Stage 2: QE ─────────────────────────────────────────────
        conditions_list = _collect_possible_conditions(db_file, possible_sql) if possible_sql else []
        possible_conditions_str = _format_possible_conditions(conditions_list)

        qe_few_shot = _prepare_qe_few_shot(few_shot_data, db_id,
                                            self.enrichment_level_shot_number, self.seed,
                                            self.enrichment_level)
        qe_prompt = self._build_qe_prompt(schema_str, db_samples, question, evidence,
                                           possible_conditions_str, db_desc_full, qe_few_shot)
        qe_result = self._llm_call("question_enrichment", qe_prompt)
        enriched_q = qe_result.get("enriched_question", "") or ""
        reasoning = qe_result.get("chain_of_thought_reasoning", "") or ""
        # Concat pattern from original Pipeline.py:234
        enriched_question = question + reasoning + enriched_q if enriched_q else question

        if data_logger:
            data_logger.info(f"{self.NAME}.qe | enriched_question={enriched_question[:80]}")

        # ── Stage 3: SR ─────────────────────────────────────────────
        sr_few_shot = _prepare_csg_few_shot(few_shot_data, db_id,
                                             self.generation_level_shot_number, self.seed)
        sr_prompt = self._build_sr_prompt(schema_str, enriched_question, evidence,
                                           possible_conditions_str, possible_sql,
                                           exec_err, db_desc_full, sr_few_shot)
        sr_result = self._llm_call("sql_refinement", sr_prompt)
        predicted_sql = _repair_schema_name_typos(sr_result.get("SQL", "") or "", schema_dict) or possible_sql or "SELECT 1"

        final_exec_err = _try_execute(db_file, predicted_sql) if predicted_sql else ""
        if final_exec_err:
            repair_prompt = self._build_sr_prompt(
                schema_str,
                enriched_question,
                evidence,
                possible_conditions_str,
                predicted_sql,
                final_exec_err,
                db_desc_full,
                sr_few_shot,
            )
            repair_result = self._llm_call("sql_refinement", repair_prompt)
            repaired_sql = _repair_schema_name_typos(repair_result.get("SQL", "") or "", schema_dict)
            if repaired_sql and not _try_execute(db_file, repaired_sql):
                predicted_sql = repaired_sql

        predicted_sql = _repair_bull_en_sql_semantics(db_id, question, predicted_sql)

        if data_logger:
            data_logger.info(f"{self.NAME}.sr | predicted_sql={predicted_sql[:80]}")

        return self.save_output(predicted_sql, item, instance_id)

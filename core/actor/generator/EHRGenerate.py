"""EHR-SQL GPT baseline generator.

The EHRSQL path follows the 2024 baseline constraints:
  - post_process_sql from scoring_program/postprocessing.py
  - abstain logic: output "null" for unanswerable MIMIC-IV questions
  - few-shot examples: 2 answerable + 1 unanswerable

For non-EHR benchmarks this actor keeps the same simple GPT baseline shape but
disables clinical abstention so it can be evaluated as a normal Text2SQL method.
"""

import re
import sqlite3
import json
import time
from os import PathLike
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from loguru import logger

from core.actor.generator.BaseGenerate import BaseGenerator
from core.data_manage import Dataset
from core.db_path import resolve_sqlite_file


# Ported verbatim from scoring_program/postprocessing.py
CURRENT_DATE = "2100-12-31"
CURRENT_TIME = "23:59:00"
NOW = f"{CURRENT_DATE} {CURRENT_TIME}"
PRECOMPUTED_DICT = {
    'temperature': (35.5, 38.1),
    'sao2': (95.0, 100.0),
    'heart rate': (60.0, 100.0),
    'respiration': (12.0, 18.0),
    'systolic bp': (90.0, 120.0),
    'diastolic bp': (60.0, 90.0),
    'mean bp': (60.0, 110.0),
}
TIME_PATTERN = r"(DATE_SUB|DATE_ADD)\((\w+\(\)|'[^']+')[, ]+ INTERVAL (\d+) (MONTH|YEAR|DAY)\)"


def _convert_date_function(match: re.Match) -> str:
    """Verbatim port of convert_date_function from postprocessing.py."""
    function = match.group(1)
    date = match.group(2)
    number = match.group(3)
    unit = match.group(4).lower()
    if number == '1':
        unit = unit.rstrip('s')
    else:
        unit += 's' if not unit.endswith('s') else ''
    sign = '-' if function == 'DATE_SUB' else '+'
    return f"datetime({date}, '{sign}{number} {unit}')"


def post_process_sql(query: str) -> str:
    """Verbatim port of post_process_sql from scoring_program/postprocessing.py."""
    query = re.sub('[ ]+', ' ', query.replace('\n', ' ')).strip()
    query = query.replace('> =', '>=').replace('< =', '<=').replace('! =', '!=')
    query = re.sub(TIME_PATTERN, _convert_date_function, query)
    if "current_time" in query:
        query = query.replace("current_time", f"'{NOW}'")
    if "current_date" in query:
        query = query.replace("current_date", f"'{CURRENT_DATE}'")
    if "'now'" in query:
        query = query.replace("'now'", f"'{NOW}'")
    if "NOW()" in query:
        query = query.replace("NOW()", f"'{NOW}'")
    if "CURDATE()" in query:
        query = query.replace("CURDATE()", f"'{CURRENT_DATE}'")
    if "CURTIME()" in query:
        query = query.replace("CURTIME()", f"'{CURRENT_TIME}'")
    if re.search(r'[ \n]+([a-zA-Z0-9_]+_lower)', query) and re.search(r'[ \n]+([a-zA-Z0-9_]+_upper)', query):
        vital_lower_expr = re.findall(r'[ \n]+([a-zA-Z0-9_]+_lower)', query)[0]
        vital_upper_expr = re.findall(r'[ \n]+([a-zA-Z0-9_]+_upper)', query)[0]
        vital_name_list = list(set(
            re.findall(r'([a-zA-Z0-9_]+)_lower', vital_lower_expr) +
            re.findall(r'([a-zA-Z0-9_]+)_upper', vital_upper_expr)
        ))
        if len(vital_name_list) == 1:
            processed_vital_name = vital_name_list[0].replace('_', ' ')
            if processed_vital_name in PRECOMPUTED_DICT:
                vital_range = PRECOMPUTED_DICT[processed_vital_name]
                query = query.replace(vital_lower_expr, f"{vital_range[0]}").replace(
                    vital_upper_expr, f"{vital_range[1]}"
                )
    query = query.replace("%y", "%Y").replace('%j', '%J')
    return query


# Few-shot examples: 2 answerable + 1 unanswerable (from EHR-SQL train set)
_DEFAULT_FEW_SHOT = [
    {
        "question": "What are the consumption methods of ampicillin sodium?",
        "is_answerable": True,
        "sql": "SELECT DISTINCT prescriptions.route FROM prescriptions WHERE prescriptions.drug = 'ampicillin sodium'",
    },
    {
        "question": "How is olanzapine (disintegrating tablet) typically consumed?",
        "is_answerable": True,
        "sql": "SELECT DISTINCT prescriptions.route FROM prescriptions WHERE prescriptions.drug = 'olanzapine (disintegrating tablet)'",
    },
    {
        "question": "What is the outpatient schedule today for dr. leigh?",
        "is_answerable": False,
        "sql": "null",
    },
]

_EHR_SYSTEM_PROMPT = """You are a clinical Text-to-SQL assistant for the MIMIC-IV electronic health records database.

The database uses time-shifted dates where the current date/time is '{now}'.

When answering:
- If the question CAN be answered with the given database schema, generate a valid SQLite SELECT statement.
- If the question CANNOT be answered (e.g. it asks about information not in the schema, or is ambiguous), output exactly: null

Use SQLite syntax. For date arithmetic use: datetime(col, '+N days'), datetime(col, '-N months'), etc.
Do NOT use MySQL functions like DATE_ADD, DATE_SUB, NOW(), CURDATE(), CURTIME().
""".strip()

_GENERIC_SYSTEM_PROMPT = """You are a Text-to-SQL assistant.

Given a question and a SQLite database schema, generate one valid SQLite SELECT statement that answers the question.
Use only tables and columns that appear in the schema.
Preserve literal values from the question and evidence.
Return only the SQL query, without explanation.
""".strip()

_FEW_SHOT_TEMPLATE = """Example {n}:
Question: {question}
SQL: {sql}
"""

_GENERATE_PROMPT = """{system}

Database schema:
{schema}

{evidence}

{few_shots}

Question: {question}
SQL:"""


def _build_schema_text(schema: Any) -> str:
    """Build a concise schema description from Squrve schema records."""
    if isinstance(schema, dict):
        # Central format: {table: {columns: [...]}}
        lines = []
        for table, info in schema.items():
            cols = info.get('columns', []) if isinstance(info, dict) else []
            lines.append(f"Table {table}: {', '.join(cols)}")
        return '\n'.join(lines)

    if isinstance(schema, list):
        # Spider format: list of {table_name_original, column_names_original, ...}
        lines = []
        tables = [r for r in schema if 'table_names_original' in r] if schema else []
        if tables:
            # Aggregate tables.json format
            db = tables[0]
            tnames = db.get('table_names_original', [])
            col_names_orig = db.get('column_names_original', [])
            fks = db.get('foreign_keys', [])
            pks = db.get('primary_keys', [])
            # Group columns by table index
            from collections import defaultdict
            col_by_table: Dict[int, List[str]] = defaultdict(list)
            for col_idx, (tbl_idx, col_name) in enumerate(col_names_orig):
                if tbl_idx >= 0:
                    pk_marker = ' (PK)' if col_idx in pks else ''
                    col_by_table[tbl_idx].append(col_name + pk_marker)
            for t_idx, tname in enumerate(tnames):
                cols_str = ', '.join(col_by_table.get(t_idx, []))
                lines.append(f"Table {tname}: {cols_str}")
            # Foreign keys
            if fks:
                lines.append('\nForeign keys:')
                for src_idx, tgt_idx in fks:
                    src_tbl = tnames[col_names_orig[src_idx][0]] if col_names_orig[src_idx][0] >= 0 else '?'
                    src_col = col_names_orig[src_idx][1]
                    tgt_tbl = tnames[col_names_orig[tgt_idx][0]] if col_names_orig[tgt_idx][0] >= 0 else '?'
                    tgt_col = col_names_orig[tgt_idx][1]
                    lines.append(f"  {src_tbl}.{src_col} -> {tgt_tbl}.{tgt_col}")
        else:
            # Parallel format: list of row dicts
            from collections import defaultdict
            by_table: Dict[str, List[str]] = defaultdict(list)
            for row in schema:
                tname = row.get('table_name_original') or row.get('table_name', '')
                col = row.get('column_name_original') or row.get('column_name', '')
                if tname and col:
                    by_table[tname].append(col)
            for tname, cols in by_table.items():
                lines.append(f"Table {tname}: {', '.join(cols)}")
        return '\n'.join(lines)

    return str(schema or '')


@BaseGenerator.register_actor
class EHRGenerator(BaseGenerator):
    """EHR-SQL GPT baseline generator with abstain on unanswerable questions."""

    NAME = "EHRGenerator"

    def __init__(
        self,
        dataset: Optional[Dataset] = None,
        llm: Any = None,
        is_save: bool = True,
        save_dir: Union[str, PathLike] = "../files/pred_sql",
        db_path: Optional[Union[str, PathLike]] = None,
        few_shot_path: Optional[Union[str, PathLike]] = None,
        max_retries: int = 3,
        abstain_on_unanswerable: Optional[bool] = None,
        execute_repair: bool = True,
        execute_timeout: float = 30.0,
        dataset_name: Optional[str] = None,
        **kwargs,
    ):
        self.dataset = dataset
        self.llm = llm
        self.is_save = is_save
        self.save_dir = save_dir
        self.db_path = db_path or (getattr(dataset, 'db_path', None) if dataset else None)
        self.max_retries = max(1, int(max_retries))
        self.abstain_on_unanswerable = abstain_on_unanswerable
        self.execute_repair = execute_repair
        self.execute_timeout = max(1.0, float(execute_timeout))
        self.dataset_name = dataset_name

        # Load few-shot examples from file or use defaults
        self._few_shot: List[Dict] = _DEFAULT_FEW_SHOT
        if few_shot_path and Path(few_shot_path).exists():
            try:
                loaded = json.load(open(few_shot_path))
                self._few_shot = [
                    {
                        'question': e['question'],
                        'is_answerable': e.get('is_answerable', e.get('query', 'null') != 'null'),
                        'sql': e.get('query', e.get('sql', 'null')),
                    }
                    for e in loaded
                ]
            except Exception as exc:
                logger.warning(f"{self.NAME}: failed to load few_shot_path: {exc}")

    def _resolve_db_file(self, db_id: str) -> Optional[Path]:
        if not self.db_path:
            return None
        path = resolve_sqlite_file(self.db_path, db_id)
        return path if path.exists() else None

    def _is_ehr_context(self, db_id: str) -> bool:
        dataset_name = (self.dataset_name or getattr(self.dataset, "name", "") or "").lower()
        return db_id == "mimic_iv" or "ehrsql" in dataset_name or "ehrsql" in str(self.db_path).lower()

    def _should_abstain(self, db_id: str) -> bool:
        if self.abstain_on_unanswerable is not None:
            return bool(self.abstain_on_unanswerable)
        return self._is_ehr_context(db_id)

    def _build_prompt(self, question: str, schema: Any, db_id: str, evidence: str = "") -> str:
        schema_text = _build_schema_text(schema)
        few_shots_text = ''
        if self._should_abstain(db_id):
            system = _EHR_SYSTEM_PROMPT.format(now=NOW)
            for i, ex in enumerate(self._few_shot, 1):
                few_shots_text += _FEW_SHOT_TEMPLATE.format(
                    n=i,
                    question=ex['question'],
                    sql=ex['sql'],
                )
        else:
            system = _GENERIC_SYSTEM_PROMPT
        return _GENERATE_PROMPT.format(
            system=system,
            schema=schema_text,
            evidence=f"Evidence: {evidence}" if evidence else "",
            few_shots=few_shots_text.strip(),
            question=question,
        )

    @staticmethod
    def _extract_sql(response: str) -> str:
        """Extract SQL from LLM response. Returns 'null' if unanswerable."""
        text = (response or '').strip()
        # If model outputs "null" explicitly
        if text.lower() in ('null', 'null;', 'null.'):
            return 'null'
        # Extract from ```sql ... ``` blocks
        fence = re.search(r'```(?:sql|sqlite)?\s*([\s\S]*?)```', text, re.IGNORECASE)
        if fence:
            text = fence.group(1).strip()
        # Extract SELECT statement
        sel = re.search(r'\b(SELECT\s[\s\S]+?)(?:;|\Z)', text, re.IGNORECASE)
        if sel:
            text = sel.group(1).strip()
        if not text.upper().startswith('SELECT'):
            lower = text.lower()
            if any(kw in lower for kw in ('cannot', 'not possible', 'unanswerable', 'not answerable', 'no sql', 'unable')):
                return 'null'
            return 'null'
        return text

    def _try_execute(self, sql: str, db_file: Optional[Path]) -> bool:
        if sql == 'null' or not db_file:
            return True
        con = None
        try:
            con = sqlite3.connect(str(db_file))
            con.text_factory = lambda b: b.decode(errors='ignore')
            deadline = time.monotonic() + self.execute_timeout

            def _interrupt_on_timeout() -> int:
                return 1 if time.monotonic() > deadline else 0

            con.set_progress_handler(_interrupt_on_timeout, 1000)
            cur = con.cursor()
            cur.execute(sql)
            cur.fetchall()
            return True
        except sqlite3.OperationalError as exc:
            if "interrupted" in str(exc).lower():
                logger.debug(f"{self.NAME}: SQL execution timed out after {self.execute_timeout:.1f}s")
            else:
                logger.debug(f"{self.NAME}: SQL execution failed: {exc}")
            return False
        except Exception as exc:
            logger.debug(f"{self.NAME}: SQL execution failed: {exc}")
            return False
        finally:
            if con is not None:
                con.close()

    def _generate(self, prompt: str) -> str:
        llm = self.get_llm()
        if llm is None:
            return 'null'
        for attempt in range(self.max_retries):
            try:
                if hasattr(llm, "complete"):
                    response = llm.complete(prompt)
                    return getattr(response, 'text', str(response)).strip()
                client = getattr(llm, "client", None)
                if client is None:
                    logger.warning(f"{self.NAME}: neither llm.complete nor llm.client is available")
                    return 'null'
                response = client.chat.completions.create(
                    model=getattr(llm, "model_name", "gpt-4o-mini"),
                    messages=[{"role": "user", "content": prompt}],
                    max_tokens=getattr(llm, "max_tokens", 2048),
                    temperature=getattr(llm, "temperature", 0.0),
                    top_p=getattr(llm, "top_p", 1.0),
                    timeout=getattr(llm, "time_out", 300.0),
                    extra_body={"enable_thinking": False},
                )
                return (response.choices[0].message.content or "").strip()
            except Exception as exc:
                logger.warning(f"{self.NAME}: LLM call failed (attempt {attempt+1}): {exc}")
        return 'null'

    def act(
        self,
        item,
        schema: Union[str, PathLike, Dict, List] = None,
        schema_links: Any = None,
        sub_questions: Any = None,
        data_logger=None,
        **kwargs,
    ) -> str:
        row = self.dataset[item]
        question = row.get('question', '')
        db_id = row.get('db_id', 'mimic_iv')
        evidence = row.get('evidence', '') or ''

        if schema is None:
            schema = self.dataset.get_db_schema(item)

        prompt = self._build_prompt(question, schema, db_id, evidence)
        raw = self._generate(prompt)
        sql = self._extract_sql(raw)

        # Apply source post_process_sql to non-null SQL
        if sql != 'null':
            sql = post_process_sql(sql)

        # Try execution. EHRSQL baseline abstains on invalid SQL; generic benchmarks
        # get one error-feedback repair so the actor remains a usable Text2SQL baseline.
        db_file = self._resolve_db_file(db_id)
        if sql != 'null' and not self._try_execute(sql, db_file):
            if self._should_abstain(db_id) or not self.execute_repair:
                logger.debug(f"{self.NAME}: execution failed, abstaining for item {item}")
                sql = 'null'
            else:
                repair_prompt = (
                    f"{prompt}\n\nThe previous SQL failed when executed on SQLite:\n{sql}\n"
                    "Generate a corrected SQLite SELECT query using only the provided schema.\nSQL:"
                )
                repaired = self._extract_sql(self._generate(repair_prompt))
                if repaired != 'null':
                    repaired = post_process_sql(repaired)
                if repaired != 'null' and self._try_execute(repaired, db_file):
                    sql = repaired

        if data_logger:
            data_logger.info(f"{self.NAME}.final_sql | sql={sql[:80]}")

        return self.save_output(sql, item, row.get('instance_id'))

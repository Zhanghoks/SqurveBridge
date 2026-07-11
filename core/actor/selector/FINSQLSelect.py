"""FINSQLSelector — ports self_consistency.py + sql_post_process.py logic.
Adapts db_map loading to use Squrve schema instead of hardcoded tables.json.
"""
import re
from copy import copy
from typing import Any, Dict, List, Optional, Union
from pathlib import Path
from loguru import logger

try:
    from fuzzywuzzy import process as fw_process
    _HAS_FUZZYWUZZY = True
except ImportError:
    _HAS_FUZZYWUZZY = False

from core.actor.selector.BaseSelect import BaseSelector
from core.data_manage import Dataset
from core.utils import load_dataset, save_dataset
from core.db_path import resolve_sqlite_file


# ---------------------------------------------------------------------------
# SQL struct parser (ported from sqliteStructureTrans_modified.py)
# ---------------------------------------------------------------------------

_FROM_RE = re.compile(r" FROM | from | From ")
_ON_RE = re.compile(r" ON | On | on")
_WHERE_RE = re.compile(r" WHERE | Where | where ")
_AS_RE = re.compile(r" +AS | +As | +as ")
_JOIN_RE = re.compile(r" LEFT +JOIN | Left +Join | left +join | INNER +JOIN | Inner +Join | inner +join | JOIN | Join | join")
_SEL_RE = re.compile(r"SELECT +|Select +|select +")
_GRP_RE = re.compile(r" GROUP +BY | Group +By | group +by ")
_HAV_RE = re.compile(r" HAVING | Having | having ")
_LIMIT_RE = re.compile(r" LIMIT | Limit | limit")
_ORDER_RE = re.compile(r" ORDER +BY | Order +By | order +by | ORDER +by ")
_AND_OR_RE = re.compile(r"( AND | And | and | OR | Or | or ) (?=(?:[^']|'[^']*')*$)")
_AND_OR_RE2 = re.compile(r"( AND | And | and | OR | Or | or )")
_AGG_RE = re.compile(r"count\(|avg\(|sum\(|max\(|min\(")
_WHERE_OP_RE = re.compile(
    "(" + "|".join([' like ', " LIKE ", " IS +NOT ", " is +not ",
                    " ?>= ?", " ?<= ?", " ?!= ?", " ?= ?", " ?> ?", " ?< ?"]) + ")")
_DATE_RE = re.compile(r"(strftime\('%Y',|strftime\('%m',|strftime\('%d',|round\(strftime\('%m',)")
_DATE_OPS = {
    "strftime('%Y',": "strftime('%Y', {})",
    "strftime('%m',": "strftime('%m', {})",
    "strftime('%d',": "strftime('%d', {})",
    "round(strftime('%m',": "round(strftime('%m',{})/3.0 + 0.495)",
}


def _agg_extract(span):
    res = _AGG_RE.findall(span.lower())
    if not res:
        return None, span
    agg = res[0][:-1].lower()
    return agg, span[len(agg) + 1:][:-1].strip()


def _agg_extract_hav(span):
    res = _AGG_RE.findall(span.lower())
    if not res:
        return None, span
    agg = res[0][:-1].lower()
    return agg, span[len(agg) + 1:].strip()


def _distinct_extract(span):
    if span.lower().startswith("distinct"):
        return True, " ".join(span.split(" ")[1:]).strip()
    return False, span


def _extract_from_span(sql):
    parts = _FROM_RE.split(sql)
    tab_tmp = _WHERE_RE.split(parts[1])[0]
    tab_tmp = _GRP_RE.split(tab_tmp)[0]
    tab_tmp = _ORDER_RE.split(tab_tmp)[0]
    return _LIMIT_RE.split(tab_tmp)[0].strip()


def _table_alias_gen(from_str):
    alias2table = {}
    if " join " in from_str.lower():
        toks = [x for x in from_str.split(" ") if x]
        for k, tok in enumerate(toks):
            if tok.lower() in ("join", "on"):
                alias_ = toks[k - 1]
                tok2, tok3 = toks[k - 2], toks[k - 3] if k >= 3 else ""
                alias2table[alias_] = tok2 if tok2.lower() != "as" else tok3
    else:
        for mention in [x.strip() for x in from_str.split(",")]:
            parts = [x for x in mention.split(" ") if x]
            alias2table["" if len(parts) == 1 else parts[-1]] = parts[0]
    return alias2table


def _select_extract(sql, a2t):
    span = _SEL_RE.split(sql)[1].strip()
    span = _FROM_RE.split(span)[0].strip()
    is_dist, span = _distinct_extract(span)
    sel = [is_dist]
    for tok in span.split(","):
        tok = tok.strip()
        agg, tok = _agg_extract(tok)
        is_d, tok = _distinct_extract(tok)
        parts = tok.split(".")
        if len(parts) == 1:
            sel.append([agg, None, parts[0], is_d])
        else:
            sel.append([agg, a2t.get(parts[0], parts[0]), parts[1], is_d])
    return sel


def _grpby_extract(sql, a2t):
    content_list, str_pat = [], re.compile(r"\'(.*?)\'")
    st = 0
    for m in str_pat.finditer(sql):
        content_list.append(sql[st:m.span()[0]])
        st = m.span()[1]
    content_list.append(sql[st:])
    if not any(" group " in c.lower() for c in content_list):
        return []
    span = _GRP_RE.split(sql)[1].strip()
    span = _LIMIT_RE.split(span)[0]
    span = _HAV_RE.split(span)[0]
    span = _ORDER_RE.split(span)[0]
    result = []
    for tok in span.split(","):
        parts = tok.strip().split(".")
        if len(parts) == 1:
            result.append([None, parts[0]])
        else:
            result.append([a2t.get(parts[0], parts[0]), parts[1]])
    return result


def _orderby_extract(sql, a2t):
    if " order " not in sql.lower():
        return []
    span = _ORDER_RE.split(sql)[1].strip()
    span = _LIMIT_RE.split(span)[0]
    span = _HAV_RE.split(span)[0]
    span = _GRP_RE.split(span)[0]
    result = []
    for tok in span.split(","):
        tok = tok.strip()
        parts = [x for x in tok.split(" ") if x]
        order_ = parts[-1].lower() if parts[-1].lower() in ("asc", "desc") else None
        col_info = " ".join(parts[:-1] if order_ else parts)
        agg, col_info = _agg_extract(col_info)
        is_d, col_info = _distinct_extract(col_info)
        cp = col_info.split(".")
        if len(cp) == 2:
            t, c = a2t.get(cp[0], cp[0]), cp[1]
        else:
            t, c = None, cp[0]
        result.append([order_, agg, is_d, t, c])
    return result


def _one_where_cond(tok, a2t, agg_op_tmp):
    parts = _WHERE_OP_RE.split(tok)
    if agg_op_tmp is not None:
        parts[0] = parts[0].strip()[:-1]
    col_info = parts[0].split(".")
    date_parts = _DATE_RE.split(parts[0])
    date_op = None
    if len(date_parts) == 3:
        date_op = _DATE_OPS.get(date_parts[1])
    if len(col_info) == 2 and date_op is None:
        tab = a2t.get(col_info[0].strip().split("(")[-1].strip(), col_info[0].strip())
        col = col_info[1]
    elif len(col_info) >= 2 and date_op is not None:
        tab = a2t.get(col_info[0].strip().split(",")[-1].strip(), col_info[0].strip())
        col = col_info[1][:-1]
    else:
        tab, col = None, col_info[0].strip()
    op = parts[1].strip().lower() if len(parts) > 1 else "="
    if re.compile(r"(is +not)").findall(op):
        op = "not"
    val = parts[2].strip() if len(parts) > 2 else ""
    return [tab, col, op, val, date_op]


def _where_having_extract(sql, a2t, mode="where"):
    if f" {mode} " not in sql.lower():
        return []
    span = (_WHERE_RE if mode == "where" else _HAV_RE).split(sql)[1].strip()
    span = _LIMIT_RE.split(span)[0]
    span = _GRP_RE.split(span)[0]
    span = _ORDER_RE.split(span)[0]
    pat = re.compile(r"\band\b(?=(?:[^']*'[^']*')*[^']*$)")
    constraints = (_AND_OR_RE2 if pat.search(sql) else _AND_OR_RE).split(span)
    constraints = [x.strip() for x in constraints if x.strip()]
    result = []
    for i, c in enumerate(constraints):
        if i % 2 == 1:
            result.append(c.lower())
            continue
        is_start_grp = c.startswith("(")
        if is_start_grp:
            c = c[1:]
        agg_op = None
        extra = []
        if mode == "having":
            agg_op, c = _agg_extract_hav(c)
            is_d, c = _distinct_extract(c)
            extra = [agg_op, is_d]
        cond = _one_where_cond(c, a2t, agg_op)
        if mode == "where" and is_start_grp:
            cond[1] = "(" + cond[1]
        if mode == "having":
            result.append(extra + cond[:-1])
        else:
            result.append([cond])
    return result


def sqlite_2_struct(question, q_id, sql, db_name):
    sql = sql.replace("\n", " ").strip(";| ")
    from_str = _extract_from_span(sql)
    a2t = _table_alias_gen(from_str)
    from_conds = []
    if len(a2t) > 1:
        for on_part in _ON_RE.split(from_str)[1:]:
            eq = on_part.split("=")
            p1 = eq[0].split(".")
            p2 = eq[1].strip().split(" ")[0].split(".")
            from_conds.append([[a2t.get(p1[0].strip(), p1[0].strip()), p1[1].strip()],
                                [a2t.get(p2[0].strip(), p2[0].strip()), p2[1].strip()]])
    return {
        "q_id": q_id, "question": question, "db_name": db_name, "sql_query": sql,
        "from": {"table_units": list(set(a2t.values())), "conds": from_conds},
        "select": _select_extract(sql, a2t),
        "where": _where_having_extract(sql, a2t, "where"),
        "groupBy": _grpby_extract(sql, a2t),
        "having": _where_having_extract(sql, a2t, "having"),
        "orderBy": _orderby_extract(sql, a2t),
        "limit": (int(sql.lower().split(" limit ")[1]) if " limit " in sql.lower() else None),
        "alias_2_table": a2t,
    }


# ---------------------------------------------------------------------------
# Self-consistency (ported from self_consistency.py)
# ---------------------------------------------------------------------------

def result_eq(d1, d2):
    if set(d1["from"]["table_units"]) != set(d2["from"]["table_units"]):
        return False
    def _sel_set(d):
        return {" ".join(filter(None, [str(x[0] or ""), str(x[2])])) for x in d["select"][1:]}
    if _sel_set(d1) != _sel_set(d2):
        return False
    def _where_set(d):
        s = set()
        for item in d["where"]:
            if not isinstance(item, list):
                continue
            c = item[0]
            s.add(" ".join(str(x) for x in c[1:3] + [c[3]]))
        return s
    if _where_set(d1) != _where_set(d2):
        return False
    if {x[1] for x in d1["groupBy"]} != {x[1] for x in d2["groupBy"]}:
        return False
    def _order_set(d):
        return {" ".join(filter(None, [str(x[0] or "asc"), str(x[3] or ""), str(x[4])])) for x in d["orderBy"]}
    if _order_set(d1) != _order_set(d2):
        return False
    return True


def get_consistent_sqls(db_id: str, p_sqls: List[str], select_number: int = 8) -> str:
    candidates = p_sqls[:select_number]
    clusters: List[List[str]] = []
    struct_map: Dict[str, Any] = {}
    for sql in candidates:
        try:
            struct_map[sql] = sqlite_2_struct("", "", sql, db_id)
        except Exception:
            continue
        matched = False
        for cluster in clusters:
            try:
                if result_eq(struct_map[cluster[0]], struct_map[sql]):
                    cluster.append(sql)
                    matched = True
                    break
            except Exception:
                pass
        if not matched:
            clusters.append([sql])
    if not clusters:
        return candidates[0] if candidates else "SELECT"
    clusters.sort(key=len, reverse=True)
    return clusters[0][0]


# ---------------------------------------------------------------------------
# Post-process & alignment (adapted from sql_post_process.py)
# ---------------------------------------------------------------------------

def _build_db_map(schema_items: List[Dict]) -> Dict:
    col2table: Dict[str, List[str]] = {}
    table2col: Dict[str, List[str]] = {}
    for si in schema_items:
        if not isinstance(si, dict):
            continue
        t = (si.get("table_name_original") or si.get("table_name", "")).lower()
        c = (si.get("column_name_original") or si.get("column_name", "")).lower()
        if not t or not c:
            continue
        col2table.setdefault(c, [])
        if t not in col2table[c]:
            col2table[c].append(t)
        table2col.setdefault(t, [])
        if c not in table2col[t]:
            table2col[t].append(c)
    return {"column2table": col2table, "table2column": table2col}


def _fix_typos(sql: str) -> str:
    sql = sql.replace("==", "=")
    while "  " in sql:
        sql = sql.replace("  ", " ")
    if "join" in sql.lower():
        if "as a join" not in sql:
            sql = sql.replace("a join", "as a join")
        if "as b on" not in sql:
            sql = sql.replace("b on", "as b on")
    return sql


def post_process(sql: str, db_map: Dict) -> str:
    sql = _fix_typos(sql)
    try:
        struct = sqlite_2_struct("", "", sql, "")
        for item in struct["select"][1:]:
            col = (item[2] or "").lower()
            if col and col not in db_map["column2table"]:
                if _HAS_FUZZYWUZZY:
                    choices = list(db_map["column2table"].keys())
                    best, _ = fw_process.extractOne(col, choices)
                    sql = re.sub(r'\b' + re.escape(col) + r'\b', best, sql, flags=re.IGNORECASE)
    except Exception:
        pass
    return sql


def alignment(sql: str, db_map: Dict) -> str:
    try:
        struct = sqlite_2_struct("", "", sql, "")
        a2t = struct.get("alias_2_table", {})
        t2a = {v: k for k, v in a2t.items()} if a2t else {}
        from_tables = {str(t).lower() for t in struct.get("from", {}).get("table_units", [])}
        for t, c in [(x[1], x[2]) for x in struct["select"][1:] if x[1] and x[2]]:
            c_lower = c.lower()
            if c_lower in db_map["column2table"] and t.lower() not in db_map["column2table"][c_lower]:
                correct_t = next(
                    (candidate for candidate in db_map["column2table"][c_lower]
                     if candidate.lower() in from_tables),
                    None,
                )
                if not correct_t:
                    continue
                alias = t2a.get(t, t)
                correct_alias = t2a.get(correct_t, correct_t)
                sql = sql.replace(f"{alias}.{c}", f"{correct_alias}.{c}")
    except Exception:
        pass
    return sql


def _has_cjk(text: str) -> bool:
    return bool(re.search(r"[\u4e00-\u9fff]", text or ""))


def _sql_literals(sql: str) -> List[str]:
    return re.findall(r"'([^']*)'", sql or "")


def _question_words(question: str) -> set:
    return set(re.findall(r"[a-z][a-z0-9]+", (question or "").lower()))


def _literal_matches_question(question: str, sql: str) -> bool:
    q_lower = (question or "").lower()
    q_words = _question_words(question)
    for literal in _sql_literals(sql):
        if _has_cjk(literal):
            continue
        literal_lower = literal.lower().strip("% ")
        literal_words = re.findall(r"[a-z][a-z0-9]+", literal_lower)
        if literal_lower and literal_lower in q_lower:
            return True
        if literal_words and all(word in q_words for word in literal_words):
            return True
    return False


def _top_level_from_index(sql: str) -> Optional[int]:
    depth = 0
    in_quote = False
    i = 0
    lower = sql.lower()
    while i < len(sql):
        ch = sql[i]
        if ch == "'":
            in_quote = not in_quote
            i += 1
            continue
        if in_quote:
            i += 1
            continue
        if ch == "(":
            depth += 1
        elif ch == ")" and depth:
            depth -= 1
        elif depth == 0 and lower.startswith(" from ", i):
            return i
        i += 1
    return None


def _widen_projection(sql: str) -> str:
    sql_lower = (sql or "").lower()
    if (
        not re.search(r"(?i)^\s*select\b", sql or "")
        or re.search(r"(?i)^\s*with\b", sql or "")
        or re.search(r"\b(count|avg|sum|min|max)\s*\(", sql_lower)
        or re.search(r"(?i)^\s*select\s+distinct\b", sql or "")
        or re.search(r"(?i)^\s*select\s+\*\s+from\b", sql or "")
    ):
        return sql
    from_index = _top_level_from_index(sql)
    if from_index is None:
        return sql
    select_part = sql[:from_index]
    if "(" in select_part or ")" in select_part:
        return sql
    return "SELECT *" + sql[from_index:]


def _selector_score(question: str, sql: str) -> float:
    question_lower = (question or "").lower()
    sql_lower = (sql or "").lower()
    score = 0.0

    literals = " ".join(_sql_literals(sql))
    if _has_cjk(literals) and not _has_cjk(question):
        score -= 5.0
    if _literal_matches_question(question, sql):
        score += 5.0
    if "select *" in sql_lower:
        score += 1.0
    if re.search(r"[<>]=?\s*0\.\d+", sql_lower) and "%" in (question or ""):
        score -= 4.0
    if re.search(r"(?i)^\s*select\s*$", sql or ""):
        score -= 20.0
    return score


# ---------------------------------------------------------------------------
# Actor
# ---------------------------------------------------------------------------

@BaseSelector.register_actor
class FINSQLSelector(BaseSelector):
    NAME = "FINSQLSelector"

    def __init__(self, dataset=None, llm=None, is_save=True,
                 save_dir="../files/pred_sql", select_number=8, **kwargs):
        self.dataset = dataset
        self.llm = llm
        self.is_save = is_save
        self.save_dir = save_dir
        self.select_number = select_number

    def _execution_candidates(self, item: int, candidates: List[str], data_logger=None) -> List[str]:
        context = self._execution_context(item)
        if context is None:
            return candidates

        db_type, db_path, credential = context
        successful = []
        attempted = False
        for sql in candidates[:self.select_number]:
            if not sql:
                continue
            attempted = True
            result = self.execute_sql_safe(sql, db_type=db_type, db_path=db_path, credential=credential)
            if result.get("success"):
                successful.append(sql)
            elif data_logger:
                data_logger.info(f"{self.NAME}.exec_failed | sql={sql} | error={result.get('error')}")

        if attempted and successful:
            return successful
        return candidates

    def _execution_context(self, item: int):
        row = self.dataset[item]
        db_type = row.get("db_type", "sqlite")
        db_id = row.get("db_id", "")
        credential = getattr(self.dataset, "db_credential", None) or getattr(self.dataset, "credential", None)
        db_path = row.get("db_path") or getattr(self.dataset, "db_path", "")
        if db_type == "sqlite" and db_id and db_path:
            try:
                db_path = str(resolve_sqlite_file(db_path, db_id))
            except Exception:
                pass
        if not db_path:
            return None
        return db_type, db_path, credential

    def _is_executable(self, item: int, sql: str, data_logger=None) -> bool:
        context = self._execution_context(item)
        if context is None or not sql:
            return False
        db_type, db_path, credential = context
        result = self.execute_sql_safe(sql, db_type=db_type, db_path=db_path, credential=credential)
        if not result.get("success") and data_logger:
            data_logger.info(f"{self.NAME}.exec_failed | sql={sql} | error={result.get('error')}")
        return bool(result.get("success"))

    def _candidate_variants(self, sql: str) -> List[str]:
        variants = []
        for variant in (sql, _widen_projection(sql)):
            if not variant:
                continue
            normalized = " ".join(variant.strip().rstrip(";").split()) + ";"
            if normalized not in variants:
                variants.append(normalized)
        return variants

    def _rank_candidates(self, item: int, candidates: List[str], data_logger=None) -> List[str]:
        question = self.dataset[item].get("question", "")
        ranked = []
        order = 0
        for candidate_index, sql in enumerate(candidates[:self.select_number]):
            for variant in self._candidate_variants(sql):
                if not self._is_executable(item, variant, data_logger=data_logger):
                    continue
                score = _selector_score(question, variant)
                if candidate_index == 0:
                    score += 0.4
                ranked.append((score, -candidate_index, -order, variant))
                order += 1

        if not ranked:
            return candidates
        ranked.sort(reverse=True)
        result = []
        for _, _, _, sql in ranked:
            if sql not in result:
                result.append(sql)
        if data_logger and result:
            data_logger.info(f"{self.NAME}.ranked_best | score={ranked[0][0]:.3f} | sql={result[0]}")
        return result

    def act(self, item, schema=None, schema_links=None, pred_sql=None, data_logger=None, **kwargs) -> str:
        row = self.dataset[item]
        db_id = row.get("db_id", "")

        candidates = self.load_pred_sql(pred_sql, item)
        if not candidates:
            return self.save_result("SELECT", item, row.get("instance_id"))

        # Build db_map from schema
        schema_items = schema or self.dataset.get_db_schema(item) or []
        if isinstance(schema_items, dict):
            from core.data_manage import single_central_process
            schema_items = single_central_process(schema_items)
        db_map = _build_db_map(schema_items)

        # Step 1: post_process per candidate. Keep the raw SQL next to the
        # processed SQL so a destructive rewrite can be rolled back.
        processed = []
        for sql in candidates:
            if not sql:
                continue
            rewritten = post_process(sql, db_map)
            if rewritten != sql and not self._is_executable(item, rewritten, data_logger=data_logger):
                processed.append(sql)
            else:
                processed.append(rewritten)

        # Step 2: keep executable candidates when the DB is available, then
        # rank safe variants. Bull-EN often has correct filters/table choice
        # but incomplete projection; Squrve EX accepts extra columns when the
        # gold columns are present, so SELECT * is a robust selector-side
        # repair for non-aggregate queries.
        executable_or_all = self._execution_candidates(item, processed, data_logger=data_logger)
        executable_or_all = self._rank_candidates(item, executable_or_all, data_logger=data_logger)
        best = get_consistent_sqls(db_id, executable_or_all, self.select_number)

        # Step 3: alignment. The original FinSQL alignment is useful when it
        # repairs a wrong table qualifier, but on Bull-EN many common columns
        # such as ChiName occur in several tables. Never keep an alignment
        # rewrite that fails execution when the pre-alignment SQL runs.
        aligned = alignment(best, db_map)
        if aligned != best:
            if self._is_executable(item, aligned, data_logger=data_logger):
                best = aligned
            elif data_logger:
                data_logger.info(f"{self.NAME}.alignment_reverted | before={best} | after={aligned}")

        return self.save_result(best, item, row.get("instance_id"))

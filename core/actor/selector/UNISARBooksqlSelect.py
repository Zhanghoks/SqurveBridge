"""UNISAR BookSQL Selector — FK-graph JOIN inference + @ → . conversion.

Rule-based post-processing selector. Ports post_processing_sql() logic from
candidates/BookSQL-main/UNISAR/step3_evaluate.py.

Steps:
1. Load pred_sql (may be in table@column notation)
2. Load schema to build a simple FK graph (table adjacency)
3. Run post_processing_sql: infer JOIN paths via networkx shortest-path on FK graph
4. Replace @ with . in final SQL
5. Save and return result
"""

import re
from os import PathLike
from typing import Union, Dict, List, Optional, Any

from loguru import logger

from core.actor.selector.BaseSelect import BaseSelector
from core.data_manage import Dataset
from core.utils import load_dataset

try:
    import networkx as nx
    _HAS_NX = True
except ImportError:
    _HAS_NX = False
    logger.warning("[UNISARBooksqlSelector] networkx not available — FK JOIN inference disabled")


def _build_fk_graph(schema_list: List[Dict]):
    """Build a directed graph of table FK relationships from Squrve schema items.

    Returns (graph, tables, schema_obj) where:
      graph: nx.DiGraph with edges (table_idx, table_idx, columns=(col_idx, col_idx))
      tables: list of table names (lower)
      col_list: flat list of "table@col" strings (index = column id)
    """
    if not _HAS_NX:
        return None, [], []

    tables = []
    col_list = ["*"]  # col_list[0] = wildcard *
    col_to_table_idx = {}  # "table@col" → table_idx

    for item in schema_list:
        if not isinstance(item, dict):
            continue
        tname = (item.get("table_name_original") or item.get("table_name", "")).lower()
        if not tname:
            continue
        if tname not in tables:
            tables.append(tname)
        t_idx = tables.index(tname)

        cols = item.get("column_names_original") or item.get("column_names") or []
        for col in cols:
            col_lower = col.lower() if isinstance(col, str) else str(col).lower()
            token = f"{tname}@{col_lower}"
            if token not in col_list:
                col_idx = len(col_list)
                col_list.append(token)
                col_to_table_idx[token] = t_idx

    # Build FK graph
    graph = nx.DiGraph()
    for t_idx in range(len(tables)):
        graph.add_node(t_idx)

    for item in schema_list:
        if not isinstance(item, dict):
            continue
        tname = (item.get("table_name_original") or item.get("table_name", "")).lower()
        if not tname or tname not in tables:
            continue
        t_idx = tables.index(tname)

        fk_entry = item.get("fk") or item.get("foreign_key")
        if fk_entry and isinstance(fk_entry, str):
            parts = fk_entry.split(".")
            if len(parts) == 2:
                other_table = parts[0].lower()
                other_col = parts[1].lower()
                if other_table in tables:
                    o_idx = tables.index(other_table)
                    src_tok = f"{tname}@{parts[1].lower()}" if len(parts) == 2 else None
                    dst_tok = f"{other_table}@{other_col}"
                    src_col_idx = col_list.index(src_tok) if src_tok in col_list else 0
                    dst_col_idx = col_list.index(dst_tok) if dst_tok in col_list else 0
                    graph.add_edge(t_idx, o_idx, columns=(src_col_idx, dst_col_idx))
                    graph.add_edge(o_idx, t_idx, columns=(dst_col_idx, src_col_idx))

    return graph, tables, col_list


def _post_processing_sql(
    pred_sql: str,
    graph,
    tables: List[str],
    col_list: List[str],
) -> str:
    """Port of step3_evaluate.post_processing_sql().

    Infers missing JOINs via FK graph shortest-path, then returns SQL.
    The @ separator is preserved here; caller does final @ → . replacement.
    """
    if not _HAS_NX or graph is None:
        return pred_sql

    p_sql = re.sub(r'(=)(\S+)', r'\1 \2', pred_sql)
    p_sql = p_sql.split()

    # Find all table IDs referenced by table@col tokens
    all_from_table_ids: set = set()
    from_idx = where_idx = group_idx = order_idx = -1

    for idx, token in enumerate(p_sql):
        tok_clean = token.strip("(),")
        if "@" in tok_clean and tok_clean in col_list:
            t_name = tok_clean.split("@")[0]
            if t_name in tables:
                all_from_table_ids.add(tables.index(t_name))
        if token.lower() == "from" and from_idx == -1:
            from_idx = idx
        if token.lower() == "where" and where_idx == -1:
            where_idx = idx
        if token.lower() == "group" and group_idx == -1:
            group_idx = idx
        if token.lower() == "order" and order_idx == -1:
            order_idx = idx

    # Don't process nested SQL or single-table queries
    select_count = sum(1 for t in p_sql if t.lower() == "select")
    if select_count > 1 or len(all_from_table_ids) == 0:
        return " ".join(p_sql)

    covered_tables: set = set()
    candidate_table_ids = sorted(all_from_table_ids)
    start_table_id = candidate_table_ids[0]
    all_conds: List = []

    for table_id in candidate_table_ids[1:]:
        if table_id in covered_tables:
            continue
        try:
            path = nx.shortest_path(graph, source=start_table_id, target=table_id)
        except (nx.NetworkXNoPath, nx.NodeNotFound, Exception):
            covered_tables.add(table_id)
            continue

        for src_tid, dst_tid in zip(path, path[1:]):
            if dst_tid in covered_tables:
                continue
            covered_tables.add(dst_tid)
            all_from_table_ids.add(dst_tid)
            edge_data = graph.get_edge_data(src_tid, dst_tid)
            if edge_data and "columns" in edge_data:
                c1_idx, c2_idx = edge_data["columns"]
                c1 = col_list[c1_idx] if c1_idx < len(col_list) else "*"
                c2 = col_list[c2_idx] if c2_idx < len(col_list) else "*"
                all_conds.append((c1, c2))
            else:
                all_conds.append(("*", "*"))

    all_from_table_ids_list = list(all_from_table_ids)

    try:
        tokens = ["from", tables[all_from_table_ids_list[0]]]
        for i, table_id in enumerate(all_from_table_ids_list[1:]):
            tokens += ["join", tables[table_id]]
            if i < len(all_conds):
                tokens += ["on", all_conds[i][0], "=", all_conds[i][1]]
    except Exception as e:
        logger.warning(f"[UNISARBooksqlSelector] JOIN inference failed: {e}")
        return " ".join(p_sql)

    if from_idx == -1:
        return " ".join(p_sql)

    if where_idx != -1:
        p_sql = p_sql[:from_idx] + tokens + p_sql[where_idx:]
    elif group_idx != -1:
        p_sql = p_sql[:from_idx] + tokens + p_sql[group_idx:]
    elif order_idx != -1:
        p_sql = p_sql[:from_idx] + tokens + p_sql[order_idx:]
    else:
        p_sql = p_sql[:from_idx] + tokens

    return " ".join(p_sql)


@BaseSelector.register_actor
class UNISARBooksqlSelector(BaseSelector):
    """UNISAR BookSQL Selector.

    Rule-based FK-graph JOIN inference + @ → . conversion.
    Ports post_processing_sql() from step3_evaluate.py.

    Input: pred_sql in table@column notation
    Output: standard SQL with . separator and inferred JOINs
    """

    NAME = "UNISARBooksqlSelector"

    SKILL = """# UNISARBooksqlSelector

Rule-based post-processing selector for UNISAR on BookSQL.

Steps:
1. Load pred_sql from dataset (table@column notation)
2. Build FK graph from schema
3. Run FK-graph shortest-path JOIN inference
4. Replace @ with . in all tokens
5. Save and return final SQL

No LLM calls — pure rule-based logic.
"""

    def __init__(
        self,
        dataset: Dataset = None,
        llm: Any = None,
        is_save: bool = True,
        save_dir: Union[str, PathLike] = "../files/pred_sql",
        **kwargs
    ):
        super().__init__(dataset, llm, is_save, save_dir, **kwargs)

    def act(
        self,
        item,
        schema: Union[str, PathLike, Dict, List] = None,
        schema_links: Union[str, List[str]] = None,
        pred_sql: Union[str, PathLike, List[str]] = None,
        data_logger=None,
        **kwargs
    ) -> str:
        if data_logger:
            data_logger.info(f"{self.NAME}.act start | item={item}")

        row = self.dataset[item]
        instance_id = row.get("instance_id", str(item))

        # Load pred_sql
        sql_list = self.load_pred_sql(pred_sql, item)
        if not sql_list:
            logger.warning(f"[{self.NAME}] No pred_sql for item {item}")
            return ""

        # Use first candidate
        raw_sql = sql_list[0] if isinstance(sql_list, list) else sql_list
        if not raw_sql:
            raw_sql = "SELECT"

        # Load schema for FK graph (schema kwarg carries reducer output, not db schema)
        schema_items = None
        if self.dataset:
            try:
                schema_items = self.dataset.get_db_schema(item)
            except Exception:
                schema_items = None

        # Normalize
        if isinstance(schema_items, dict):
            from core.data_manage import single_central_process
            schema_list = single_central_process(schema_items)
        elif isinstance(schema_items, list):
            schema_list = schema_items
        else:
            schema_list = []

        # Build FK graph
        graph, tables, col_list = _build_fk_graph(schema_list)

        # Apply FK-graph JOIN inference
        try:
            processed_sql = _post_processing_sql(raw_sql, graph, tables, col_list)
        except Exception as e:
            logger.warning(f"[{self.NAME}] post_processing_sql failed for item {item}: {e}")
            processed_sql = raw_sql

        # Replace @ with . (final output uses standard dot notation)
        final_sql = processed_sql.replace("@", ".")

        # Collapse extra spaces
        while "  " in final_sql:
            final_sql = final_sql.replace("  ", " ")
        final_sql = final_sql.strip()

        if data_logger:
            data_logger.info(f"{self.NAME}.final_sql | {final_sql[:200]}")

        result = self.save_result(final_sql, item, instance_id)

        if data_logger:
            data_logger.info(f"{self.NAME}.act end | item={item}")

        return result

"""FINSQLReducer — source-style input_sequence builder for BULL/FinSQL."""
import re
from pathlib import Path
from typing import Any, Dict, List, Set

from core.actor.reducer.BaseReduce import BaseReducer
from core.data_manage import save_dataset


@BaseReducer.register_actor
class FINSQLReducer(BaseReducer):
    NAME = "FINSQLReducer"
    STOPWORDS = {
        "a", "an", "and", "are", "as", "by", "for", "from", "in", "is",
        "of", "on", "or", "the", "to", "with",
    }
    FINANCIAL_ABBREVIATIONS = {
        "abbr": {"abbreviation", "abbreviated", "short", "name"},
        "accu": {"accumulated", "cumulative"},
        "amount": {"amount", "number"},
        "asset": {"asset", "assets"},
        "avg": {"average"},
        "bench": {"benchmark"},
        "bond": {"bond", "bonds"},
        "bonds": {"bond", "bonds"},
        "chi": {"chinese", "company", "fund"},
        "company": {"company", "companies"},
        "concept": {"concept"},
        "edu": {"education", "educational"},
        "exg": {"exchange", "industry"},
        "exec": {"executive", "executives"},
        "expense": {"expense", "expenses", "cost", "costs"},
        "fin": {"financial", "finance"},
        "fp": {"freeze", "frozen", "pledge", "pledged"},
        "gr": {"growth", "rate"},
        "holder": {"holder", "shareholder"},
        "holding": {"holding", "holdings"},
        "holdings": {"holding", "holdings"},
        "industry": {"industry"},
        "info": {"information", "info"},
        "int": {"intangible", "research", "development"},
        "invest": {"investment", "invest"},
        "largesh": {"largest", "large", "shareholder", "shareholders"},
        "manager": {"manager", "managers"},
        "nv": {"net", "value"},
        "pct": {"percentage", "proportion", "ratio"},
        "perf": {"performance"},
        "portfolio": {"portfolio", "holding", "holdings"},
        "portifolio": {"portfolio", "holding", "holdings"},
        "qdii": {"qdii"},
        "rd": {"research", "development"},
        "ret": {"return", "returns"},
        "scale": {"scale", "size"},
        "secu": {"security", "securities", "stock", "fund"},
        "sh": {"shareholder", "shareholders", "share"},
        "share": {"share", "shares", "stock"},
        "shares": {"share", "shares", "stock"},
        "stock": {"stock", "company", "companies"},
        "sub": {"subscription", "subscribe", "rights", "issue", "issues"},
        "subscription": {"subscription", "rights", "issue", "issues"},
        "trustee": {"trustee", "pledge", "pledged"},
        "value": {"value"},
    }
    TABLE_HINTS = {
        "mf_fundarchives": {"fund", "funds", "investment", "direction", "orientation", "operation", "mode", "archive"},
        "mf_fundmanagernew": {"fund", "funds", "manager", "managers", "managed"},
        "mf_personalinfo": {"education", "educational", "degree", "undergraduate", "personal", "manager", "managers"},
        "mf_fmscaleanalysisn": {"scale", "qdii", "manager", "managers", "fund", "funds"},
        "mf_bondportifoliodetail": {"bond", "bonds", "holding", "holdings", "portfolio"},
        "mf_benchmarkgrowthrate": {"benchmark", "growth", "rate", "week", "month", "year"},
        "mf_fundreturnrank": {"return", "returns", "rank", "period", "cycle", "category"},
        "lc_executivesholdings": {"executive", "executives", "position", "positions", "holding", "holdings"},
        "lc_largeshsubscription": {"largest", "shareholder", "shareholders", "rights", "issue", "issues", "subscription"},
        "lc_sharefpsta": {"frozen", "freeze", "pledge", "pledged", "shareholder", "shares"},
        "lc_intassetsdetail": {"research", "development", "intangible", "expense", "expenses"},
        "lc_stockarchives": {"company", "companies", "listed", "province", "archive"},
        "lc_exgindustry": {"industry", "industries", "primary"},
        "lc_sharetransfer": {"transfer", "shareholding", "percentage", "proportion"},
    }

    def __init__(
        self,
        dataset=None,
        llm=None,
        is_save=True,
        save_dir="../files/instance_schemas",
        add_fk_info=True,
        topk_table_num: int = 3,
        topk_column_num: int = 7,
        use_chinese: bool = False,
        **kwargs,
    ):
        self.dataset = dataset
        self.llm = llm
        self.is_save = is_save
        self.save_dir = save_dir
        self.add_fk_info = add_fk_info
        self.topk_table_num = max(1, int(topk_table_num))
        self.topk_column_num = max(1, int(topk_column_num))
        self.use_chinese = use_chinese

    @staticmethod
    def _table_name(item: Dict[str, Any]) -> str:
        return item.get("table_name_original") or item.get("table_name") or ""

    @staticmethod
    def _column_name(item: Dict[str, Any]) -> str:
        return item.get("column_name_original") or item.get("column_name") or ""

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
                singular = token[:-1]
                if singular not in cls.STOPWORDS:
                    tokens.add(singular)
        return tokens

    @classmethod
    def _expanded_tokens(cls, text: str) -> set[str]:
        tokens = cls._tokens(text)
        expanded = set(tokens)
        for token in tokens:
            expanded.update(cls.FINANCIAL_ABBREVIATIONS.get(token, set()))
        return expanded

    @staticmethod
    def _prob(item: Dict[str, Any], keys: List[str]) -> float | None:
        for key in keys:
            value = item.get(key)
            if isinstance(value, (int, float)):
                return float(value)
        return None

    def _lexical_score(self, question_tokens: set[str], *parts: str) -> float:
        tokens = set()
        for part in parts:
            tokens.update(self._tokens(part))
        score = len(tokens & question_tokens)
        compact_parts = re.sub(r"[^A-Za-z0-9]+", "", " ".join(str(part) for part in parts)).lower()
        for question_token in question_tokens:
            if len(question_token) > 3 and question_token in compact_parts:
                score += 0.35
        return score

    def _table_tokens(self, table: str, rows: List[Dict[str, Any]]) -> Set[str]:
        tokens = self._expanded_tokens(table)
        tokens.update(self.TABLE_HINTS.get(table.lower(), set()))
        return tokens

    @staticmethod
    def _foreign_key_tables(row: Dict[str, Any]) -> Set[str]:
        related = set()
        fk = row.get("foreign_key") or ""
        if not isinstance(fk, str):
            return related
        for table, _column in re.findall(r"\[([A-Za-z_][\w]*)\(([^)]*)\)\]", fk):
            related.add(table)
        return related

    def _rank_tables(self, grouped: Dict[str, List[Dict[str, Any]]], question: str) -> List[str]:
        question_tokens = self._tokens(question)
        scored = []
        table_token_cache = {
            table: self._table_tokens(table, rows)
            for table, rows in grouped.items()
        }
        for order, (table, rows) in enumerate(grouped.items()):
            probs = [
                self._prob(row, ["table_pred_prob", "table_pred_probs", "table_score", "table_prob"])
                for row in rows
            ]
            probs = [prob for prob in probs if prob is not None]
            if probs:
                score = max(probs)
            else:
                table_score = self._lexical_score(question_tokens, table) * 2.0
                table_score += 1.2 * len(self.TABLE_HINTS.get(table.lower(), set()) & question_tokens)
                column_scores = [
                    self._lexical_score(
                        question_tokens,
                        self._column_name(row),
                        row.get("column_descriptions", ""),
                    )
                    for row in rows
                ]
                column_scores.sort(reverse=True)
                score = table_score
                if column_scores:
                    score += column_scores[0]
                    score += 0.25 * sum(column_scores[1:3])
            scored.append((score, order, table))
        scored.sort(key=lambda item: (-item[0], item[1]))
        ranked = [table for _, _, table in scored]
        primary_count = self.topk_table_num if self.topk_table_num <= 3 else self.topk_table_num - 2
        selected = ranked[:primary_count]
        selected_set = set(selected)

        if len(selected) < self.topk_table_num:
            related_candidates = []
            selected_order = {table: order for order, table in enumerate(ranked)}
            for table in selected:
                for row in grouped.get(table, []):
                    for related_table in self._foreign_key_tables(row):
                        if related_table not in grouped or related_table in selected_set:
                            continue
                        related_score = len(table_token_cache.get(related_table, set()) & question_tokens)
                        related_score += 0.2 * max(0, primary_count - selected_order.get(table, primary_count))
                        related_candidates.append((related_score, selected_order.get(related_table, len(ranked)), related_table))
            related_candidates.sort(key=lambda item: (-item[0], item[1]))

            for score, _order, related_table in related_candidates:
                if score <= 0:
                    continue
                if related_table in selected_set:
                    continue
                selected.append(related_table)
                selected_set.add(related_table)
                if len(selected) >= self.topk_table_num:
                    break

            for table in ranked:
                if len(selected) >= self.topk_table_num:
                    break
                if table in selected_set:
                    continue
                selected.append(table)
                selected_set.add(table)
        return selected[:self.topk_table_num]

    def _rank_columns(self, rows: List[Dict[str, Any]], question: str) -> List[Dict[str, Any]]:
        question_tokens = self._tokens(question)
        scored = []
        for order, row in enumerate(rows):
            score = self._prob(row, ["column_pred_prob", "column_pred_probs", "column_score", "column_prob"])
            if score is None:
                score = self._lexical_score(
                    question_tokens,
                    self._column_name(row),
                    row.get("column_name", ""),
                    row.get("column_descriptions", ""),
                )
            scored.append((score, order, row))
        scored.sort(key=lambda item: (-item[0], item[1]))
        return [row for _, _, row in scored[:self.topk_column_num]]

    def act(self, item, schema=None, data_logger=None, **kwargs):
        row = self.dataset[item]
        question = row["question"]
        schema_items = schema or self.dataset.get_db_schema(item)
        if schema_items is None:
            raise ValueError(f"No schema for item {item}")
        if isinstance(schema_items, dict):
            from core.data_manage import single_central_process
            schema_items = single_central_process(schema_items)

        grouped: Dict[str, List[Dict[str, Any]]] = {}
        for schema_item in schema_items:
            if not isinstance(schema_item, dict):
                continue
            table = self._table_name(schema_item)
            column = self._column_name(schema_item)
            if table and column:
                grouped.setdefault(table, []).append(schema_item)

        selected_tables = self._rank_tables(grouped, question)
        tc_original: List[str] = []
        instance_schemas: List[Dict[str, Any]] = []
        schema_tables: List[Dict[str, Any]] = []
        schema_sequence = ""

        for table in selected_tables:
            selected_columns = self._rank_columns(grouped[table], question)
            columns = [self._column_name(col) for col in selected_columns if self._column_name(col)]
            if not columns:
                continue
            schema_sequence += " | " + table + " : "
            schema_sequence += " , ".join(f"{table}.{column}" for column in columns)
            tc_original.append(f"{table}.*")
            tc_original.extend(f"{table}.{column}" for column in columns)
            schema_tables.append({
                "table_name_original": table,
                "column_names_original": columns,
            })
            for column in columns:
                instance_schemas.append({
                    "table_name": table,
                    "column_name": column,
                    "table_name_original": table,
                    "column_name_original": column,
                })

        if self.add_fk_info:
            for fk in (row.get("fk") or row.get("foreign_keys") or []):
                if not isinstance(fk, dict):
                    continue
                src_t = fk.get("source_table_name_original", "")
                src_c = fk.get("source_column_name_original", "")
                tgt_t = fk.get("target_table_name_original", "")
                tgt_c = fk.get("target_column_name_original", "")
                if src_t in selected_tables and tgt_t in selected_tables and src_c and tgt_c:
                    schema_sequence += f" | {src_t}.{src_c} = {tgt_t}.{tgt_c}"

        result = {
            "input_sequence": question + schema_sequence,
            "tc_original": tc_original,
            "schema_tables": schema_tables,
            "instance_schemas": instance_schemas,
        }

        if self.is_save:
            instance_id = row.get("instance_id", str(item))
            save_path = Path(self.save_dir)
            if self.dataset.dataset_index:
                save_path = save_path / str(self.dataset.dataset_index)
            save_path.mkdir(parents=True, exist_ok=True)
            save_path = save_path / f"{self.NAME}_{instance_id}.json"
            save_dataset(result, new_data_source=save_path)
            self.dataset.setitem(item, "instance_schemas", str(save_path))
        else:
            self.dataset.setitem(item, "instance_schemas", result)

        if data_logger:
            data_logger.info(f"{self.NAME}.act end | item={item} | seq_len={len(result['input_sequence'])}")
        return result

"""基于 sqlglot 的 SQL 结构特征解析器。

参考: NL2SQL360 src/nl2sql360/parser/sql_parser.py
"""

from __future__ import annotations

from typing import Dict, List, Optional, Tuple

import sqlglot
from sqlglot import exp


class SQLFeatureExtractor:
    """用 sqlglot 提取 SQL 的 16 维结构特征 + 难度分级。

    每个特征是一个计数（整数），-1 表示 SQL 无法解析。
    """

    _SET_KEYWORDS = (exp.Union, exp.Except, exp.Intersect)
    _SCALAR_KEYWORDS = (
        exp.Abs, exp.Length, exp.Cast, exp.Round,
        exp.Upper, exp.Lower, exp.Rand,
    )
    _SCALAR_ANONYMOUS = ("STRFTIME", "JULIADAY", "NOW", "INSTR", "SUBSTR")
    _MATH_KEYWORDS = (exp.Add, exp.Sub, exp.Mul, exp.Div, exp.Mod)
    _LOGICAL_KEYWORDS = (exp.And, exp.Or)
    _CONTROL_FLOW = (exp.Case,)
    _CONTROL_FLOW_ANONYMOUS = ("IIF",)

    FEATURES: Tuple[str, ...] = (
        "query_fields",      # SELECT 列数
        "group_by",          # GROUP BY 子句数
        "order_by",          # ORDER BY 子句数
        "limit",             # LIMIT 子句数
        "join",              # JOIN 数
        "predicate",         # WHERE 条件数
        "aggregation",       # 聚合函数数 (COUNT, SUM, AVG, MAX, MIN)
        "scalar_function",   # 标量函数数 (ABS, LENGTH, CAST, ROUND, ...)
        "subquery",          # 子查询数
        "set_operation",     # UNION/INTERSECT/EXCEPT 数
        "math_compute",      # 算术运算数 (+ - * / %)
        "logical_connector", # AND/OR 数
        "distinct",          # DISTINCT 数
        "like",              # LIKE 数
        "control_flow",      # CASE/IIF 数
        "window",            # 窗口函数数
    )

    # ---- 基于 select clause 结构提取的 7 个 SQL 组件，用于 EM / CF1 对比 ----
    COMPONENTS = (
        "select",    # SELECT 列集合
        "where",     # WHERE 条件
        "group",     # GROUP BY / HAVING
        "order",     # ORDER BY / LIMIT
        "join",      # FROM tables / JOIN
        "iuen",      # INTERSECT/UNION/EXCEPT/NESTED 子查询
        "keywords",  # DISTINCT / LIKE / BETWEEN / IN / EXISTS 等
    )

    def __init__(self, sql: str, dialect: str = "sqlite"):
        self.sql = (sql or "").strip()
        self.dialect = dialect
        self.ast: Optional[exp.Expression] = None
        self.valid: bool = False
        self._try_parse()

    # ------------------------------------------------------------------
    # 16 维特征
    # ------------------------------------------------------------------

    def _try_parse(self):
        if not self.sql:
            return
        try:
            self.ast = sqlglot.parse_one(self.sql, dialect=self.dialect, error_level=sqlglot.ErrorLevel.IGNORE)
            self.valid = self.ast is not None
        except Exception:
            self.ast = None
            self.valid = False

    def extract(self) -> Dict[str, int]:
        """提取全部 16 维特征 → dict。解析失败时全部返回 -1。"""
        if not self.valid or self.ast is None:
            return {f: -1 for f in self.FEATURES}
        return {
            "query_fields":      self._count_query_fields(),
            "group_by":          self._count(exp.Group),
            "order_by":          self._count(exp.Order),
            "limit":             self._count(exp.Limit),
            "join":              self._count(exp.Join),
            "predicate":         self._count(exp.Predicate),
            "aggregation":       self._count(exp.AggFunc),
            "scalar_function":   self._count_scalar(),
            "subquery":          self._count(exp.Subquery),
            "set_operation":     self._count(self._SET_KEYWORDS),
            "math_compute":      self._count(self._MATH_KEYWORDS),
            "logical_connector": self._count(self._LOGICAL_KEYWORDS),
            "distinct":          self._count(exp.Distinct),
            "like":              self._count(exp.Like),
            "control_flow":      self._count_control_flow(),
            "window":            self._count(exp.Window),
        }

    @staticmethod
    def compute_delta(gold_features: Dict[str, int],
                      pred_features: Dict[str, int]) -> Dict[str, int]:
        """pred - gold。正值 = pred 多了，负值 = pred 少了。"""
        return {f: pred_features.get(f, 0) - gold_features.get(f, 0)
                for f in SQLFeatureExtractor.FEATURES}

    def classify_hardness(self) -> str:
        """基于 MT-Teql 的自动难度分级：easy / medium / hard / extra。"""
        f = self.extract()
        comp1 = (int(f["predicate"] > 0) + int(f["group_by"] > 0) +
                 int(f["order_by"] > 0) + int(f["limit"] > 0) +
                 int(f["join"] > 0) + int(f["logical_connector"] > 0) +
                 int(f["like"] > 0))
        comp2 = f["subquery"] + f["set_operation"]
        others = (int(f["aggregation"] > 1) + int(f["query_fields"] > 1) +
                  int(f["predicate"] > 1) + int(f["group_by"] > 1))

        if comp1 <= 2 and comp2 == 0:
            return "easy"
        elif (comp1 <= 2 and others < 2) or (comp1 <= 1 and others <= 2):
            return "medium"
        elif comp1 <= 3 or comp2 <= 1:
            return "hard"
        else:
            return "extra"

    # ------------------------------------------------------------------
    # 7 组件解析 (用于 EM / CF1)
    # ------------------------------------------------------------------

    def parse_components(self) -> Optional[Dict[str, set]]:
        """将 SQL 解析为 7 个组件的元素集合。

        返回 None 表示 SQL 无法解析。
        各 component 的集合内容:
          - select:   {col_name, ...}          — SELECT 表达式中的列名/别名
          - where:    {condition_repr, ...}    — WHERE 子句中各条件的字符串表示
          - group:    {col_name, ...}          — GROUP BY 列 + HAVING 条件
          - order:    {col_name, ...} ∪ {"LIMIT"}  — ORDER BY 列 + limit 标记
          - join:     {table_name, ...}        — FROM / JOIN 的表名
          - iuen:     {subquery_repr, ...}      — 子查询 / UNION / INTERSECT / EXCEPT
          - keywords: {keyword, ...}            — DISTINCT / LIKE / BETWEEN / IN / EXISTS / IS NULL
        """
        if not self.valid or self.ast is None:
            return None

        comps: Dict[str, set] = {c: set() for c in self.COMPONENTS}

        # collect top-level SELECT nodes (exclude subquery-nested ones)
        top_selects = self._top_level_selects()

        # select — 只取最外层 SELECT 的列表达式（忽略子查询内的 SELECT）
        for node in top_selects:
            for expr in node.expressions:
                name = self._col_name(expr)
                if name and name != "*":
                    comps["select"].add(name)

        # join — FROM 表名 + JOIN 表名
        for node in self.ast.find_all(exp.From):
            if not self._inside_subquery(node):
                comps["join"].add(self._table_name(node.this))
        for node in self.ast.find_all(exp.Join):
            if not self._inside_subquery(node):
                comps["join"].add(self._table_name(node.this))

        # where — WHERE/HAVING/ON 条件 (拆开 AND)
        for pred_node in self.ast.find_all(exp.Where, exp.Having):
            if not self._inside_subquery(pred_node):
                for cond in self._flatten_and(pred_node.this):
                    rep = self._condition_repr(cond)
                    if rep:
                        comps["where"].add(rep)
        # ON 条件也归入 where 组件（JOIN 的 ON 不受 subquery 影响，JOIN 本身已限制）
        for join_node in self.ast.find_all(exp.Join):
            if not self._inside_subquery(join_node):
                if join_node.args.get("on"):
                    for cond in self._flatten_and(join_node.args["on"]):
                        rep = self._condition_repr(cond)
                        if rep:
                            comps["where"].add(rep)

        # group — GROUP BY 列 + HAVING 条件
        for node in self.ast.find_all(exp.Group):
            if not self._inside_subquery(node):
                for expr in node.expressions:
                    name = self._col_name(expr)
                    if name:
                        comps["group"].add(name)
        for node in self.ast.find_all(exp.Having):
            if not self._inside_subquery(node):
                comps["group"].add(f"HAVING:{self._condition_repr(node.this)}")

        # order — ORDER BY 列（Ordered 节点，不是 Order）
        for node in self.ast.find_all(exp.Ordered):
            if not self._inside_subquery(node):
                name = self._col_name(node.this)
                if name:
                    comps["order"].add(name)
        # LIMIT
        if list(self.ast.find_all(exp.Limit)):
            comps["order"].add("__LIMIT__")

        # iuen — 子查询 + 集合操作
        subquery_count = 0
        for node in self.ast.find_all(exp.Subquery):
            subquery_count += 1
            comps["iuen"].add(self._subquery_repr(node))
        # 如果没有任何子查询/集合操作，iuen 为空（两者 gold/pred 都空 → 匹配）
        for node in self.ast.find_all(exp.Union, exp.Intersect, exp.Except):
            comps["iuen"].add(f"SETOP:{type(node).__name__}")

        # keywords — 只从顶层提取
        kw_map = [
            (exp.Distinct, "DISTINCT"),
            (exp.Like, "LIKE"),
            (exp.Between, "BETWEEN"),
            (exp.In, "IN"),
            (exp.Is, "IS"),
            (exp.Exists, "EXISTS"),
            (exp.Any, "ANY"),
            (exp.All, "ALL"),
        ]
        for cls, label in kw_map:
            found = False
            for node in self.ast.find_all(cls):
                if not self._inside_subquery(node):
                    found = True
                    break
            if found:
                comps["keywords"].add(label)

        # IS NULL 特殊处理
        for node in self.ast.find_all(exp.Is):
            if not self._inside_subquery(node):
                comps["keywords"].add("IS")

        return comps

    # ------------------------------------------------------------------
    # 子查询上下文判断
    # ------------------------------------------------------------------

    def _inside_subquery(self, node) -> bool:
        """判断节点是否在子查询内部（非顶层）。"""
        parent = node.parent
        while parent is not None:
            if isinstance(parent, exp.Subquery):
                return True
            parent = parent.parent
        return False

    def _top_level_selects(self) -> list:
        """获取所有非子查询嵌套的顶层 SELECT 节点。"""
        result = []
        for node in self.ast.find_all(exp.Select):
            if not self._inside_subquery(node):
                result.append(node)
        return result

    # ------------------------------------------------------------------
    # 内部辅助
    # ------------------------------------------------------------------

    def _count(self, expression_types) -> int:
        return len(list(self.ast.find_all(expression_types)))

    def _count_query_fields(self) -> int:
        ast = self.ast
        # 跳过最外层 SET 操作
        if isinstance(ast, self._SET_KEYWORDS):
            ast = ast.this
        if isinstance(ast, exp.Select):
            return len(ast.expressions)
        return 0

    def _count_scalar(self) -> int:
        n = self._count(self._SCALAR_KEYWORDS)
        for node in self.ast.find_all(exp.Anonymous):
            if node.this.upper() in self._SCALAR_ANONYMOUS:
                n += 1
        return n

    def _count_control_flow(self) -> int:
        n = self._count(self._CONTROL_FLOW)
        for node in self.ast.find_all(exp.Anonymous):
            if node.this.upper() in self._CONTROL_FLOW_ANONYMOUS:
                n += 1
        return n

    # ---- 组件辅助 ----

    @staticmethod
    def _col_name(expr) -> Optional[str]:
        """从表达式中提取列名（忽略字面量和复杂表达式）。"""
        if isinstance(expr, exp.Column):
            return expr.name.lower()
        if isinstance(expr, exp.Literal):
            return None
        # 简单别名 / 函数调用 → 返回 sql() 的小写表示（去重用）
        if isinstance(expr, (exp.Alias, exp.AggFunc, exp.Anonymous,
                             exp.Func, exp.Window)):
            return expr.sql(dialect="sqlite").lower()[:80]
        return None

    @staticmethod
    def _table_name(expr) -> str:
        """提取表名（用于 join 组件）。"""
        if isinstance(expr, exp.Table):
            return expr.name.lower()
        if isinstance(expr, exp.Subquery):
            alias = expr.alias
            return f"SUBQ:{alias}" if alias else "SUBQ:anon"
        return expr.sql(dialect="sqlite").lower()[:60]

    @staticmethod
    def _flatten_and(node) -> List[exp.Expression]:
        """把 AND 链拆成独立条件的列表。"""
        if isinstance(node, exp.And):
            return (SQLFeatureExtractor._flatten_and(node.this) +
                    SQLFeatureExtractor._flatten_and(node.args.get("expression")))
        return [node]

    @staticmethod
    def _condition_repr(node) -> Optional[str]:
        """条件节点的规范化字符串表示（保留字面量值以区分不同条件）。

        对于比较操作符 (EQ/NEQ/GT/LT/GTE/LTE)，右侧是字面量时编码值：
          例：age > 10 → "age > VAL:10"，age > 20 → "age > VAL:20"
        这样保留结构信息的同时能区分不同的具体值。
        """
        if isinstance(node, (exp.EQ, exp.NEQ, exp.GT, exp.LT,
                              exp.GTE, exp.LTE)):
            left = SQLFeatureExtractor._col_name(node.this)
            right = node.args.get("expression")
            right_is_literal = isinstance(right, exp.Literal)
            if left:
                op = {exp.EQ: "=", exp.NEQ: "!=", exp.GT: ">",
                      exp.LT: "<", exp.GTE: ">=", exp.LTE: "<="}[type(node)]
                if right_is_literal:
                    lit_val = str(right.this) if right.this is not None else "NULL"
                    return f"{left} {op} VAL:{lit_val}"
                return f"{left} {op} COL"
            return None
        if isinstance(node, exp.In):
            col = SQLFeatureExtractor._col_name(node.this)
            return f"{col} IN" if col else None
        if isinstance(node, exp.Like):
            col = SQLFeatureExtractor._col_name(node.this)
            return f"{col} LIKE" if col else None
        if isinstance(node, exp.Between):
            col = SQLFeatureExtractor._col_name(node.this)
            return f"{col} BETWEEN" if col else None
        if isinstance(node, exp.Is):
            col = SQLFeatureExtractor._col_name(node.this)
            return f"{col} IS" if col else None
        if isinstance(node, exp.Exists):
            return "EXISTS"
        # 其他情况用 sql() 表示
        return node.sql(dialect="sqlite").lower()[:60]

    @staticmethod
    def _subquery_repr(node) -> str:
        """子查询的简单表示：最外层 SELECT 的第一个词。"""
        inner = node.this
        if isinstance(inner, exp.Select):
            exprs = inner.expressions
            if exprs:
                return f"SUBQ:{SQLFeatureExtractor._col_name(exprs[0]) or '*'}"
        return "SUBQ"

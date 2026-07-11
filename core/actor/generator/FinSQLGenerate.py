"""FinSQL Generator — Template-based SQL generation for financial Text2SQL.

Uses FinSQL's 44 prompt templates (Chinese + English) with optional CoT,
skeleton-first generation, and temperature sampling for diversity.

Replaces the LoRA fine-tuned LLM with Squrve's native LLM provider API.
"""

from typing import Union, Dict, List, Optional
from os import PathLike
from pathlib import Path
import random
import time
import re

from loguru import logger

from core.actor.generator.BaseGenerate import BaseGenerator
from core.data_manage import Dataset, single_central_process, save_dataset
from core.utils import load_dataset, sql_clean


# ============================================================================
# Prompt Templates — from FinSQL Hybrid_Data_Augmentation/configures/templates.json
# ============================================================================

# ---- English instruction templates ----
INSTRUCTION_EN_1 = """Providing you with the database schema information and a question, performing the following tasks:
1 - Output the SQL query statement corresponding to this question.

Notes:
1 - When generating the SQL, only the relevant parts corresponding to the question need to be included, without additional output of tables and columns.
2 - Directly output the final SQL in the following format:
Generated SQL:
```
{{sql}}
```

###
Schema:
{schema}
Foreign keys:
{fks}

Question:
{question}
###

"""

INSTRUCTION_EN_2 = """I have a question for you. I need you to write the corresponding SQL query for this question. To make it easier for you to compose the SQL, I will provide you with the database schema information. Please provide the SQL in the following format:
Generated SQL:
```
{{sql}}
```

###
Schema:
{schema}
Foreign keys:
{fks}

Question:
{question}
###

"""

INSTRUCTION_EN_3 = """Given the provided database schema information and a question, please write the corresponding SQL query statement for the question.

"Question":
{question}
"Table Information":
{schema}
"Foreign Keys":
{fks}

Please output the final SQL in the following format without any explanations:
Generated SQL:
```
{{sql}}
```
"""

# ---- Chinese instruction templates ----
INSTRUCTION_ZH_1 = """给你数据库Schema信息以及一个问题，执行以下任务：
1 - 输出这条问题对应的SQL查询语句。

注意：
1 - 在生成SQL的时候只需要输出问题中对应的部分，不要额外输出表和列。
2 - 请以如下形式直接输出最终SQL:
生成的SQL：
```
{{sql}}
```

###
Schema:
{schema}
Foreign keys:
{fks}

Question:
{question}
###

"""

INSTRUCTION_ZH_2 = """给你一个问题，你需要写出该问题对应的SQL，为了方便你撰写SQL，我将会提供数据库Schema信息。
请在最后直接如下格式输出最终的SQL：
生成的SQL：
```
{{sql}}
```


###
Schema:
{schema}
Foreign keys:
{fks}

Question:
{question}
###

"""

INSTRUCTION_ZH_3 = """给定以下数据库Schema信息和一个问题，请为该问题编写相应的SQL查询语句。

"问题":
{question}
"表信息":
{schema}
"外键":
{fks}

请用下面的格式输出最终SQL:
生成的SQL：
```
{{sql}}
```
"""

# ---- English CoT templates ----
COT_EN_1 = """Providing you with the database schema information and a question, performing the following tasks:
1 - Output the SQL query statement corresponding to this question.

Notes:
1 - When generating the SQL, only the relevant parts corresponding to the question need to be included, without additional output of tables and columns.
2 - You should first present your intermediate thought process, and then provide the final SQL in the following format:
Generated SQL:
```
{{sql}}
```

###
Schema:
{schema}
Foreign keys:
{fks}

Question:
{question}
###

"""

COT_EN_2 = """I have a question for you. I need you to write the corresponding SQL query for this question. To make it easier for you to compose the SQL, I will provide you with the database schema information. Please start by outlining your thought process, and finally, provide the SQL in the following format:
Generated SQL:
```
{{sql}}
```

###
Schema:
{schema}
Foreign keys:
{fks}

Question:
{question}
###

"""

COT_EN_3 = """Given the provided database schema information and a question, please write the corresponding SQL query statement for the question.

"Question":
{question}
"Table Information":
{schema}
"Foreign Keys":
{fks}

Please start by outlining your thought process, and then output the final SQL in the following format:
Generated SQL:
```
{{sql}}
```
"""

# ---- Chinese CoT templates ----
COT_ZH_1 = """给你数据库Schema信息以及一个问题，执行以下任务：
1 - 输出这条问题对应的SQL查询语句。

注意：
1 - 在生成SQL的时候只需要输出问题中对应的部分，不要额外输出表和列。
2 - 你需要先输出你的中间思考过程，再以如下形式输出最终SQL:
生成的SQL：
```
{{sql}}
```

###
Schema:
{schema}
Foreign keys:
{fks}

Question:
{question}
###

"""

COT_ZH_2 = """给你一个问题，你需要写出该问题对应的SQL，为了方便你撰写SQL，我将会提供数据库Schema信息。
请先写出你的思考过程，最后直接如下格式输出最终的SQL：
生成的SQL：
```
{{sql}}
```


###
Schema:
{schema}
Foreign keys:
{fks}

Question:
{question}
###

"""

COT_ZH_3 = """给定以下数据库Schema信息和一个问题，请为该问题编写相应的SQL查询语句。

"问题":
{question}
"表信息":
{schema}
"外键":
{fks}

请先写出你的思考过程，然后用下面的格式输出最终SQL:
生成的SQL：
```
{{sql}}
```
"""

# ---- English skeleton templates ----
SKELETON_EN_1 = """Here is the database schema information and a question for you to perform the following tasks:
1. Output the skeleton of the SQL statement corresponding to this question.
2. Output the SQL query statement corresponding to this question.

Note:
1. When generating the SQL, only the relevant parts from the question need to be included. Do not provide additional information about tables and columns.
2. Please provide the final SQL output in the following format: .

Generated SQL skeleton：
```
{{sql skeleton}}
```
Generated SQL：
```
{{sql}}
```

###
Schema:
{schema}
Foreign keys:
{fks}

Question:
{question}
###

"""

SKELETON_EN_2 = """Given you a question, you need to write the corresponding SQL. To facilitate you in composing the SQL, I will provide the database schema information. Please provide the SQL skeleton and the final SQL in the following format at the end:
Generated SQL skeleton:
```
{{sql skeleton}}
```
Generated SQL:
```
{{sql}}
```


###
Schema:
{schema}
Foreign keys:
{fks}

Question:
{question}
###

"""

SKELETON_EN_3 = """Given the following database schema information and a question, please write the corresponding SQL query statement for the question.

"Question":
{question}
"Table information":
{schema}
"Foreign keys":
{fks}

Please output the SQL skeleton and the final SQL in the following format:
Generated SQL skeleton:
```
{{sql skeleton}}
```
Generated SQL:
```
{{sql}}
```
"""

# ---- Chinese skeleton templates ----
SKELETON_ZH_1 = """给你数据库Schema信息以及一个问题，执行以下任务：
1 - 输出这个问题对应的SQL查询的骨架
2 - 输出这条问题对应的SQL查询语句。

注意：
1 - 在生成SQL的时候只需要输出问题中对应的部分，不要额外输出表和列。
2 - 你需要以如下形式输出最终SQL骨架和SQL:
生成的SQL骨架:
```
{{sql skeleton}}
生成的SQL：
```
{{sql}}
```

###
Schema:
{schema}
Foreign keys:
{fks}

Question:
{question}
###

"""

SKELETON_ZH_2 = """给你一个问题，你需要写出该问题对应的SQL，为了方便你撰写SQL，我将会提供数据库Schema信息。
请在最后直接如下格式输出SQL骨架和最终的SQL:
生成的SQL骨架:
```
{{sql skeleton}}
生成的SQL：
```
{{sql}}
```


###
Schema:
{schema}
Foreign keys:
{fks}

Question:
{question}
###

"""

SKELETON_ZH_3 = """给定以下数据库Schema信息和一个问题，请为该问题编写相应的SQL骨架和SQL查询语句。

"问题":
{question}
"表信息":
{schema}
"外键":
{fks}

请用下面的格式输出SQL骨架和最终SQL:
生成的SQL骨架:
```
{{sql skeleton}}
生成的SQL：
```
{{sql}}
```
"""

# ---- Financial CoT few-shot examples (from few_shot_examples.json) ----
# 8 Chinese financial CoT examples
FEWSHOT_COT_ZH = [
    """这里给你一个样例：
问题：2021年收入从大到小排名前5的是哪几家公司？
回答：
思考过程：
1. 要查询2021年的收入排名，需要使用lc_mainoperincome表。
2. 需要查询的字段是公司的中文名称，即chinameabbr字段。
3. 需要根据主营业务收入mainoperincome字段进行排序，且按降序排列。
4. 需要限制结果只显示前5个公司。
5. 需要根据enddate字段筛选出2021年的数据。

生成的SQL：
```
SELECT chinameabbr
FROM lc_mainoperincome
WHERE strftime('%Y', enddate)='2021'
ORDER BY mainoperincome DESC
LIMIT 5;
```

""",
    """这里给你一个样例：
问题：占冻结质押方持股数比重超过0.5的股东有哪些，列出股东名称和占冻结质押方持股数量比例。
回答：
思考过程：推理过程：
根据给出的Schema信息，我们可以看到占冻结质押方持股数比重是存在于lc_sharefp表中的pctofpledger字段。而我们需要找到占冻结质押方持股数比重超过0.5的股东，所以我们需要从lc_sharefp表中选取fpshname和pctofpledger这两个字段，并且加上条件pctofpledger > 0.5。

生成的SQL：
```
SELECT fpshname, pctofpledger
FROM lc_sharefp
WHERE pctofpledger > 0.5;
```

""",
    """这里给你一个样例：
问题：华夏沪港深500ETF基金的全称是什么？
回答：
推理过程：
1. 需要从哪些表中获取信息？答案：问题要查询基金的全称，因此需要使用表 mf_fundarchives。
2. 需要获取哪些列的信息？答案：问题问了基金的全称，因此需要使用列 chiname。
3. 需要加入哪些条件来筛选符合要求的行？答案：列 secuabbr='华夏沪港深500ETF'。
4. 需要连接哪些表来获取所有必要的信息？答案：不需要连接其他表。

根据以上思考过程，生成的SQL查询语句如下：

生成的SQL：
```
SELECT chiname FROM mf_fundarchives WHERE secuabbr='华夏沪港深500ETF';
```

""",
    """这里给你一个样例：
问题：找下两年基金基准增长幅度大于20%的基金。
回答：推理过程：
1. 需要从 mf_benchmarkgrowthrate 表中筛选出 benchgrfor2year 大于20% 的基金。
2. 需要选取这些基金的基金简称即secuabbr。

生成的SQL：
```
SELECT secuabbr
FROM mf_benchmarkgrowthrate
WHERE benchgrfor2year > 20;
```

""",
    """这里给你一个样例：
问题：列出所有博士最高学历水平的基金经理，以及他们管理基金的数量和总规模信息。
回答：推理过程：
首先，我们需要找到所有博士最高学历水平的基金经理，可以从mf_personalinfo表中筛选出education为"博士"的记录。然后，我们需要获取这些基金经理的管理基金的数量和总规模信息，可以从mf_fmscaleanalysisn表中获取对应的数据。最后，我们需要通过连接mf_personalinfo和mf_fmscaleanalysisn表来获取博士最高学历水平的基金经理的管理基金的数量和总规模信息。

基于这些想法，我们可以使用以下SQL查询语句来解决问题：

生成的SQL：
```
select b.chinesename, b.numberoffunds, b.totalfundnv
from mf_personalinfo as a join mf_fmscaleanalysisn as b
on a.personalcode = b.personalcode
where a.education = '博士';
```

""",
    """这里给你一个样例：
问题：A股总股本超过10亿的公司有哪些，按自由流通比重从大到小排序。
回答：推理过程：
根据问题，我们需要查询A股总股本超过10亿的公司，并按照自由流通比重从大到小排序。根据数据库Schema信息，我们需要使用lc_freefloat表来查询自由流通股本信息，并根据totalashare字段过滤A股总股本超过10亿的公司，并按照adjfreefloatratio字段从大到小排序。

生成的SQL：
```
SELECT chinameabbr
FROM lc_freefloat
WHERE totalashare > 1000000000
ORDER BY adjfreefloatratio DESC
```

""",
    """这里给你一个样例：
问题：我想买000752，帮我看看这三年的销售毛利率分别是多少？
回答：推理过程：
第一步：我们需要从 lc_mainoperincome 表中获取销售毛利率，所以我们需要用到 grossprofit 列。
第二步：我们需要从 lc_mainoperincome 表中筛选出 enddate 在三年内的数据，所以我们需要用到 enddate 列和日期函数 strftime() 进行日期比较。
第三步：我们需要从 lc_mainoperincome 表中筛选出 secucode = '000752' 的数据，所以我们需要用到 secucode 列。

生成的SQL：
```
SELECT grossprofit
FROM lc_mainoperincome
WHERE strftime('%Y', enddate) > strftime('%Y', DATE('now', '-3 year'))
AND secucode ='000752';
```

""",
    """这里给你一个样例：
问题：基金经理总管理基金数目排名前十的都有谁？
回答：推理过程：
这个问题涉及到基金经理和基金经理规模统计这两个实体和属性。我们需要从mf_fmscaleanalysisn这个表中检索数据。我们可以根据totalfundnrank这一属性进行排序，然后选择排名前十的基金经理。

基于这些想法，我们可以使用以下SQL查询语句来解决问题：

生成的SQL：
```
SELECT chinesename
FROM mf_fmscaleanalysisn
ORDER BY totalfundnrank
LIMIT 10;
```

""",
]

# 8 English financial CoT examples
FEWSHOT_COT_EN = [
    """Here's an example for you:
Question: What are the top 5 companies ranked by income from highest to lowest in 2021?
Answer:
Thought process:
1. To query the income ranking for 2021, use the lc_mainoperincome table.
2. The required field is the Chinese name of the company, i.e., the chinameabbr field.
3. Sort the results based on mainoperincome field in descending order.
4. Limit the results to display only the top 5 companies.
5. Filter the data for the year 2021 based on the enddate field.

Generated SQL:
```
SELECT chinameabbr
FROM lc_mainoperincome
WHERE strftime('%Y', enddate)='2021'
ORDER BY mainoperincome DESC
LIMIT 5;
```

""",
    """Here's an example for you:
Question: Which shareholders have a shareholding ratio exceeding 0.5 in the freeze pledge, and list their names and the ratio of shares held by the freeze pledge?
Answer:
Thought process: Inference process:
Based on the provided Schema information, we can see that the shareholding ratio in the freeze pledge is in the pctofpledger field of the lc_sharefp table. We need to select fpshname and pctofpledger fields from the lc_sharefp table and add the condition pctofpledger > 0.5.

Generated SQL:
```
SELECT fpshname, pctofpledger
FROM lc_sharefp
WHERE pctofpledger > 0.5;
```

""",
    """Here's an example for you:
Question: What is the full name of the Huaxia CSI 500 ETF Fund?
Answer:
Inference process:
1. To obtain information from which tables? Answer: The question requires querying the full name of the fund, so the mf_fundarchives table needs to be used.
2. Which columns of information need to be obtained? Answer: The question asks for the full name of the fund, so the chiname column needs to be used.
3. What conditions need to be added to filter the required rows? Answer: Use the condition secuabbr='Huaxia CSI 500 ETF'.
4. Which tables need to be joined to obtain all the necessary information? Answer: No need to join other tables.

Based on the above thought process, the generated SQL query is as follows:

Generated SQL:
```
SELECT chiname FROM mf_fundarchives WHERE secuabbr='Huaxia CSI 500 ETF';
```

""",
    """Here's an example for you:
Question: Find funds with a benchmark growth rate greater than 20% for the next two years.
Answer:
Inference process:
1. Need to filter funds with benchgrfor2year greater than 20% from the mf_benchmarkgrowthrate table.
2. Need to select the fund abbreviations (secuabbr) for these funds.

Generated SQL:
```
SELECT secuabbr
FROM mf_benchmarkgrowthrate
WHERE benchgrfor2year > 20;
```

""",
    """Here's an example for you:
Question: List all fund managers with a Ph.D. as their highest education level, along with the number of funds they manage and total scale information.
Answer:
Inference process:
First, we need to find all fund managers with a Ph.D., which can be filtered from the mf_personalinfo table based on the education field being 'Ph.D.' Then, we need to get the number of funds managed and total scale information for these fund managers, which can be obtained from the mf_fmscaleanalysisn table. Finally, we need to connect the mf_personalinfo and mf_fmscaleanalysisn tables to get the required information for fund managers with a Ph.D.

Based on these ideas, we can use the following SQL query to solve the problem:

Generated SQL:
```
select b.chinesename, b.numberoffunds, b.totalfundnv
from mf_personalinfo as a join mf_fmscaleanalysisn as b
on a.personalcode = b.personalcode
where a.education = 'Ph.D.';
```

""",
    """Here's an example for you:
Question: Which companies have a total share capital in A-shares exceeding 1 billion, sorted by free float ratio from high to low?
Answer:
Inference process:
According to the question, we need to query companies with A-shares total share capital exceeding 1 billion and sort them by free float ratio from high to low. According to the database Schema information, we need to use the lc_freefloat table to query free float share capital information and filter companies with A-shares total share capital exceeding 1 billion based on the totalashare field, and then sort them by adjfreefloatratio field in descending order.

Generated SQL:
```
SELECT chinameabbr
FROM lc_freefloat
WHERE totalashare > 1000000000
ORDER BY adjfreefloatratio DESC
```

""",
    """Here's an example for you:
Question: I want to buy 000752, can you help me see the sales gross profit margin for the past three years?
Answer:
Inference process:
Step 1: We need to retrieve the sales gross profit margin from the lc_mainoperincome table, so we need to use the grossprofit column.
Step 2: We need to filter data from the lc_mainoperincome table for the last three years based on the enddate column using the strftime() date function.
Step 3: We need to filter data from the lc_mainoperincome table where secucode = '000752', so we need to use the secucode column.

Generated SQL:
```
SELECT grossprofit
FROM lc_mainoperincome
WHERE strftime('%Y', enddate) > strftime('%Y', DATE('now', '-3 year'))
AND secucode ='000752';
```

""",
    """Here's an example for you:
Question: Who are the top ten fund managers in terms of the total number of funds managed?
Answer:
Inference process:
This question involves entities and attributes related to fund managers and fund manager scale statistics. We need to retrieve data from the mf_fmscaleanalysisn table. We can sort based on the totalfundnrank attribute and then select the top ten fund managers.

Based on these ideas, we can use the following SQL query to solve the problem:

Generated SQL:
```
SELECT chinesename
FROM mf_fmscaleanalysisn
ORDER BY totalfundnrank
LIMIT 10;
```

""",
]


SQLITE_DIALECT_NOTE = (
    "Important: The database backend is SQLite. "
    "You MUST use SQLite-compatible syntax only:\n"
    "- Year/month/day: strftime('%Y', col), strftime('%m', col), strftime('%d', col)\n"
    "  Do NOT use YEAR(col), MONTH(col), DAY(col), or EXTRACT(YEAR FROM col)\n"
    "- Date arithmetic: DATE(col, '-N years'), DATE(col, '+N months'), etc.\n"
    "  Do NOT use DATE_SUB, DATE_ADD, or INTERVAL keyword\n"
    "- Current date: date('now')  — NOT NOW() or CURDATE()\n"
    "CRITICAL: Only use column names from the schema above. Do NOT invent column names.\n\n"
)


@BaseGenerator.register_actor
class FINSQLGenerator(BaseGenerator):
    """FinSQL SQL generation using template-based prompting.

    Supports:
    - 44 prompt template variants (instruction/CoT/skeleton × EN/ZH × 3 variants each)
    - Financial CoT few-shot examples
    - Temperature sampling for diversity (when generate_num > 1)
    - Skeleton-first generation mode
    - Max 5 retry attempts with graceful degradation
    """

    NAME = "FINSQLGenerator"

    SKILL = """# FINSQLGenerator

FinSQL template-based SQL generation. Uses 44 prompt variants (instruction,
CoT, skeleton) in Chinese and English. Supports temperature sampling for
multiple candidates and skeleton-first generation.

## Inputs
- `schema`: instance_schemas from Reduce stage
- `schema_links`: (unused, schema already reduced)

## Output
`pred_sql`

## Steps
1. Select prompt template variant (random or fixed).
2. Build schema text from instance_schemas.
3. Optionally insert CoT few-shot examples.
4. Call LLM with retry (max 5 attempts).
5. Extract SQL from ```...``` code fences.
6. Degrade to "SELECT" on total failure.
"""

    def __init__(
        self,
        dataset: Dataset = None,
        llm: any = None,
        is_save: bool = True,
        save_dir: Union[str, PathLike] = "../files/pred_sql",
        use_cot: bool = True,
        use_skeleton: bool = False,
        use_chinese: bool = True,
        max_attempt_times: int = 5,
        n_candidates: int = 1,
        temperature: float = None,
        **kwargs
    ):
        self.dataset = dataset
        self.llm = llm
        self.is_save = is_save
        self.save_dir = save_dir
        self.use_cot = use_cot
        self.use_skeleton = use_skeleton
        self.use_chinese = use_chinese
        self.max_attempt_times = max_attempt_times
        self.n_candidates = max(1, int(n_candidates))
        self._temperature = temperature
        self.enable_thinking = kwargs.get("enable_thinking", False)
        self.schema_format = kwargs.get("schema_format", "resdsql")  # "resdsql" or "legacy"

    # ------------------------------------------------------------------
    # Schema formatting
    # ------------------------------------------------------------------

    def _format_schema_resdsql_style(self, instance_schemas: list) -> str:
        """Format schema in RESDSQL style — aligned with FinSQL text2sql_data_generator_finsql.py.

        Format: table_original : table_original.col_original , table_original.col_original | fk...

        This is the DEFAULT format, matching what the original FinSQL model was
        trained on during Hybrid Data Augmentation.
        """
        parts = []
        for table in instance_schemas:
            if not isinstance(table, dict):
                continue
            tname = table.get("table_name_original", table.get("table_name", ""))
            if not tname:
                continue
            cols_original = table.get("column_names_original", table.get("columns", []))
            col_items = []
            for co in cols_original:
                col_items.append(f"{tname}.{co}")
            parts.append(f" | {tname} : {', '.join(col_items)}")
        return "".join(parts)

    def _format_schema_for_prompt(self, instance_schemas: list) -> str:
        """Format instance_schemas into text for the prompt.

        Uses FinSQL format: table_name(中文名): col1(中文名), col2(中文名), ...

        This is the LEGACY format, kept as an alternative.
        """
        lines = []
        for table in instance_schemas:
            if isinstance(table, dict):
                tname = table.get("table_name_original", table.get("table_name", ""))
                tname_cn = table.get("table_name", tname)
                cols_original = table.get("column_names_original", table.get("columns", []))
                cols_cn = table.get("column_names", cols_original)

                col_parts = []
                for i, co in enumerate(cols_original):
                    cn = cols_cn[i] if i < len(cols_cn) else co
                    if cn and cn != co:
                        col_parts.append(f"{co}({cn})")
                    else:
                        col_parts.append(co)

                display_name = f"{tname}({tname_cn})" if tname_cn and tname_cn != tname else tname
                lines.append(f"# {display_name} ( {', '.join(col_parts)} )")
        return "\n".join(lines)

    def _format_fks_for_prompt(self, instance_schemas: list) -> str:
        """Extract FK strings for prompt."""
        fks = []
        for table in instance_schemas:
            if isinstance(table, dict):
                fk = table.get("fk") or table.get("foreign_key")
                if fk:
                    fks.append(str(fk))
        return "\n".join(f"# {fk}" for fk in fks) if fks else ""

    # ------------------------------------------------------------------
    # Template selection
    # ------------------------------------------------------------------

    def _select_template(self) -> str:
        """Select a prompt template based on configuration.

        Returns the template string with {schema}, {fks}, {question} placeholders.
        """
        import random as _random

        if self.use_skeleton and self.use_chinese:
            pool = [SKELETON_ZH_1, SKELETON_ZH_2, SKELETON_ZH_3]
        elif self.use_skeleton:
            pool = [SKELETON_EN_1, SKELETON_EN_2, SKELETON_EN_3]
        elif self.use_cot and self.use_chinese:
            pool = [COT_ZH_1, COT_ZH_2, COT_ZH_3]
        elif self.use_cot:
            pool = [COT_EN_1, COT_EN_2, COT_EN_3]
        elif self.use_chinese:
            pool = [INSTRUCTION_ZH_1, INSTRUCTION_ZH_2, INSTRUCTION_ZH_3]
        else:
            pool = [INSTRUCTION_EN_1, INSTRUCTION_EN_2, INSTRUCTION_EN_3]

        return _random.choice(pool)

    def _get_fewshot_example(self) -> str:
        """Get a random CoT few-shot example."""
        import random as _random
        if self.use_chinese:
            examples = FEWSHOT_COT_ZH
        else:
            examples = FEWSHOT_COT_EN
        return _random.choice(examples) if examples else ""

    # ------------------------------------------------------------------
    # SQL extraction
    # ------------------------------------------------------------------

    def _extract_sql(self, response: str) -> Optional[str]:
        """Extract SQL from LLM response.

        Handles: ```sql ... ```, ``` ... ```, Generated SQL: ``` ... ```
        """
        # Try to find SQL in code fences
        # Pattern: look for last ``` block
        parts = response.rsplit("```")
        if len(parts) >= 2:
            sql = parts[-2].strip()
            # Remove language tag if present
            if "\n" in sql:
                first_line = sql.split("\n")[0].strip().lower()
                if first_line in ("sql", "sqlite", "mysql"):
                    sql = "\n".join(sql.split("\n")[1:])
            return sql.strip()

        # Fallback: take everything after a "Generated SQL:" marker
        match = re.search(r'Generated\s+SQL\s*[:：]\s*(.+)$', response, re.DOTALL | re.IGNORECASE)
        if match:
            return match.group(1).strip().strip("`").strip()

        return None

    def _clean_sql(self, sql: str) -> str:
        """Clean extracted SQL."""
        sql = sql.replace("\n", " ").strip()
        while "  " in sql:
            sql = sql.replace("  ", " ")
        return sql

    # ------------------------------------------------------------------
    # Schema validation helpers
    # ------------------------------------------------------------------

    def _build_schema_lookup(self, schemas_list: list) -> dict:
        """Build {table_lower: {col_lower, ...}} from instance_schemas list.
        Indexes both table_name_original and table_name for alias matching.
        """
        lookup: dict[str, set[str]] = {}
        if isinstance(schemas_list, dict):
            table_names = schemas_list.get("table_names_original") or schemas_list.get("table_names") or []
            column_names = schemas_list.get("column_names_original") or schemas_list.get("column_names") or []
            for table_idx, col_name in column_names:
                if table_idx is None or table_idx < 0 or not col_name:
                    continue
                if table_idx >= len(table_names):
                    continue
                lookup.setdefault(str(table_names[table_idx]).lower(), set()).add(str(col_name).lower())
            if lookup:
                return lookup
            schemas_list = [schemas_list]
        for tbl in schemas_list:
            if not isinstance(tbl, dict):
                continue
            tname = tbl.get("table_name_original") or tbl.get("table_name", "")
            tname_cn = tbl.get("table_name", tname)
            cols = tbl.get("column_names_original") or tbl.get("columns")
            if cols is None:
                col = tbl.get("column_name_original") or tbl.get("column_name")
                cols = [col] if col else []
            col_set = {c.lower() for c in cols}
            if tname:
                lookup.setdefault(tname.lower(), set()).update(col_set)
            if tname_cn and tname_cn != tname:
                lookup.setdefault(tname_cn.lower(), set()).update(col_set)
        return lookup

    def _validate_sql_columns(self, sql: str, schema_lookup: dict) -> tuple[bool, list[str]]:
        """Check that all table.column references in SQL exist in schema_lookup.

        Returns (is_valid, list_of_bad_references).
        """
        if not schema_lookup:
            return True, []
        sql_keywords = {
            'as', 'on', 'where', 'and', 'or', 'join', 'from', 'select', 'group',
            'order', 'by', 'limit', 'having', 'inner', 'left', 'right', 'outer',
            'cross', 'union', 'case', 'when', 'then', 'else', 'end', 'distinct',
        }
        # Exclude floating-point literals (e.g. 1.0, 0.2) that match \w+\.\w+
        refs = [(t, c) for t, c in re.findall(r'\b(\w+)\.(\w+)\b', sql)
                if not (t.isdigit() and c.isdigit())]
        bad = []
        for table_ref, col_ref in refs:
            if table_ref.lower() in sql_keywords:
                continue
            if col_ref.lower() in ('*',):
                continue
            valid_cols = schema_lookup.get(table_ref.lower())
            if valid_cols is not None:
                # Known table: validate column strictly
                if col_ref.lower() not in valid_cols:
                    bad.append(f"{table_ref}.{col_ref}")
                continue
            # Unknown table_ref = SQL alias → trust the SQL engine at runtime
            continue
        return len(bad) == 0, bad

    # ------------------------------------------------------------------
    # LLM call with retry
    # ------------------------------------------------------------------

    def _generate_one(self, prompt: str, attempt: int = 0) -> Optional[str]:
        """Call LLM and extract SQL. Returns None on failure."""
        try:
            llm = self.get_llm()
            if llm is None:
                raise ValueError("LLM is not initialized")
            if hasattr(llm, "complete"):
                response = llm.complete(prompt)
                response_text = response.text.strip()
            else:
                response = llm.client.chat.completions.create(
                    model=getattr(llm, "model_name", None),
                    messages=[
                        {"role": "system", "content": "You are a financial Text-to-SQL assistant."},
                        {"role": "user", "content": prompt},
                    ],
                    temperature=self._temperature if self._temperature is not None else getattr(llm, "temperature", 0),
                    extra_body={"enable_thinking": self.enable_thinking},
                )
                response_text = response.choices[0].message.content.strip()
        except Exception as e:
            logger.warning(f"[FINSQLGenerator] LLM call failed (attempt {attempt + 1}): {e}")
            if attempt < self.max_attempt_times - 1:
                time.sleep(1 + attempt)
            return None

        sql = self._extract_sql(response_text)
        if not sql:
            logger.warning(f"[FINSQLGenerator] Failed to extract SQL from response (attempt {attempt + 1})")
            return None

        # Heuristic: if the "extracted SQL" is mostly the whole response, it's likely a bad extraction
        if len(sql) / max(len(response_text), 1) > 0.8:
            logger.warning(f"[FINSQLGenerator] Extracted SQL is >80% of response — likely bad format")
            return None

        return self._clean_sql(sql)

    def _save_candidate_output(self, pred_sql, item, instance_id: str):
        if not self.is_save:
            return pred_sql

        if not isinstance(pred_sql, list):
            return self.save_output(pred_sql, item, instance_id)

        save_path = Path(self.save_dir)
        if self.dataset and self.dataset.dataset_index:
            save_path = save_path / str(self.dataset.dataset_index)
        save_path.mkdir(parents=True, exist_ok=True)

        saved_paths = []
        for idx, sql in enumerate(pred_sql, start=1):
            path = save_path / f"{self.NAME}_{instance_id}_{idx}.sql"
            save_dataset(sql, new_data_source=path)
            saved_paths.append(str(path))
        self.dataset.setitem(item, "pred_sql", saved_paths)
        return pred_sql

    # ------------------------------------------------------------------
    # Main act
    # ------------------------------------------------------------------

    def act(
        self,
        item,
        schema: Union[str, PathLike, Dict, List] = None,
        schema_links: Union[str, List[str]] = None,
        sub_questions: Union[str, List[str], Dict] = None,
        data_logger=None,
        **kwargs
    ) -> str:
        if data_logger:
            data_logger.info(f"{self.NAME}.act start | item={item}")

        row = self.dataset[item]
        question = row["question"]

        # Load instance_schemas
        instance_schemas = schema
        if instance_schemas is None:
            schema_ref = row.get("instance_schemas")
            if isinstance(schema_ref, (str, PathLike)):
                instance_schemas = load_dataset(schema_ref)
            elif schema_ref:
                instance_schemas = schema_ref

        if instance_schemas is None:
            instance_schemas = self.dataset.get_db_schema(item)

        if instance_schemas is None:
            raise ValueError(f"No schema available for item {item}")

        # Normalise: unwrap dict wrapper
        schema_text_override = None
        if isinstance(instance_schemas, dict):
            if isinstance(instance_schemas.get("input_sequence"), str):
                schema_text_override = instance_schemas["input_sequence"]
            schemas_list = (
                instance_schemas.get("schema_tables")
                or instance_schemas.get("instance_schemas", instance_schemas)
            )
            if isinstance(schemas_list, dict):
                if schema_text_override is not None and "db_id" not in schemas_list:
                    schemas_list = []
                else:
                    from core.data_manage import single_central_process
                    schemas_list = single_central_process(schemas_list)
        else:
            schemas_list = instance_schemas

        if isinstance(schemas_list, dict):
            schemas_list = [schemas_list]

        # Format schema — use RESDSQL style by default (aligned with FinSQL training)
        if self.schema_format == "legacy":
            schema_text = self._format_schema_for_prompt(schemas_list)
        else:
            schema_text = self._format_schema_resdsql_style(schemas_list)
        if schema_text_override is not None:
            schema_text = schema_text_override
        fk_text = self._format_fks_for_prompt(schemas_list)

        # Select template
        template = self._select_template()
        if self.use_cot:
            fewshot = self._get_fewshot_example()
            # Prepend few-shot before the question
            template = fewshot + "\n" + template

        # Build prompt
        prompt = SQLITE_DIALECT_NOTE + template.format(schema=schema_text, fks=fk_text, question=question)

        if data_logger:
            data_logger.info(f"{self.NAME}.prompt_preview | {prompt[:300]}...")

        pred_sqls = []
        full_schema_items = self.dataset.get_db_schema(item)
        if isinstance(full_schema_items, dict):
            from core.data_manage import single_central_process
            full_schema_items = single_central_process(full_schema_items)
        if not full_schema_items:
            full_schema_items = schemas_list
        schema_lookup = self._build_schema_lookup(full_schema_items)
        for candidate_idx in range(self.n_candidates):
            pred_sql = None
            for attempt in range(self.max_attempt_times):
                pred_sql = self._generate_one(prompt, attempt)
                if not pred_sql:
                    if data_logger:
                        data_logger.info(
                            f"{self.NAME}.retry | candidate={candidate_idx + 1} attempt={attempt + 1}"
                        )
                    continue
                # Validate generated SQL against reduced schema
                valid, bad_refs = self._validate_sql_columns(pred_sql, schema_lookup)
                if valid:
                    break
                logger.warning(
                    f"[FINSQLGenerator] SQL has {len(bad_refs)} unknown column ref(s) "
                    f"(attempt {attempt + 1}): {bad_refs[:5]}"
                )
                if data_logger:
                    data_logger.info(
                        f"{self.NAME}.invalid_cols | candidate={candidate_idx + 1} "
                        f"attempt={attempt + 1} bad_refs={bad_refs[:5]}"
                    )
                pred_sql = None  # force retry

            if not pred_sql:
                logger.warning(
                    f"[FINSQLGenerator] Candidate {candidate_idx + 1} failed after "
                    f"{self.max_attempt_times} attempts, falling back to 'SELECT'"
                )
                pred_sql = "SELECT"
            pred_sqls.append(sql_clean(pred_sql))

        pred_sql = pred_sqls[0] if self.n_candidates == 1 else pred_sqls

        if data_logger:
            data_logger.info(f"{self.NAME}.final_sql | sql={pred_sql}")

        pred_sql = self._save_candidate_output(pred_sql, item, row.get("instance_id"))

        if data_logger:
            data_logger.info(f"{self.NAME}.act end | item={item}")

        return pred_sql


FinSQLGenerator = FINSQLGenerator

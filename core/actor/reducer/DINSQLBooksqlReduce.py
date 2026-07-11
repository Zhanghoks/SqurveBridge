"""DIN-SQL BookSQL Reducer — Schema linking + complexity classification for BookSQL.

Two LLM calls:
  1. schema_linking_prompt  → extract schema_links (split on "Schema_links: ")
  2. classification_prompt  → extract predicted_class + sub_questions (split on "Label: ")

Prompts are ported verbatim from candidates/BookSQL-main/GPT/DIN-SQL.py lines 10-178.
The college_2 anchor used in the original Spider DINSQLGenerator is intentionally absent;
BookSQL already supplies its own few-shot examples.
"""

from typing import Any, Dict, List, Union
from loguru import logger

from core.actor.reducer.BaseReduce import BaseReducer
from core.data_manage import Dataset


# ---------------------------------------------------------------------------
# Schema format helpers (MySQL-like, aligned with BookSQL source)
# ---------------------------------------------------------------------------

def find_fields_mysql_like(schema_items: List[Dict]) -> str:
    """Format schema items as 'Table <name>, columns = [*, col1, col2, ...]' lines."""
    tables: Dict[str, List[str]] = {}
    for item in schema_items:
        tname = item.get("table_name_original") or item.get("table_name", "")
        cname = item.get("column_name_original") or item.get("column_name", "")
        if tname not in tables:
            tables[tname] = []
        if cname:
            tables[tname].append(cname)

    lines = []
    for tname, cols in tables.items():
        col_str = ",".join(["*"] + cols)
        lines.append(f"Table {tname}, columns = [{col_str}]")
    return "\n".join(lines) + "\n" if lines else ""


def find_foreign_keys_mysql_like(schema_items: List[Dict], row: Dict = None) -> str:
    """Format foreign keys as 'table1.col1 = table2.col2' list."""
    fks = []
    # Try item-level FK fields
    for item in schema_items:
        fk = item.get("foreign_key") or item.get("fk")
        if fk:
            fks.append(str(fk))

    # Try row-level FK metadata
    if not fks and row:
        fks_raw = row.get("fk") or row.get("foreign_keys") or []
        for fk in fks_raw:
            if isinstance(fk, dict):
                src = (f"{fk.get('source_table_name_original', '')}."
                       f"{fk.get('source_column_name_original', '')}")
                tgt = (f"{fk.get('target_table_name_original', '')}."
                       f"{fk.get('target_column_name_original', '')}")
                fks.append(f"{src} = {tgt}")
            else:
                fks.append(str(fk))

    return "[" + ",".join(fks) + "]"


# ---------------------------------------------------------------------------
# DINSQLBooksqlReducer
# ---------------------------------------------------------------------------

@BaseReducer.register_actor
class DINSQLBooksqlReducer(BaseReducer):
    """DIN-SQL reducer for BookSQL: schema linking + complexity classification.

    LLM call 1: schema_linking_prompt → schema_links
    LLM call 2: classification_prompt → predicted_class + sub_questions

    Output stored in dataset: schema_links, predicted_class, sub_questions
    """

    NAME = "DINSQLBooksqlReducer"

    SKILL = """# DINSQLBooksqlReducer

DIN-SQL schema linking + complexity classification for the BookSQL accounting domain.
Two LLM calls:
  1. schema_linking_prompt (10 BookSQL few-shot CoT examples) → schema_links
  2. classification_prompt (8 examples) → predicted_class (EASY/NON-NESTED/NESTED) + sub_questions

## Inputs
- Full database schema from dataset

## Outputs
- schema_links: str
- predicted_class: str (EASY / NON-NESTED / NESTED)
- sub_questions: str
"""

    # ------------------------------------------------------------------
    # Prompt templates — ported verbatim from DIN-SQL.py lines 10-178
    # ------------------------------------------------------------------

    SCHEMA_LINKING_PROMPT = '''Table master_txn_table, columns = [*, Transaction_ID, Transaction_DATE, Transaction_TYPE, Amount, CreatedDATE, CreatedUSER, Account, AR_paid, AP_paid, Due_DATE, Open_balance, \
                            Customers, Vendor, Product_Service, Quantity, Rate, Credit, Debit, payment_method, Misc]
Table chart_of_accounts, columns = [*, Account_name, Account_type]
Table customers, columns = [*, customer_name, customer_full_name, Billing_address, Billing_city, Billing_state, Billing_ZIP_code, Shipping_address, Shipping_city, Shipping_state, Shipping_ZIP_code, Balance]
Table employees, columns = [*, Employee_name, Employee_ID, Hire_date, Billing_rate, Deleted]
Table products, columns = [*, Product_Service, Product_Service_type]
Table vendors, columns = [*, Vendor_name, Billing_address, Billing_city, Billing_state, Billing_ZIP_code, Balance]
Table payment_method, columns = [*, Payment_method, Credit_card]
Foreign_keys = [master_txn_table.Account = chart_of_accounts.Account_name,master_txn_table.Customers = customers.customer_name,master_txn_table.Vendor = vendors.Vendor_name,master_txn_table.Product_Service = products.Product_Service,master_txn_table.payment_method = payment_method.payment_method]
Q: How much open credit does customer Felicia King have?
S: select sum(open_balance) from ( select distinct transaction_id, open_balance from master_txn_table where customers = 'Felicia King')
A: Let\'s think step by step. In the question "How much open credit does customer Felicia King?", we are asked:
    "How much open credit", so we need column = [master_txn_table.open_balance]
    "open credit does customer Felicia King", so we need column = [master_txn_table.transaction_id,master_txn_table.customers]
    Based on the columns and tables, we need these Foreign_keys = [].
    Based on the tables, columns, and Foreign_keys, The set of possible cell values are = [Felicia King]. So the Schema_links are:
    Schema_links: [master_txn_table.open_balance,master_txn_table.customers,master_txn_table.transaction_id,Felicia King]

Q: Last 7 days, how much has Katie White paid us?
S: select sum(amount) from (select distinct transaction_id, amount from master_txn_table  where customers = 'Katie White' and transaction_type = 'payment' and transaction_date BETWEEN date( current_date, '-7 days') AND date( current_date)  )
A: Let\'s think step by step. In the question "Last 7 days, how much has Katie White paid us?", we are asked:
    "paid us", so we need column = [master_txn_table.transaction_type]
    "Katie White", so we need column = [master_txn_table.customers]
    "Last 7 days", so we need column = [master_txn_table.transaction_date]
    Based on the columns and tables, we need these Foreign_keys = [].
    Based on the tables, columns, and Foreign_keys, The set of possible cell values are = [Last 7 days]. So the Schema_links are:
    Schema_links: [master_txn_table.transaction_type,master_txn_table.customers,master_txn_table.transaction_date,current_date]

Q: How many Traveller accomodation did we sell to Eric Quinn Last 7 days?
S: select sum(quantity) from master_txn_table where customers = 'Eric Quinn' and product_service = 'Traveller accomodation' and transaction_type in ('invoice', 'sales receipt') and transaction_date BETWEEN date( current_date, '-7 days') AND date( current_date)
A: Let\'s think step by step. In the question "How many Traveller accomodation did we sell to Eric Quinn Last 7 days?", we are asked:
    "How many Traveller accomodation", so we need column = [master_txn_table.product_service,master_txn_table.quantity]
    "did we sell", so we need column = [master_txn_table.transaction_type]
    "Last 7 days", so we need column = [master_txn_table.transaction_date]
    Based on the columns and tables, we need these Foreign_keys = [].
    Based on the tables, columns, and Foreign_keys, The set of possible cell values are = [Eric Quinn,Last 7 days]. So the Schema_links are:
    Schema_links: [master_txn_table.quantity,master_txn_table.customers,master_txn_table.product_service,master_txn_table.trasaction_type,master_txn_table.transaction_date,current_date]

Q: Number of invoices created for Uncategorized Income in in q1 this year?
S: select count(distinct transaction_id) from master_txn_table where transaction_type = 'invoice' and instr(account,"Uncategorized Income") and transaction_date BETWEEN date(current_date, 'start of year') AND date(current_date, 'start of year', '+3 month', '-1 day')
A: Let\'s think step by step. In the question "Number of invoices created for Uncategorized Income in in q1 this year?", we are asked:
    "Number of invoices", so we need column = [master_txn_table.transaction_id]
    "Uncategorized Income", so we need column = [master_txn_table.account]
    "q1 this year", so we need column = [master_txn_table.transaction_date]
    Based on the columns and tables, we need these Foreign_keys = [].
    Based on the tables, columns, and Foreign_keys, The set of possible cell values are = [Uncategorized Income,invoice]. So the Schema_links are:
    Schema_links: [master_txn_table.transaction_id,master_txn_table.accounts,master_txn_table.trasaction_type,master_txn_table.transaction_date,current_date]

Q: What payment method was used to pay sales receipt #85820
S: select distinct payment_method from master_txn_table where transaction_type = 'sales receipt' and transaction_id = 85820
A: Let\'s think step by step. In the question "What payment method was used to pay sales receipt #85820", we are asked:
    "What payment method", so we need column = [master_txn_table.payment_method]
    "to pay sales", so we need column = [master_txn_table.transaction_type]
    "receipt #85820", so we need column = [master_txn_table.transaction_id]
    Based on the columns and tables, we need these Foreign_keys = [].
    Based on the tables, columns, and Foreign_keys, The set of possible cell values are = [85820]. So the Schema_links are:
    Schema_links: [master_txn_table.transaction_id,master_txn_table.trasaction_type]

Q: Since Last 12 months, how much has Catherine Deleon paid us?
S: select sum(amount) from (select distinct transaction_id, amount from master_txn_table  where customers = 'Catherine Deleon' and transaction_type = 'payment' and transaction_date BETWEEN date( current_date, "-12 months", "start of month") AND date( current_date, 'start of month', '-1 day')  )
A:  Let\'s think step by step. In the question "Since Last 12 months, how much has Catherine Deleon paid us?", we are asked:
    "how much has Catherine Deleon", so we need column = [master_txn_table.transaction_id,master_txn_table.customers]
    "paid us", so we need column = [master_txn_table.transaction_type]
    "Since Last 12 months", so we need column = [master_txn_table.transaction_date]
    Based on the columns and tables, we need these Foreign_keys = [].
    Based on the tables, columns, and Foreign_keys, The set of possible cell values are = [atherine Deleon]. So the Schema_links are:
    Schema_links: [master_txn_table.transaction_id,,master_txn_table.customers,master_txn_table.trasaction_type,master_txn_table.transaction_date,current_date]

Q: What was our total spend for Registration for tournaments and matches in yesterday
S: select sum(debit) from master_txn_table  as T1 join chart_of_accounts as T2 on T1.account = T2.account_name where instr(account,'Registration for tournaments and matches') and account_type in ('Expenses','Other Expenses') and transaction_date BETWEEN date( current_date, '-1 day') AND date( current_date, '-1 day')
A:  Let\'s think step by step. In the question "What was our total spend for Registration for tournaments and matches in yesterday", we are asked:
    "What was our total spend", so we need column = [master_txn_table.debit,master_txn_table.account,chart_of_accounts.account_type]
    "Registration for tournaments and matches", so we need column = [master_txn_table.account]
    "yesterday", so we need column = [master_txn_table.transaction_date]
    Based on the columns and tables, we need these Foreign_keys = [master_txn_table.account=chart_of_accounts.account_name].
    Based on the tables, columns, and Foreign_keys, The set of possible cell values are = [Bradley Howard]. So the Schema_links are:
    Schema_links: [master_txn_table.debit,master_txn_table.account,master_txn_table.customers,master_txn_table.transaction_date,chart_of_accounts.account_name,chart_of_accounts.account_type,current_date]

Q: What is my average revenue from Jacob Ramirez in the in q2 this year?
S: select avg(credit) from master_txn_table  as T1 join chart_of_accounts as T2 on T1.account = T2.account_name where account_type in ('Income','Other Income') and customers = 'Jacob Ramirez' and transaction_date BETWEEN date(current_date, 'start of year','+3 month') AND date(current_date, 'start of year', '+6 month', '-1 day')
A: Let\'s think step by step. In the question "What is my average revenue from Jacob Ramirez in the in q2 this year?", we are asked:
    "What is my average revenue", so we need column = [master_txn_table.credit]
    "from Jacob Ramirez", so we need column = [master_txn_table.customers]
    Based on the columns and tables, we need these Foreign_keys = [].
    Based on the tables, columns, and Foreign_keys, The set of possible cell values are = [Jacob Ramirez,master_txn_table.account=chart_of_accounts.account_name]. So the Schema_links are:
    Schema_links: [master_txn_table.credit,master_txn_table.customers,master_txn_table.transaction_type,master_txn_table.transaction_date,chart_of_accounts.account_name,chart_of_accounts.account_type,current_date]]

Q: How much money did we make This quarter to date?
S: select sum(credit) from master_txn_table  as T1 join chart_of_accounts as T2 on T1.account = T2.account_name where account_type in ('Income','Other Income') and transaction_date >= strftime('%Y-%m-%d', strftime('%Y', now) || '-' || substr('00' || (((strftime('%m', now) - 1) / 3) * 3 + 1), -2, 2) || '-01')
A: Let\'s think step by step. In the question "How much money did we make This quarter to date?", we are asked:
    "How much money", so we need column = [master_txn_table.credit,master_txn_table.account,chart_of_accounts.account_type]
    "This quarter to date", so we need column = [master_txn_table.transaction_date]
    Based on the columns and tables, we need these Foreign_keys = [].
    Based on the tables, columns, and Foreign_keys, The set of possible cell values are = []. So the Schema_links are:
    Schema_links: [master_txn_table.credit,master_txn_table.account,master_txn_table.transaction_date,chart_of_accounts.account_name,chart_of_accounts.account_type]

Q: What was our greatest expenses This fiscal year to date?
S: select account, sum(debit) from master_txn_table  as T1 join chart_of_accounts as T2 on T1.account = T2.account_name where account_type in ('Expenses','Other Expenses') and transaction_date BETWEEN date(current_date, '-3 months', 'start of year', '+3 months') AND date(current_date, '-3 months', 'start of year','+1 year', '+3 months', '-1 day')  order by sum(debit) desc limit 1
A: Let\'s think step by step. In the question "What was our greatest expenses This fiscal year to date?", we are asked:
    "What was our greatest expenses", so we need column = [master_txn_table.debit,master_txn_table.account,chart_of_accounts.account_type]
    "This fiscal year to date", so we need column = [master_txn_table.transaction_date]
    Based on the columns and tables, we need these Foreign_keys = [].
    Based on the tables, columns, and Foreign_keys, The set of possible cell values are = []. So the Schema_links are:
    Schema_links: [master_txn_table.debit,master_txn_table.account,master_txn_table.transaction_date,chart_of_accounts.account_name,chart_of_accounts.account_type,current_date]

'''

    CLASSIFICATION_PROMPT = '''Q: What are my transactions MTD?
schema_links: [master_txn_table.transaction_id,master_txn_table.amount,master_txn_table.transaction_date]
A: Let\'s think step by step. The SQL query for the question "What are my transactions MTD?" needs these tables = [master_txn_table], so we don\'t need JOIN.
Plus, it doesn\'t require nested queries with (INTERSECT, UNION, EXCEPT, IN, NOT IN), and we need the answer to the questions = [""].
So, we don\'t need JOIN and don\'t need nested queries, then the the SQL query can be classified as "EASY".
Label: "EASY"


Q: How many products are never sold with total value higher than 5?
schema_links: [Product_Service.transaction_id,master_txn_table.transaction_type]
A: Let\'s think step by step. The SQL query for the question "How many products are never sold with total value higher than 5?" needs these tables = [Product_Service,master_txn_table], so we need JOIN.
Plus, it requires nested queries with (INTERSECT, UNION, EXCEPT, IN, NOT IN) or inner query inside from clause, and we need the answer to the questions = ["products that are sold with total value higher than 5"].
So, we need JOIN and need nested queries, then the the SQL query can be classified as "NESTED".
Label: "NESTED"


Q: Who has the lowest money outstanding?
schema_links: [master_txn_table.customers,master_txn_table.open_balance,master_txn_table.transaction_id,master_txn_table.customers]
A: Let\'s think step by step. The SQL query for the question "Who has the lowest money outstanding?" needs these tables = [master_txn_table], so we dont need JOIN.
Plus, it requires nested queries with (INTERSECT, UNION, EXCEPT, IN, NOT IN) or inner query inside from clause, and we need the answer to the questions = ["products that are sold with total value higher than 5"].
So, we don\'t need JOIN and need nested queries, then the the SQL query can be classified as "NESTED".
Label: "NESTED"


Q: What is my average invoice from Patricia Mercado?
schema_links: [master_txn_table.customers,master_txn_table.open_balance,master_txn_table.transaction_id,master_txn_table.customers]
A: Let\'s think step by step. The SQL query for the question "What is my average invoice from Patricia Mercado? " needs these tables = [master_txn_table], so we dont need JOIN.
Plus, it requires nested queries with (INTERSECT, UNION, EXCEPT, IN, NOT IN) or inner query inside from clause, and we need the answer to the questions = ["Invoice from Patricia Mercado"].
So, we don\'t need JOIN and need nested queries, then the the SQL query can be classified as "NESTED".
Label: "NESTED"


Q:give me the list of accounts where my revenue increased by more than 10% in this month as compared to last month",
schema_links: [master_txn_table.account,master_txn_table.credit,chart_of_accounts.account_name]
A: Let\'s think step by step. The SQL query for the question "give me the list of accounts where my revenue increased by more than 10% in this month as compared to last month" needs these tables = [master_txn_table,chart_of_accounts], so we need JOIN.
Plus, it requires nested queries with (INTERSECT, UNION, EXCEPT, IN, NOT IN) or inner query inside from clause, and we need the answer to the questions = ["revenue of last month and this month"].
So, we need JOIN and need nested queries, then the the SQL query can be classified as "NESTED".
Label: "NESTED"


Q: What was our total income from Bradley Howard in yesterday?
schema_links = [master_txn_table.account = chart_of_accounts.account_name,master_txn_table.credit,master_txn_table.transaction_date,master_txn_table.account_type]
A: Let\'s think step by step. The SQL query for the question "What was our total income from Bradley Howard in yesterday?" needs these tables = [master_txn_table,chart_of_accounts], so we need JOIN.
Plus, it doesn\'t need nested queries with (INTERSECT, UNION, EXCEPT, IN, NOT IN), and we need the answer to the questions = [""].
So, we need JOIN and don\'t need nested queries, then the the SQL query can be classified as "NON-NESTED".
Label: "NON-NESTED"


Q: What are my expenses for the Last 7 days?
schema_links = [master_txn_table.account = chart_of_accounts.account_name,master_txn_table.credit,master_txn_table.transaction_date,master_txn_table.account_type]
A: Let\'s think step by step. The SQL query for the question "What are my expenses for the Last 7 days?" needs these tables = [master_txn_table,chart_of_accounts], so we need JOIN.
Plus, it doesn\'t need nested queries with (INTERSECT, UNION, EXCEPT, IN, NOT IN), and we need the answer to the questions = [""].
So, we need JOIN and don\'t need nested queries, then the the SQL query can be classified as "NON-NESTED".
Label: "NON-NESTED"


Q: YTD, what was our smallest expense?
schema_links = [master_txn_table.account = chart_of_accounts.account_name,master_txn_table.credit,master_txn_table.transaction_date,master_txn_table.account_type,master_txn_table.debit]
A: Let\'s think step by step. The SQL query for the question "YTD, what was our smallest expense?" needs these tables = [master_txn_table,chart_of_accounts], so we need JOIN.
Plus, it doesn\'t need nested queries with (INTERSECT, UNION, EXCEPT, IN, NOT IN), and we need the answer to the questions = [""].
So, we need JOIN and don\'t need nested queries, then the the SQL query can be classified as "NON-NESTED".
Label: "NON-NESTED"

'''

    # ------------------------------------------------------------------
    # Init
    # ------------------------------------------------------------------

    def __init__(
        self,
        dataset: Dataset = None,
        llm: Any = None,
        is_save: bool = True,
        save_dir: str = "../files/instance_schemas",
        **kwargs,
    ):
        self.dataset = dataset
        self.llm = llm
        self.is_save = is_save
        self.save_dir = save_dir

    # ------------------------------------------------------------------
    # Prompt builders
    # ------------------------------------------------------------------

    def _schema_linking_prompt_maker(self, question: str, fields: str, foreign_keys: str) -> str:
        instruction = (
            "# Find the schema_links for generating SQL queries for each question "
            "based on the database schema and Foreign keys.\n"
        )
        return (
            instruction
            + self.SCHEMA_LINKING_PROMPT
            + fields
            + "Foreign_keys = " + foreign_keys + "\n"
            + 'Q: "' + question + '"\n'
            + "A: Let's think step by step."
        )

    def _classification_prompt_maker(
        self, question: str, fields: str, foreign_keys: str, schema_links: str
    ) -> str:
        instruction = (
            "# For the given question, classify it as EASY, NON-NESTED, or NESTED "
            "based on nested queries and JOIN.\n"
            "\nif need nested queries: predict NESTED\n"
            "elif need JOIN and don't need nested queries: predict NON-NESTED\n"
            "elif don't need JOIN and don't need nested queries: predict EASY\n\n"
        )
        return (
            instruction
            + fields
            + "Foreign_keys = " + foreign_keys + "\n\n"
            + self.CLASSIFICATION_PROMPT
            + 'Q: "' + question + '"\n'
            + "schema_links: " + schema_links + "\n"
            + "A: Let's think step by step."
        )

    # ------------------------------------------------------------------
    # Main act
    # ------------------------------------------------------------------

    def act(self, item, schema=None, data_logger=None, **kwargs):
        if data_logger:
            data_logger.info(f"{self.NAME}.act start | item={item}")

        row = self.dataset[item]
        question = row["question"]

        # Load schema items
        schema_items = schema
        if schema_items is None:
            schema_items = self.dataset.get_db_schema(item)
        if schema_items is None:
            raise ValueError(f"No schema for item {item}")

        if isinstance(schema_items, dict):
            from core.data_manage import single_central_process
            schema_items = single_central_process(schema_items)

        # Build schema fields and foreign keys strings
        fields = find_fields_mysql_like(schema_items)
        foreign_keys = find_foreign_keys_mysql_like(schema_items, row)

        # ------------------------------------------------------------------
        # LLM call 1: schema linking
        # ------------------------------------------------------------------
        prompt1 = self._schema_linking_prompt_maker(question, fields, foreign_keys)
        if data_logger:
            data_logger.info(f"{self.NAME}.schema_link_prompt | preview={prompt1[:200]}")

        try:
            llm = self.get_llm()
            if llm is None:
                raise ValueError("LLM not initialised")
            raw1 = llm.complete(prompt1).text.strip()
        except Exception as e:
            logger.error(f"[{self.NAME}] LLM call 1 failed: {e}")
            raw1 = ""

        try:
            schema_links = raw1.split("Schema_links: ")[1].strip()
        except IndexError:
            logger.warning(f"[{self.NAME}] Schema_links parsing failed; using []")
            schema_links = "[]"

        if data_logger:
            data_logger.info(f"{self.NAME}.schema_links | {schema_links}")

        # ------------------------------------------------------------------
        # LLM call 2: classification
        # ------------------------------------------------------------------
        prompt2 = self._classification_prompt_maker(question, fields, foreign_keys, schema_links)
        if data_logger:
            data_logger.info(f"{self.NAME}.classification_prompt | preview={prompt2[:200]}")

        try:
            raw2 = llm.complete(prompt2).text.strip()
        except Exception as e:
            logger.error(f"[{self.NAME}] LLM call 2 failed: {e}")
            raw2 = ""

        try:
            predicted_class = raw2.split("Label: ")[1].strip()
        except IndexError:
            logger.warning(f"[{self.NAME}] Label parsing failed; defaulting to NESTED")
            predicted_class = '"NESTED"'

        # Extract sub_questions for NESTED case
        sub_questions = ""
        try:
            sub_questions = raw2.split('questions = ["')[1].split('"]')[0]
        except IndexError:
            pass

        if data_logger:
            data_logger.info(
                f"{self.NAME}.classification | predicted_class={predicted_class} "
                f"| sub_questions={sub_questions}"
            )

        # Persist into dataset row
        self.dataset.setitem(item, "schema_links", schema_links)
        self.dataset.setitem(item, "predicted_class", predicted_class)
        self.dataset.setitem(item, "sub_questions", sub_questions)

        result = {
            "schema_links": schema_links,
            "predicted_class": predicted_class,
            "sub_questions": sub_questions,
        }

        if data_logger:
            data_logger.info(f"{self.NAME}.act end | item={item}")

        return result

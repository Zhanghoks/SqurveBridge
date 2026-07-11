"""DIN-SQL BookSQL Generator -- difficulty-routed SQL generation for BookSQL.

Three LLM-call paths based on predicted_class from DINSQLBooksqlReducer:
  EASY       -> easy_prompt (5 BookSQL few-shot examples) -> SQL directly
  NON-NESTED -> medium_prompt (10 examples) -> split on "SQL: "
  NESTED     -> hard_prompt (10 examples) + sub_questions -> split on "SQL: "

Prompts ported verbatim from candidates/BookSQL-main/GPT/DIN-SQL.py lines 181-344.
No college_2 anchor -- BookSQL supplies its own domain-specific few-shot examples.
"""

from typing import Any, Dict, List, Union, Optional
from os import PathLike
from loguru import logger

from core.actor.generator.BaseGenerate import BaseGenerator
from core.data_manage import Dataset
from core.utils import sql_clean
from core.actor.reducer.DINSQLBooksqlReduce import (
    find_fields_mysql_like,
    find_foreign_keys_mysql_like,
)


@BaseGenerator.register_actor
class DINSQLBooksqlGenerator(BaseGenerator):
    """DIN-SQL generator for BookSQL accounting domain.

    Reads schema_links, predicted_class, sub_questions from the dataset row
    (populated by DINSQLBooksqlReducer) and routes to the appropriate
    BookSQL-specific few-shot prompt template.
    """

    NAME = "DINSQLBooksqlGenerator"

    SKILL = """# DINSQLBooksqlGenerator

DIN-SQL generation step for BookSQL. Reads predicted_class from dataset row
(set by DINSQLBooksqlReducer) and routes to EASY / NON-NESTED / NESTED prompt.

## Inputs
- schema_links: from dataset row (set by DINSQLBooksqlReducer)
- predicted_class: EASY / NON-NESTED / NESTED
- sub_questions: for NESTED path

## Output
pred_sql
"""

    # ------------------------------------------------------------------
    # BookSQL-specific prompt constants
    # Ported verbatim from candidates/BookSQL-main/GPT/DIN-SQL.py lines 181-344
    # ------------------------------------------------------------------

    EASY_PROMPT = (
        'Q: "How much open credit does customer Felicia King?"\n'
        "Schema_links: [master_txn_table.open_balance,master_txn_table.transaction_id,master_txn_table.customers,Felicia King]\n"
        "SQL: select sum(open_balance) from ( select distinct transaction_id, open_balance from master_txn_table where customers = 'Felicia King')\n\n"
        'Q: "What are my transactions Last fiscal year?"\n'
        "Schema_links: [master_txn_table.transaction_id,master_txn_table.amount,master_txn_table.transaction_date]\n"
        "SQL: select distinct transaction_id, amount from master_txn_table where transaction_date BETWEEN date(current_date, '-3 months', 'start of year','-1 years', '+3 months') AND date(current_date, '-3 months', 'start of year','-1 years', '+3 months', '+1 years', '-1 days')\n\n"
        'Q: "How much open credit does customer Lonnie Snow?"\n'
        "Schema_links: [master_txn_table.open_balance,master_txn_table.transaction_id,master_txn_table.customers,Lonnie Snow]\n"
        "SQL: select sum(open_balance) from ( select distinct transaction_id, open_balance from master_txn_table where customers = 'Lonnie Snow')\n\n"
        'Q: "What are my transactions in may last year?"\n'
        "Schema_links: [master_txn_table.transaction_id,master_txn_table.amount,master_txn_table.transaction_date]\n"
        "SQL: select distinct transaction_id, amount from master_txn_table where transaction_date BETWEEN date(current_date, '-1 year', 'start of year', '+4 month') AND date(current_date, '-1 year', 'start of year', '+5 month', '-1 day')\n\n"
        'Q: "What are my transactions in aug this year?"\n'
        "Schema_links: [master_txn_table.transaction_id,master_txn_table.amount,master_txn_table.transaction_date]\n"
        "SQL: select distinct transaction_id, amount from master_txn_table where transaction_date BETWEEN date(current_date, 'start of year', '+7 month') AND date(current_date, 'start of year', '+8 month', '-1 day')\n\n\n"
    )

    MEDIUM_PROMPT = (
        'Q: "How many Traveller accomodation did we sell to Eric Quinn Last 7 days?"\n'
        "Schema_links: [master_txn_table.quantity,master_txn_table.customers,master_txn_table.product_service,master_txn_table.transaction_type,master_txn_table.transaction_date]\n"
        "A: Let's think step by step. For creating the SQL for the given question, we need to join these tables = []. First, create an intermediate representation, then use it to construct the SQL query.\n"
        "Intermediate_representation: select sum(master_txn_table.quantity) from master_txn_table where master_txn_table.customers = 'Eric Quinn' and master_txn_table.product_service = 'Traveller accomodation' and master_txn_table.trasaction_type in ('invoice','sales receipt') and master_txn_table.transaction_date BETWEEN date(current_date) AND date(current_date)\n"
        'SQL: select sum(quantity) from master_txn_table where customers = "Eric Quinn" and product_service = "Traveller accomodation" and trasaction_type in (\'invoice\',\'sales receipt\') and transaction_date BETWEEN date(current_date) AND date(current_date)\n\n'
        'Q: "How many Richard Wall invoices are still outstanding?"\n'
        "Schema_links: [master_txn_table.transaction_id,master_txn_table.customers,master_txn_table.open_balance,master_txn_table.transaction_type]\n"
        "A: Let's think step by step. For creating the SQL for the given question, we need to join these tables = []. First, create an intermediate representation, then use it to construct the SQL query.\n"
        "Intermediate_representation: select count(distinct master_txn_table.transaction_id) from master_txn_table where master_txn_table.customers = 'Richard Wall' and master_txn_table.open_balance > 0 and master_txn_table.transaction_type = 'invoice'\n"
        "SQL: select count(distinct transaction_id) from master_txn_table where customers = 'Richard Wall' and open_balance > 0 and transaction_type = 'invoice'\n\n"
        'Q: "How many invoices are still oustanding for Tony Arellano as of in q1 this year?"\n'
        "Schema_links: [master_txn_table.transaction_id,master_txn_table.customers,master_txn_table.transaction_type,master_txn_table.open_balance,master_txn_table.transaction_date]\n"
        "A: Let's think step by step. For creating the SQL for the given question, we need to join these tables = []. First, create an intermediate representation, then use it to construct the SQL query.\n"
        "Intermediate_representation: select count(distinct master_txn_table.transaction_id) from master_txn_table where master_txn_table.customers = 'Tony Arellano' and master_txn_table.transaction_type = 'invoice' and master_txn_table.open_balance >0 and master_txn_table.transaction_date BETWEEN date(current_date, 'start of year') AND date(current_date, 'start of year', '+3 month', '-1 day')\n"
        'SQL: select count(distinct transaction_id) from master_txn_table where customers = "Tony Arellano" and transaction_type = \'invoice\' and open_balance >0 and transaction_date BETWEEN date(current_date, \'start of year\') AND date(current_date, \'start of year\', \'+3 month\', \'-1 day\')\n\n'
        'Q: "Since Last 12 months, how many invoices have gone unpaid?"\n'
        "Schema_links: [master_txn_table.transaction_id,master_txn_table.transaction_type,master_txn_table.due_date,master_txn_table.open_balance,master_txn_table.transaction_date]\n"
        "A: Let's think step by step. For creating the SQL for the given question, we need to join these tables = []. First, create an intermediate representation, then use it to construct the SQL query.\n"
        "Intermediate_representation: select count(distinct master_txn_table.transaction_id) from master_txn_table where master_txn_table.transaction_type = 'invoice' and master_txn_table.due_date < current_date and master_txn_table.transaction_date BETWEEN date( current_date, '-12 months', 'start of month') AND date( current_date, 'start of month', '-1 day')  and master_txn_table.open_balance > 0\n"
        "SQL: select count(distinct transaction_id) from master_txn_table where transaction_type = 'invoice' and due_date < current_date and transaction_date BETWEEN date( current_date, '-12 months', 'start of month') AND date( current_date, 'start of month', '-1 day')  and open_balance > 0\n\n"
        'Q: "When was Colleen Cunningham first payment?"\n'
        "Schema_links: [master_txn_table.transaction_date,master_txn_table.transaction_type,master_txn_table.customers,master_txn_table.transaction_date]\n"
        "A: Let's think step by step. For creating the SQL for the given question, we need to join these tables = []. First, create an intermediate representation, then use it to construct the SQL query.\n"
        "Intermediate_representation: select master_txn_table.transaction_date from master_txn_table where master_txn_table.transaction_type = 'payment' and master_txn_table.customers = 'Colleen Cunningham' order by master_txn_table.transaction_date limit 1\n"
        "SQL: select transaction_date from master_txn_table where transaction_type = 'payment' and customers = 'Colleen Cunningham' order by transaction_date limit 1\n\n"
        'Q: "Have we billed Stephanie Boyd for the in This quarter?"\n'
        "Schema_links: [master_txn_table.transaction_id,master_txn_table.transaction_type,master_txn_table.customers,master_txn_table.product_service,master_txn_table.transaction_date]\n"
        "A: Let's think step by step. For creating the SQL for the given question, we need to join these tables = []. First, create an intermediate representation, then use it to construct the SQL query.\n"
        "Intermediate_representation: select distinct master_txn_table.transaction_id from master_txn_table where master_txn_table.transaction_type = 'bill' and master_txn_table.customers = \"Stephanie Boyd\" and master_txn_table.product_service = \"--\" and master_txn_table.transaction_date >= strftime('%Y-%m-%d', strftime('%Y', 'now', '-1 year') || '-' || substr('00' || (((strftime('%m', 'now') - 1) / 3) * 3 + 1), -2, 2) || '-01')\n"
        "SQL: select distinct transaction_id from master_txn_table where transaction_type = 'bill' and customers = \"Stephanie Boyd\" and product_service = \"--\" and transaction_date >= strftime('%Y-%m-%d', strftime('%Y', 'now', '-1 year') || '-' || substr('00' || (((strftime('%m', 'now') - 1) / 3) * 3 + 1), -2, 2) || '-01')\n\n"
        'Q: "Find out 5 customers name who most recently purchased something."\n'
        "Schema_links: [master_txn_table.transaction_id,master_txn_table.customers,master_txn_table.transaction_date]\n"
        "A: Let's think step by step. For creating the SQL for the given question, we need to join these tables = []. First, create an intermediate representation, then use it to construct the SQL query.\n"
        "Intermediate_representation: SELECT master_txn_table.customers FROM (select distinct master_txn_table.transaction_id, master_txn_table.customers, master_txn_table.transaction_date from master_txn_table) ORDER BY master_txn_table.transaction_date DESC LIMIT 5\n"
        "SQL: SELECT customers FROM (select distinct transaction_id, customers, transaction_date from master_txn_table) ORDER BY transaction_date DESC LIMIT 5\n\n"
        'Q: "Last month, how many Software Training did we sell to Ryan Mcdonald?"\n'
        "Schema_links: [master_txn_table.quantity,master_txn_table.customers,master_txn_table.product_service,master_txn_table.trasaction_type,master_txn_table.transaction_date]\n"
        "A: Let's think step by step. For creating the SQL for the given question, we need to join these tables = []. First, create an intermediate representation, then use it to construct the SQL query.\n"
        "Intermediate_representation: select sum(master_txn_table.quantity) from master_txn_table where master_txn_table.customers = \"Ryan Mcdonald\" and master_txn_table.product_service = \"Software Training\" and master_txn_table.trasaction_type in ('invoice','sales receipt') and master_txn_table.transaction_date BETWEEN date( current_date, \"start of month\", \"-1 months\") AND date( current_date, \"start of month\", \"-1 days\")\n"
        "SQL: select sum(quantity) from master_txn_table where customers = 'Ryan Mcdonald' and product_service = 'Software Training' and trasaction_type in ('invoice','sales receipt') and transaction_date BETWEEN date( current_date, 'start of month', '-1 months') AND date( current_date, 'start of month', '-1 days')\n\n"
        'Q: "Since in q3 last year, how many invoices have been late?"\n'
        "Schema_links: [master_txn_table.transaction_id,master_txn_table.due_date,master_txn_table.open_balance,master_txn_table.transaction_date]\n"
        "A: Let's think step by step. For creating the SQL for the given question, we need to join these tables = []. First, create an intermediate representation, then use it to construct the SQL query.\n"
        "Intermediate_representation: select count(distinct master_txn_table.transaction_id) from master_txn_table where master_txn_table.transaction_type = 'invoice' and master_txn_table.due_date < current_date and master_txn_table.transaction_date BETWEEN date(current_date, '-1 year', 'start of year', '+6 month') AND date(current_date, '-1 year', 'start of year', '+9 month', '-1 day')  and master_txn_table.open_balance > 0\n"
        "SQL: select count(distinct transaction_id) from master_txn_table where transaction_type = 'invoice' and due_date < current_date and transaction_date BETWEEN date(current_date, '-1 year', 'start of year', '+6 month') AND date(current_date, '-1 year', 'start of year', '+9 month', '-1 day')  and open_balance > 0\n\n"
        'Q: "This quarter to date, what are my accounts receivable?"\n'
        "Schema_links: [master_txn_table.debit,master_txn_table.account,master_txn_table.transaction_date]\n"
        "A: Let's think step by step. For creating the SQL for the given question, we need to join these tables = []. First, create an intermediate representation, then use it to construct the SQL query.\n"
        "Intermediate_representation: select sum(master_txn_table.debit) from master_txn_table where master_txn_table.account = 'accounts receivable (a/r)' and master_txn_table.transaction_date >= strftime('%Y-%m-%d', strftime('%Y', 'now', '-1 year') || '-' || substr('00' || (((strftime('%m', 'now') - 1) / 3) * 3 + 1), -2, 2) || '-01')\n"
        "SQL: select sum(debit) from master_txn_table where account = 'accounts receivable (a/r)' and transaction_date >= strftime('%Y-%m-%d', strftime('%Y', 'now', '-1 year') || '-' || substr('00' || (((strftime('%m', 'now') - 1) / 3) * 3 + 1), -2, 2) || '-01')\n\n\n"
    )

    HARD_PROMPT = (
        'Q: "How many products are never sold with total value higher than 5?"\n'
        "Schema_links: [master_txn_table.product_service,master_txn_table.transaction_type,master_txn_table.credit,product_service.*]\n"
        "A: Let's think step by step. \"How many products are never sold with total value higher than 5?\" can be solved by knowing the answer to the following sub-question \"Show me all the products which are never sold with total credit value higher than 5?\".\n"
        "The SQL query for the sub-question \"Show me all the products which are never sold with total credit value higher than 5?\" is SELECT count(*) FROM Product_Service WHERE product_service NOT IN ( SELECT product_service FROM master_txn_table WHERE transaction_type in ('invoice','sales receipt') group by product_service  having sum(credit)  >  5)\n"
        "So, the answer to the question \"How many products are never sold with total value higher than 5?\" is =\n"
        "Intermediate_representation: SELECT count(Product_Service.*) FROM Product_Service WHERE Product_Service.product_service NOT IN ( SELECT master_txn_table.product_service FROM master_txn_table WHERE master_txn_table.transaction_type in ('invoice','sales receipt') group by master_txn_table.product_service  having sum(master_txn_table.credit)  >  5)\n"
        "SQL: SELECT count(*) FROM Product_Service WHERE product_service NOT IN ( SELECT product_service FROM master_txn_table WHERE transaction_type in ('invoice','sales receipt') group by product_service  having sum(credit)  >  5)\n\n"
        'Q: "What was our total income from Bradley Howard in yesterday?"\n'
        "Schema_links: [master_txn_table.credit,master_txn_table.account,master_txn_table.customers,master_txn_table.transaction_date,chart_of_accounts.account,chart_of_accounts.account_type]\n"
        "A: Let's think step by step. \"What was our total income from Bradley Howard in yesterday?\" can be solved by knowing the answer to the following sub-question \"How much amount got credited yesterday from Bradley Howard\".\n"
        "The SQL query for the sub-question \"How much amount got credited yesterday from Bradley Howard\" is select sum(credit) from master_txn_table  as T1 join chart_of_accounts as T2 on T1.account = T2.account_name where customers = 'Bradley Howard' and transaction_date BETWEEN date( current_date, '-1 day') AND date( current_date, '-1 day')  and account_type in ('Income','Other Income')\n"
        "So, the answer to the question \"What was our total income from Bradley Howard in yesterday?\" is =\n"
        "Intermediate_representation: select sum(master_txn_table.credit) from master_txn_table  where master_txn_table.customers = 'Bradley Howard' and master_txn_table.transaction_date BETWEEN date( current_date, \"-1 day\") AND date( current_date, \"-1 day\")  and chart_of_accounts.account_type in ('Income','Other Income')\n"
        "SQL: select sum(credit) from master_txn_table  as T1 join chart_of_accounts as T2 on T1.account = T2.account_name where customers = 'Bradley Howard' and transaction_date BETWEEN date( current_date, '-1 day') AND date( current_date, '-1 day')  and account_type in ('Income','Other Income')\n\n"
        'Q: "How much money did we make This quarter to date?"\n'
        "Schema_links: [master_txn_table.credit,master_txn_table.account,master_txn_table.transaction_date,chart_of_accounts.account_name,chart_of_accounts.account_type]\n"
        "A: Let's think step by step. \"How much money did we make This quarter to date?\" can be solved by knowing the answer to the following sub-question \"How much money got credited from current month quarter to current date\".\n"
        "The SQL query for the sub-question \"How much money got credited from current month quarter to current date\" is select sum(credit) from master_txn_table  as T1 join chart_of_accounts as T2 on T1.account = T2.account_name where account_type in ('Income','Other Income') and transaction_date >= strftime('%Y-%m-%d', strftime('%Y', 'now', '-1 year') || '-' || substr('00' || (((strftime('%m', 'now') - 1) / 3) * 3 + 1), -2, 2) || '-01')\n"
        "So, the answer to the question \"How much money did we make This quarter to date?\" is =\n"
        "Intermediate_representation: select sum(master_txn_table.credit) from master_txn_table where chart_of_accounts.account_type in ('Income','Other Income') and master_txn_table.transaction_date >= strftime('%Y-%m-%d', strftime('%Y', 'now', '-1 year') || '-' || substr('00' || (((strftime('%m', 'now') - 1) / 3) * 3 + 1), -2, 2) || '-01')\n"
        "SQL: select sum(credit) from master_txn_table  as T1 join chart_of_accounts as T2 on T1.account = T2.account_name where account_type in ('Income','Other Income') and transaction_date >= strftime('%Y-%m-%d', strftime('%Y', 'now', '-1 year') || '-' || substr('00' || (((strftime('%m', 'now') - 1) / 3) * 3 + 1), -2, 2) || '-01')\n\n"
        'Q: "Who has the lowest money outstanding?"\n'
        "Schema_links: [master_txn_table.customers,master_txn_table.open_balance,master_txn_table.transaction_id]\n"
        "A: Let's think step by step. \"Who has the lowest money outstanding?\" can be solved by knowing the answer to the following sub-question \"Which customers has the lowest total open balance?\".\n"
        "The SQL query for the sub-question \"Which customers has the lowest total open balance?\" is select customers, sum(open_balance) from ( select distinct transaction_id, customers, open_balance from master_txn_table ) group by customers order by sum(open_balance) asc limit 1\n"
        "So, the answer to the question \"Who has the lowest money outstanding?\" is =\n"
        "Intermediate_representation: select master_txn_table.customers, sum(master_txn_table.open_balance) from ( select distinct master_txn_table.transaction_id, master_txn_table.customers, master_txn_table.open_balance from master_txn_table ) group by master_txn_table.customers order by sum(master_txn_table.open_balance) asc limit 1\n"
        "SQL: select customers, sum(open_balance) from ( select distinct transaction_id, customers, open_balance from master_txn_table ) group by customers order by sum(open_balance) asc limit 1\n\n"
        'Q: "Return the most common payment method used for transactions."\n'
        "Schema_links: [master_txn_table.payment_method,master_txn_table.transaction_id]\n"
        "A: Let's think step by step. \"Return the most common payment method used for transactions.\" can be solved by knowing the answer to the following sub-question \"Find which payment method is used in more number of transactions\".\n"
        "The SQL query for the sub-question \"Find which payment method is used in more number of transactions\" is SELECT payment_method FROM master_txn_table GROUP BY payment_method ORDER BY count(distinct transaction_id) DESC LIMIT 1\n"
        "So, the answer to the question \"Return the most common payment method used for transactions.\" is =\n"
        "Intermediate_representation: SELECT master_txn_table.payment_method FROM master_txn_table GROUP BY master_txn_table.payment_method ORDER BY count(distinct master_txn_table.transaction_id) DESC LIMIT 1\n"
        "SQL: SELECT payment_method FROM master_txn_table GROUP BY payment_method ORDER BY count(distinct transaction_id) DESC LIMIT 1\n\n"
        'Q: "Who are my outstanding debtors or creditors?"\n'
        "Schema_links: [master_txn_table.customers,master_txn_table.open_balance,master_txn_table.vendor_name]\n"
        "A: Let's think step by step. \"Who are my outstanding debtors or creditors?\" can be solved by knowing the answer to the following sub-question \"How many customers' and vendors' open balance greater than 0?\".\n"
        "The SQL query for the sub-question \"How many customers' and vendors' open balance greater than 0?\" is select distinct customers from master_txn_table where open_balance > 0 union select distinct vendor_name from master_txn_table where open_balance > 0\n"
        "So, the answer to the question \"Who are my outstanding debtors or creditors?\" is =\n"
        "Intermediate_representation: select distinct master_txn_table.customers from master_txn_table where master_txn_table.open_balance > 0 union select distinct master_txn_table.vendor_name from master_txn_table where master_txn_table.open_balance > 0\n"
        "SQL: select distinct customers from master_txn_table where open_balance > 0 union select distinct vendor_name from master_txn_table where open_balance > 0\n\n"
        'Q: "How much did we pay Michael Vaughn the Last fiscal year?"\n'
        "Schema_links: [master_txn_table.debit,master_txn_table.vendor,master_txn_table.transaction_date,master_txn_table.account,chart_of_accounts.account_name,chart_of_accounts.account_type]\n"
        "A: Let's think step by step. \"How much did we pay Michael Vaughn the Last fiscal year?\" can be solved by knowing the answer to the following sub-question \"What are the amounts did we pay to Michael Vaughn in the Last fiscal year?\".\n"
        "The SQL query for the sub-question \"What are the amounts did we pay to Michael Vaughn in the Last fiscal year?\" is select sum(debit) from master_txn_table as T1 join chart_of_accounts as T2 on T1.account = T2.account_name where account_type in ('Expense', 'Other Expense') and vendor = \"Michael Vaughn\" and transaction_date BETWEEN date(current_date, '-3 months', 'start of year','-1 years', '+3 months') AND date(current_date, '-3 months', 'start of year','-1 years', '+3 months', '+1 years', '-1 days')\n"
        "So, the answer to the question \"How much did we pay Michael Vaughn the Last fiscal year?\" is =\n"
        "Intermediate_representation: select sum(master_txn_table.debit) from master_txn_table where chart_of_accounts.account_type in ('Expense', 'Other Expense') and master_txn_table.vendor = 'Michael Vaughn' and master_txn_table.transaction_date BETWEEN date(current_date, '-3 months', 'start of year','-1 years', '+3 months') AND date(current_date, '-3 months', 'start of year','-1 years', '+3 months', '+1 years', '-1 days')\n"
        "SQL: select sum(debit) from master_txn_table as T1 join chart_of_accounts as T2 on T1.account = T2.account_name where account_type in ('Expense', 'Other Expense') and vendor = 'Michael Vaughn' and transaction_date BETWEEN date(current_date, '-3 months', 'start of year','-1 years', '+3 months') AND date(current_date, '-3 months', 'start of year','-1 years', '+3 months', '+1 years', '-1 days')\n\n"
        'Q: "show me my product level revenue for this month vs last month"\n'
        "Schema_links: [master_txn_type.product_service,master_txn_type.transaction_date,master_txn_type.credit,master_txn_type.account,chart_of_accounts.account_name,chart_of_accounts.account_type]\n"
        "A: Let's think step by step. \"show me my product level revenue for this month vs last month\" can be solved by knowing the answer to the following sub-question \"What are the product level revenue for this month vs product level revenue for last month\".\n"
        "The SQL query for the sub-question \"What are the product level revenue for this month vs product level revenue for last month\" is select product_service, strftime('%m', transaction_date), sum(credit) from master_txn_table  as T1 join chart_of_accounts as T2 on T1.account = T2.account_name where account_type in ('Income','Other Income') and strftime('%m', transaction_date) >= strftime('%m', current_timestamp) - 1 group by product_service, strftime('%m', transaction_date)\n"
        "So, the answer to the question \"show me my product level revenue for this month vs last month\" is =\n"
        "Intermediate_representation: select master_txn_table.product_service, strftime('%m', master_txn_table.transaction_date), sum(master_txn_table.credit) from master_txn_table where chart_of_accounts.account_type in ('Income','Other Income') and strftime('%m', master_txn_table.transaction_date) >= strftime('%m', current_timestamp) - 1 group by master_txn_table.product_service, strftime('%m', master_txn_table.transaction_date)\n"
        "SQL: select product_service, strftime('%m', transaction_date), sum(credit) from master_txn_table  as T1 join chart_of_accounts as T2 on T1.account = T2.account_name where account_type in ('Income','Other Income') and strftime('%m', transaction_date) >= strftime('%m', current_timestamp) - 1 group by product_service, strftime('%m', transaction_date)\n\n"
        'Q: "What are Crystal Price recurring product purchases over past 6 months?"\n'
        "Schema_links: [master_txn_table.product_service,master_txn_table.customers,master_txn_table.transaction_date]\n"
        "A: Let's think step by step. \"What are Crystal Price recurring product purchases over past 6 months?\" can be solved by knowing the answer to the following sub-question \"What are the products purchased by customer Crystal Price in past over 6 months\".\n"
        "The SQL query for the sub-question \"What are the products purchased by customer Crystal Price in past over 6 months\" is select product_service from master_txn_table where customers = 'Crystal Price' and transaction_date BETWEEN date(current_date,'start of month','-6 month') and date(current_date,'start of month','-1 day') group by product_service having count(distinct strftime('%m', transaction_date)) = 6\n"
        "So, the answer to the question \"What are Crystal Price recurring product purchases over past 6 months?\" is =\n"
        "Intermediate_representation: select master_txn_table.product_service from master_txn_table where master_txn_table.customers = 'Crystal Price' and master_txn_table.transaction_date BETWEEN date(current_date,'start of month','-6 month') and date(current_date,'start of month','-1 day') group by master_txn_table.product_service having count(distinct strftime('%m', master_txn_table.transaction_date)) = 6\n"
        "SQL: select product_service from master_txn_table where customers = 'Crystal Price' and transaction_date BETWEEN date(current_date,'start of month','-6 month') and date(current_date,'start of month','-1 day') group by product_service having count(distinct strftime('%m', transaction_date)) = 6\n\n"
        'Q: "How much revenue came through Christine Stone in q3 last year"\n'
        "Schema_links: [master_txn_table.credit,master_txn_table.account,transaction_date,master_txn_table.customers,chart_of_accounts.account_name,chart_of_accounts.account_type]\n"
        "A: Let's think step by step. \"How much revenue came through Christine Stone in q3 last year\" can be solved by knowing the answer to the following sub-question \"How much we earn from Christine Stone in q3 last year?\".\n"
        "The SQL query for the sub-question \"How much we earn from Christine Stone in q3 last year?\" is select sum(credit) from master_txn_table  as T1 join chart_of_accounts as T2 on T1.account = T2.account_name where account_type in ('Income','Other Income') and  transaction_date BETWEEN date(current_date, '-1 year', 'start of year', '+6 month') AND date(current_date, '-1 year', 'start of year', '+9 month', '-1 day')  and T1.customers = 'Christine Stone'\n"
        "So, the answer to the question \"How much revenue came through Christine Stone in q3 last year\" is =\n"
        "Intermediate_representation: select sum(master_txn_table.credit) from master_txn_table where chart_of_accounts.account_type in ('Income','Other Income') and  master_txn_table.transaction_date BETWEEN date(current_date, '-1 year', 'start of year', '+6 month') AND date(current_date, '-1 year', 'start of year', '+9 month', '-1 day')  and master_txn_table.customers = 'Christine Stone'\n"
        "SQL: select sum(credit) from master_txn_table  as T1 join chart_of_accounts as T2 on T1.account = T2.account_name where account_type in ('Income','Other Income') and  transaction_date BETWEEN date(current_date, '-1 year', 'start of year', '+6 month') AND date(current_date, '-1 year', 'start of year', '+9 month', '-1 day')  and T1.customers = 'Christine Stone'\n"
    )

    # ------------------------------------------------------------------
    # Init
    # ------------------------------------------------------------------

    def __init__(
        self,
        dataset: Dataset = None,
        llm: Any = None,
        is_save: bool = True,
        save_dir: Union[str, PathLike] = "../files/pred_sql",
        **kwargs,
    ):
        self.dataset = dataset
        self.llm = llm
        self.is_save = is_save
        self.save_dir = save_dir

    # ------------------------------------------------------------------
    # Prompt builders
    # ------------------------------------------------------------------

    def easy_prompt_maker(self, question: str, schema: str, schema_links) -> str:
        instruction = "# Use the the schema links to generate the SQL queries for each of the questions.\n"
        return (
            instruction
            + schema + "\n"
            + self.EASY_PROMPT
            + 'Q: "' + question + '"\n'
            + "Schema_links: " + str(schema_links) + "\n"
            + "SQL:"
        )

    def medium_prompt_maker(self, question: str, schema: str, schema_links) -> str:
        instruction = "# Use the the schema links and Intermediate_representation to generate the SQL queries for each of the questions.\n"
        return (
            instruction
            + schema + "\n"
            + self.MEDIUM_PROMPT
            + 'Q: "' + question + '"\n'
            + "Schema_links: " + str(schema_links) + "\n"
            + "A: Let's think step by step."
        )

    def hard_prompt_maker(self, question: str, schema: str, schema_links, sub_questions: str) -> str:
        instruction = "# Use the intermediate representation and the schema links to generate the SQL queries for each of the questions.\n"
        stepping = (
            f'\nA: Let\'s think step by step. "{question}" can be solved by knowing the answer to the '
            f'following sub-question "{sub_questions}".'
        )
        return (
            instruction
            + schema + "\n"
            + self.HARD_PROMPT
            + 'Q: "' + question + '"'
            + "\nschema_links: " + str(schema_links)
            + stepping
            + '\nThe SQL query for the sub-question"'
        )

    # ------------------------------------------------------------------
    # Main act
    # ------------------------------------------------------------------

    def act(self, item, schema=None, schema_links=None, sub_questions=None, data_logger=None, **kwargs) -> str:
        if data_logger:
            data_logger.info(f"{self.NAME}.act start | item={item}")

        row = self.dataset[item]
        question = row["question"]
        instance_id = row.get("instance_id", str(item))

        # Load actual db schema (schema kwarg carries reducer output, not db schema)
        schema_items = self.dataset.get_db_schema(item)
        if schema_items is None:
            raise ValueError(f"No schema for item {item}")
        if isinstance(schema_items, dict):
            from core.data_manage import single_central_process
            schema_items = single_central_process(schema_items)

        fields = find_fields_mysql_like(schema_items)
        foreign_keys = find_foreign_keys_mysql_like(schema_items, row)
        schema_str = fields + "Foreign_keys = " + foreign_keys + "\n"

        # Load schema_links from row if not provided
        if schema_links is None:
            schema_links = row.get("schema_links", "[]")

        # Load predicted_class from row
        predicted_class = row.get("predicted_class", '"NESTED"')
        if data_logger:
            data_logger.info(f"{self.NAME}.predicted_class | {predicted_class}")

        # Load sub_questions from row if not provided
        if sub_questions is None:
            sub_questions = row.get("sub_questions", "What is the answer?")
        if not sub_questions:
            sub_questions = "What is the answer?"

        # Route to the appropriate prompt
        llm = self.get_llm()
        if llm is None:
            raise ValueError("LLM not initialised")

        if '"EASY"' in predicted_class:
            logger.debug(f"[{self.NAME}] EASY path for item {item}")
            prompt = self.easy_prompt_maker(question, schema_str, schema_links)
            sql = llm.complete(prompt).text.strip()
        elif '"NON-NESTED"' in predicted_class:
            logger.debug(f"[{self.NAME}] NON-NESTED path for item {item}")
            prompt = self.medium_prompt_maker(question, schema_str, schema_links)
            raw = llm.complete(prompt).text.strip()
            try:
                sql = raw.split("SQL: ")[1]
            except IndexError:
                logger.warning(f"[{self.NAME}] SQL split failed for NON-NESTED, using raw output")
                sql = raw
        else:
            logger.debug(f"[{self.NAME}] NESTED path for item {item}")
            prompt = self.hard_prompt_maker(question, schema_str, schema_links, sub_questions)
            raw = llm.complete(prompt).text.strip()
            try:
                sql = raw.split("SQL: ")[1]
            except IndexError:
                logger.warning(f"[{self.NAME}] SQL split failed for NESTED, using raw output")
                sql = raw

        sql = sql_clean(sql)

        if data_logger:
            data_logger.info(f"{self.NAME}.final_sql | {sql}")

        sql = self.save_output(sql, item, instance_id)

        if data_logger:
            data_logger.info(f"{self.NAME}.act end | item={item}")

        return sql

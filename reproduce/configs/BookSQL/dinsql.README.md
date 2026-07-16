# BookSQL/dinsql

<!--
Generated fields are bracketed by markers so tools can refresh them from the
reproduce config. Keep manual notes outside generated blocks.
-->

<!-- SQURVE:CONFIG-README:BEGIN -->
| Field | Value |
|---|---|
| Config | `reproduce/configs/BookSQL/dinsql.json` |
| Dataset | `BookSQL` |
| Method | `dinsql` |
| Run identifier | `BookSQL-dinsql` |
| Data source | `BookSQL:val:` |
| Schema source | `BookSQL:val` |
| LLM provider | `qwen` |
| LLM model | `qwen-turbo` |
| Generate num | `1` |
| Checkpoint | `enabled, interval=50` |

## Run

From the repository root:

```bash
python reproduce/run.py BookSQL dinsql
```

For smoke/debug runs, prefer changing only the third `data_source` segment (`<benchmark>:<split>:<filter>`) in the config, then run the same command.

## Workflow

| Task | Type | Actor binding | Eval | Snapshot |
| --- | --- | --- | --- | --- |
| dinsql_reduce | ReduceTask | reduce_type=DINSQLBooksqlReducer | reduce_recall, reduce_precision, reduce_rate | `../files/datasets/booksql_dinsql_dinsql_reduce.json` |
| dinsql_generate | GenerateTask | generate_type=DINSQLBooksqlGenerator | execute_accuracy | `../files/datasets/booksql_dinsql_dinsql_generate.json` |
| dinsql_selector | SelectTask | select_type=DINSQLBooksqlSelector | execute_accuracy | `../files/datasets/booksql_dinsql_dinsql_selector.json` |

## Outputs

| Name | Kind | Path |
| --- | --- | --- |
| dinsql_reduce | stage | `../files/datasets/booksql_dinsql_dinsql_reduce.json` |
| dinsql_generate | stage | `../files/datasets/booksql_dinsql_dinsql_generate.json` |
| dinsql_selector | stage | `../files/datasets/booksql_dinsql_dinsql_selector.json` |
| dinsql_full | workflow | `../files/datasets/booksql_dinsql_full.json` |
<!-- SQURVE:CONFIG-README:END -->

## Project Notes

- Purpose:
- Candidate/source reference:
- Expected run scale:
- Known prerequisites:

## Validation

```bash
python tools/verify.py reproduce-contract --path reproduce/configs/BookSQL/dinsql.json
```

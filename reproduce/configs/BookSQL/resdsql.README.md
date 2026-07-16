# BookSQL/resdsql

<!--
Generated fields are bracketed by markers so tools can refresh them from the
reproduce config. Keep manual notes outside generated blocks.
-->

<!-- SQURVE:CONFIG-README:BEGIN -->
| Field | Value |
|---|---|
| Config | `reproduce/configs/BookSQL/resdsql.json` |
| Dataset | `BookSQL` |
| Method | `resdsql` |
| Run identifier | `BookSQL-resdsql` |
| Data source | `BookSQL:val:` |
| Schema source | `BookSQL:val` |
| LLM provider | `qwen` |
| LLM model | `qwen-turbo` |
| Generate num | `1` |
| Checkpoint | `enabled, interval=50` |

## Run

From the repository root:

```bash
python reproduce/run.py BookSQL resdsql
```

For smoke/debug runs, prefer changing only the third `data_source` segment (`<benchmark>:<split>:<filter>`) in the config, then run the same command.

## Workflow

| Task | Type | Actor binding | Eval | Snapshot |
| --- | --- | --- | --- | --- |
| resdsql_reduce | ReduceTask | reduce_type=RESDSQLBooksqlReducer | reduce_recall, reduce_precision, reduce_rate | `../files/datasets/booksql_resdsql_resdsql_reduce.json` |
| resdsql_generate | GenerateTask | generate_type=RESDSQLBooksqlGenerator | execute_accuracy | `../files/datasets/booksql_resdsql_resdsql_generate.json` |

## Outputs

| Name | Kind | Path |
| --- | --- | --- |
| resdsql_reduce | stage | `../files/datasets/booksql_resdsql_resdsql_reduce.json` |
| resdsql_generate | stage | `../files/datasets/booksql_resdsql_resdsql_generate.json` |
| resdsql_full | workflow | `../files/datasets/booksql_resdsql_full.json` |
<!-- SQURVE:CONFIG-README:END -->

## Project Notes

- Purpose:
- Candidate/source reference:
- Expected run scale:
- Known prerequisites:

## Validation

```bash
python tools/verify.py reproduce-contract --path reproduce/configs/BookSQL/resdsql.json
```

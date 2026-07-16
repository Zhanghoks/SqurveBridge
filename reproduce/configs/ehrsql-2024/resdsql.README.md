# ehrsql-2024/resdsql

<!--
Generated fields are bracketed by markers so tools can refresh them from the
reproduce config. Keep manual notes outside generated blocks.
-->

<!-- SQURVE:CONFIG-README:BEGIN -->
| Field | Value |
|---|---|
| Config | `reproduce/configs/ehrsql-2024/resdsql.json` |
| Dataset | `ehrsql-2024` |
| Method | `resdsql` |
| Run identifier | `ehrsql-2024-resdsql` |
| Data source | `ehrsql-2024:valid:` |
| Schema source | `ehrsql-2024:valid` |
| LLM provider | `qwen` |
| LLM model | `qwen-turbo` |
| Generate num | `1` |
| Checkpoint | `enabled, interval=50` |

## Run

From the repository root:

```bash
python reproduce/run.py ehrsql-2024 resdsql
```

For smoke/debug runs, prefer changing only the third `data_source` segment (`<benchmark>:<split>:<filter>`) in the config, then run the same command.

## Workflow

| Task | Type | Actor binding | Eval | Snapshot |
| --- | --- | --- | --- | --- |
| resdsql_parse | ParseTask | parse_type=RESDSQLParser | schema_linking_eval | `../files/datasets/ehrsql_2024_resdsql_resdsql_parse.json` |
| resdsql_reduce | ReduceTask | reduce_type=RESDSQLReducer | reduce_recall, reduce_precision, reduce_rate | `../files/datasets/ehrsql_2024_resdsql_resdsql_reduce.json` |
| resdsql_generate | GenerateTask | generate_type=RESDSQLGenerator | execute_accuracy | `../files/datasets/ehrsql_2024_resdsql_resdsql_generate.json` |

## Outputs

| Name | Kind | Path |
| --- | --- | --- |
| resdsql_parse | stage | `../files/datasets/ehrsql_2024_resdsql_resdsql_parse.json` |
| resdsql_reduce | stage | `../files/datasets/ehrsql_2024_resdsql_resdsql_reduce.json` |
| resdsql_generate | stage | `../files/datasets/ehrsql_2024_resdsql_resdsql_generate.json` |
| resdsql_full | workflow | `../files/datasets/ehrsql_2024_resdsql_full.json` |
<!-- SQURVE:CONFIG-README:END -->

## Project Notes

- Purpose:
- Candidate/source reference:
- Expected run scale:
- Known prerequisites:

## Validation

```bash
python tools/verify.py reproduce-contract --path reproduce/configs/ehrsql-2024/resdsql.json
```

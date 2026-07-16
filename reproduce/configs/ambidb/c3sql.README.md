# ambidb/c3sql

<!--
Generated fields are bracketed by markers so tools can refresh them from the
reproduce config. Keep manual notes outside generated blocks.
-->

<!-- SQURVE:CONFIG-README:BEGIN -->
| Field | Value |
|---|---|
| Config | `reproduce/configs/ambidb/c3sql.json` |
| Dataset | `ambidb` |
| Method | `c3sql` |
| Run identifier | `ambidb-c3sql` |
| Data source | `ambidb:all:` |
| Schema source | `ambidb:all` |
| LLM provider | `qwen` |
| LLM model | `qwen-turbo` |
| Generate num | `1` |
| Checkpoint | `enabled, interval=50` |

## Run

From the repository root:

```bash
python reproduce/run.py ambidb c3sql
```

For smoke/debug runs, prefer changing only the third `data_source` segment (`<benchmark>:<split>:<filter>`) in the config, then run the same command.

## Workflow

| Task | Type | Actor binding | Eval | Snapshot |
| --- | --- | --- | --- | --- |
| c3sql_reduce | ReduceTask | reduce_type=C3SQLReducer | reduce_recall, reduce_precision, reduce_rate | `../files/datasets/ambidb_c3sql_c3sql_reduce.json` |
| c3sql_parse | ParseTask | parse_type=C3SQLParser | parse_recall, parse_precision, parse_exact_matching | `../files/datasets/ambidb_c3sql_c3sql_parse.json` |
| c3sql_generate | GenerateTask | generate_type=C3SQLGenerator | execute_accuracy | `../files/datasets/ambidb_c3sql_c3sql_generate.json` |

## Outputs

| Name | Kind | Path |
| --- | --- | --- |
| c3sql_reduce | stage | `../files/datasets/ambidb_c3sql_c3sql_reduce.json` |
| c3sql_parse | stage | `../files/datasets/ambidb_c3sql_c3sql_parse.json` |
| c3sql_generate | stage | `../files/datasets/ambidb_c3sql_c3sql_generate.json` |
| c3sql_full | workflow | `../files/datasets/ambidb_c3sql_full.json` |
<!-- SQURVE:CONFIG-README:END -->

## Project Notes

- Purpose:
- Candidate/source reference:
- Expected run scale:
- Known prerequisites:

## Validation

```bash
python tools/verify.py reproduce-contract --path reproduce/configs/ambidb/c3sql.json
```

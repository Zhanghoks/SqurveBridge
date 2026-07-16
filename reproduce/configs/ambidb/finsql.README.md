# ambidb/finsql

<!--
Generated fields are bracketed by markers so tools can refresh them from the
reproduce config. Keep manual notes outside generated blocks.
-->

<!-- SQURVE:CONFIG-README:BEGIN -->
| Field | Value |
|---|---|
| Config | `reproduce/configs/ambidb/finsql.json` |
| Dataset | `ambidb` |
| Method | `finsql` |
| Run identifier | `ambidb-finsql` |
| Data source | `ambidb:all:` |
| Schema source | `ambidb:all` |
| LLM provider | `qwen` |
| LLM model | `qwen-turbo` |
| Generate num | `1` |
| Checkpoint | `enabled, interval=50` |

## Run

From the repository root:

```bash
python reproduce/run.py ambidb finsql
```

For smoke/debug runs, prefer changing only the third `data_source` segment (`<benchmark>:<split>:<filter>`) in the config, then run the same command.

## Workflow

| Task | Type | Actor binding | Eval | Snapshot |
| --- | --- | --- | --- | --- |
| finsql_reduce | ReduceTask | reduce_type=FINSQLReducer | reduce_recall, reduce_precision, reduce_rate | `../files/datasets/ambidb_finsql_finsql_reduce.json` |
| finsql_generate | GenerateTask | generate_type=FINSQLGenerator | execute_accuracy | `../files/datasets/ambidb_finsql_finsql_generate.json` |
| finsql_selector | SelectTask | select_type=FINSQLSelector | execute_accuracy | `../files/datasets/ambidb_finsql_finsql_selector.json` |

## Outputs

| Name | Kind | Path |
| --- | --- | --- |
| finsql_reduce | stage | `../files/datasets/ambidb_finsql_finsql_reduce.json` |
| finsql_generate | stage | `../files/datasets/ambidb_finsql_finsql_generate.json` |
| finsql_selector | stage | `../files/datasets/ambidb_finsql_finsql_selector.json` |
| finsql_full | workflow | `../files/datasets/ambidb_finsql_full.json` |
<!-- SQURVE:CONFIG-README:END -->

## Project Notes

- Purpose:
- Candidate/source reference:
- Expected run scale:
- Known prerequisites:

## Validation

```bash
python tools/verify.py reproduce-contract --path reproduce/configs/ambidb/finsql.json
```

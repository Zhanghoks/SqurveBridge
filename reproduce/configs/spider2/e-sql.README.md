# spider2/e-sql

<!--
Generated fields are bracketed by markers so tools can refresh them from the
reproduce config. Keep manual notes outside generated blocks.
-->

<!-- SQURVE:CONFIG-README:BEGIN -->
| Field | Value |
|---|---|
| Config | `reproduce/configs/spider2/e-sql.json` |
| Dataset | `spider2` |
| Method | `e-sql` |
| Run identifier | `spider2-e-sql` |
| Data source | `spider2:lite:` |
| Schema source | `spider2:lite` |
| LLM provider | `qwen` |
| LLM model | `qwen-turbo` |
| Generate num | `1` |
| Checkpoint | `enabled, interval=50` |

## Run

From the repository root:

```bash
python reproduce/run.py spider2 e-sql
```

For smoke/debug runs, prefer changing only the third `data_source` segment (`<benchmark>:<split>:<filter>`) in the config, then run the same command.

## Workflow

| Task | Type | Actor binding | Eval | Snapshot |
| --- | --- | --- | --- | --- |
| esql_generate | GenerateTask | generate_type=ESQLGenerator | execute_accuracy | `../files/datasets/spider2_e_sql_esql_generate.json` |

## Outputs

| Name | Kind | Path |
| --- | --- | --- |
| esql_generate | stage | `../files/datasets/spider2_e_sql_esql_generate.json` |
<!-- SQURVE:CONFIG-README:END -->

## Project Notes

- Purpose:
- Candidate/source reference:
- Expected run scale:
- Known prerequisites:

## Validation

```bash
python tools/verify.py reproduce-contract --path reproduce/configs/spider2/e-sql.json
```

# bird/dinsql

<!--
Generated fields are bracketed by markers so tools can refresh them from the
reproduce config. Keep manual notes outside generated blocks.
-->

<!-- SQURVE:CONFIG-README:BEGIN -->
| Field | Value |
|---|---|
| Config | `reproduce/configs/bird/dinsql.json` |
| Dataset | `bird` |
| Method | `dinsql` |
| Run identifier | `bird-dinsql` |
| Data source | `bird:dev:` |
| Schema source | `bird:dev` |
| LLM provider | `qwen` |
| LLM model | `qwen-turbo` |
| Generate num | `1` |
| Checkpoint | `enabled, interval=50` |

## Run

From the repository root:

```bash
python reproduce/run.py bird dinsql
```

For smoke/debug runs, prefer changing only the third `data_source` segment (`<benchmark>:<split>:<filter>`) in the config, then run the same command.

## Workflow

| Task | Type | Actor binding | Eval | Snapshot |
| --- | --- | --- | --- | --- |
| dinsql_generate | GenerateTask | generate_type=DINSQLGenerator | execute_accuracy | `../files/datasets/bird_dinsql_dinsql_generate.json` |

## Outputs

| Name | Kind | Path |
| --- | --- | --- |
| dinsql_generate | stage | `../files/datasets/bird_dinsql_dinsql_generate.json` |
<!-- SQURVE:CONFIG-README:END -->

## Project Notes

- Purpose:
- Candidate/source reference:
- Expected run scale:
- Known prerequisites:

## Validation

```bash
python tools/verify.py reproduce-contract --path reproduce/configs/bird/dinsql.json
```

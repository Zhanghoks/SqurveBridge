# bull-en/dinsql

<!--
Generated fields are bracketed by markers so tools can refresh them from the
reproduce config. Keep manual notes outside generated blocks.
-->

<!-- SQURVE:CONFIG-README:BEGIN -->
| Field | Value |
|---|---|
| Config | `reproduce/configs/bull-en/dinsql.json` |
| Dataset | `bull-en` |
| Method | `dinsql` |
| Run identifier | `bull-en-dinsql` |
| Data source | `bull-en:dev:` |
| Schema source | `bull-en:dev` |
| LLM provider | `qwen` |
| LLM model | `qwen-turbo` |
| Generate num | `1` |
| Checkpoint | `enabled, interval=50` |

## Run

From the repository root:

```bash
python reproduce/run.py bull-en dinsql
```

For smoke/debug runs, prefer changing only the third `data_source` segment (`<benchmark>:<split>:<filter>`) in the config, then run the same command.

## Workflow

| Task | Type | Actor binding | Eval | Snapshot |
| --- | --- | --- | --- | --- |
| dinsql_generate | GenerateTask | generate_type=DINSQLGenerator | execute_accuracy | `../files/datasets/bull_en_dinsql_dinsql_generate.json` |

## Outputs

| Name | Kind | Path |
| --- | --- | --- |
| dinsql_generate | stage | `../files/datasets/bull_en_dinsql_dinsql_generate.json` |
<!-- SQURVE:CONFIG-README:END -->

## Project Notes

- Purpose:
- Candidate/source reference:
- Expected run scale:
- Known prerequisites:

## Validation

```bash
python tools/verify.py reproduce-contract --path reproduce/configs/bull-en/dinsql.json
```

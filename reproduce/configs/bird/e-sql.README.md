# bird/e-sql

<!--
Generated fields are bracketed by markers so tools can refresh them from the
reproduce config. Keep manual notes outside generated blocks.
-->

<!-- SQURVE:CONFIG-README:BEGIN -->
| Field | Value |
|---|---|
| Config | `reproduce/configs/bird/e-sql.json` |
| Dataset | `bird` |
| Method | `e-sql` |
| Run identifier | `bird-e-sql` |
| Data source | `bird:dev:` |
| Schema source | `bird:dev` |
| LLM provider | `qwen` |
| LLM model | `deepseek-v4-flash` |
| Generate num | `1` |
| Checkpoint | `enabled, interval=50` |

## Run

From the repository root:

```bash
python reproduce/run.py bird e-sql
```

For smoke/debug runs, prefer changing only the third `data_source` segment (`<benchmark>:<split>:<filter>`) in the config, then run the same command.

## Workflow

| Task | Type | Actor binding | Eval | Snapshot |
| --- | --- | --- | --- | --- |
| generate | GenerateTask | generate_type=ESQLGenerator | execute_accuracy | `../files/datasets/bird_esql.json` |

## Outputs

| Name | Kind | Path |
| --- | --- | --- |
| generate | stage | `../files/datasets/bird_esql.json` |
<!-- SQURVE:CONFIG-README:END -->

## Project Notes

- Purpose:
- Candidate/source reference:
- Expected run scale:
- Known prerequisites:

## Validation

```bash
python tools/verify.py reproduce-contract --path reproduce/configs/bird/e-sql.json
```


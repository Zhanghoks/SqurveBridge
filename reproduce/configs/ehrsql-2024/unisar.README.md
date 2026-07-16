# ehrsql-2024/unisar

<!--
Generated fields are bracketed by markers so tools can refresh them from the
reproduce config. Keep manual notes outside generated blocks.
-->

<!-- SQURVE:CONFIG-README:BEGIN -->
| Field | Value |
|---|---|
| Config | `reproduce/configs/ehrsql-2024/unisar.json` |
| Dataset | `ehrsql-2024` |
| Method | `unisar` |
| Run identifier | `ehrsql-2024-unisar` |
| Data source | `ehrsql-2024:valid:` |
| Schema source | `ehrsql-2024:valid` |
| LLM provider | `qwen` |
| LLM model | `qwen-turbo` |
| Generate num | `1` |
| Checkpoint | `enabled, interval=50` |

## Run

From the repository root:

```bash
python reproduce/run.py ehrsql-2024 unisar
```

For smoke/debug runs, prefer changing only the third `data_source` segment (`<benchmark>:<split>:<filter>`) in the config, then run the same command.

## Workflow

| Task | Type | Actor binding | Eval | Snapshot |
| --- | --- | --- | --- | --- |
| unisar_reduce | ReduceTask | reduce_type=UNISARBooksqlReducer | reduce_recall, reduce_precision, reduce_rate | `../files/datasets/ehrsql_2024_unisar_unisar_reduce.json` |
| unisar_generate | GenerateTask | generate_type=UNISARBooksqlGenerator | execute_accuracy | `../files/datasets/ehrsql_2024_unisar_unisar_generate.json` |
| unisar_selector | SelectTask | select_type=UNISARBooksqlSelector | execute_accuracy | `../files/datasets/ehrsql_2024_unisar_unisar_selector.json` |

## Outputs

| Name | Kind | Path |
| --- | --- | --- |
| unisar_reduce | stage | `../files/datasets/ehrsql_2024_unisar_unisar_reduce.json` |
| unisar_generate | stage | `../files/datasets/ehrsql_2024_unisar_unisar_generate.json` |
| unisar_selector | stage | `../files/datasets/ehrsql_2024_unisar_unisar_selector.json` |
| unisar_full | workflow | `../files/datasets/ehrsql_2024_unisar_full.json` |
<!-- SQURVE:CONFIG-README:END -->

## Project Notes

- Purpose:
- Candidate/source reference:
- Expected run scale:
- Known prerequisites:

## Validation

```bash
python tools/verify.py reproduce-contract --path reproduce/configs/ehrsql-2024/unisar.json
```

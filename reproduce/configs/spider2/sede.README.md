# spider2/sede

<!--
Generated fields are bracketed by markers so tools can refresh them from the
reproduce config. Keep manual notes outside generated blocks.
-->

<!-- SQURVE:CONFIG-README:BEGIN -->
| Field | Value |
|---|---|
| Config | `reproduce/configs/spider2/sede.json` |
| Dataset | `spider2` |
| Method | `sede` |
| Run identifier | `spider2-sede` |
| Data source | `spider2:lite:` |
| Schema source | `spider2:lite` |
| LLM provider | `qwen` |
| LLM model | `qwen-turbo` |
| Generate num | `1` |
| Checkpoint | `enabled, interval=50` |

## Run

From the repository root:

```bash
python reproduce/run.py spider2 sede
```

For smoke/debug runs, prefer changing only the third `data_source` segment (`<benchmark>:<split>:<filter>`) in the config, then run the same command.

## Workflow

| Task | Type | Actor binding | Eval | Snapshot |
| --- | --- | --- | --- | --- |
| sede_reduce | ReduceTask | reduce_type=SEDEReducer | reduce_recall, reduce_precision, reduce_rate | `../files/datasets/spider2_sede_sede_reduce.json` |
| sede_generate | GenerateTask | generate_type=SEDEGenerator | execute_accuracy | `../files/datasets/spider2_sede_sede_generate.json` |

## Outputs

| Name | Kind | Path |
| --- | --- | --- |
| sede_reduce | stage | `../files/datasets/spider2_sede_sede_reduce.json` |
| sede_generate | stage | `../files/datasets/spider2_sede_sede_generate.json` |
| sede_full | workflow | `../files/datasets/spider2_sede_full.json` |
<!-- SQURVE:CONFIG-README:END -->

## Project Notes

- Purpose:
- Candidate/source reference:
- Expected run scale:
- Known prerequisites:

## Validation

```bash
python tools/verify.py reproduce-contract --path reproduce/configs/spider2/sede.json
```

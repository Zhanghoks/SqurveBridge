# spider/gpt-baseline

<!--
Generated fields are bracketed by markers so tools can refresh them from the
reproduce config. Keep manual notes outside generated blocks.
-->

<!-- SQURVE:CONFIG-README:BEGIN -->
| Field | Value |
|---|---|
| Config | `reproduce/configs/spider/gpt-baseline.json` |
| Dataset | `spider` |
| Method | `gpt-baseline` |
| Run identifier | `spider-gpt-baseline` |
| Data source | `spider:dev:` |
| Schema source | `spider:dev` |
| LLM provider | `qwen` |
| LLM model | `qwen-turbo` |
| Generate num | `1` |
| Checkpoint | `enabled, interval=50` |

## Run

From the repository root:

```bash
python reproduce/run.py spider gpt-baseline
```

For smoke/debug runs, prefer changing only the third `data_source` segment (`<benchmark>:<split>:<filter>`) in the config, then run the same command.

## Workflow

| Task | Type | Actor binding | Eval | Snapshot |
| --- | --- | --- | --- | --- |
| gpt_baseline_generate | GenerateTask | generate_type=EHRGenerator | execute_accuracy | `../files/datasets/spider_gpt_baseline_gpt_baseline_generate.json` |

## Outputs

| Name | Kind | Path |
| --- | --- | --- |
| gpt_baseline_generate | stage | `../files/datasets/spider_gpt_baseline_gpt_baseline_generate.json` |
<!-- SQURVE:CONFIG-README:END -->

## Project Notes

- Purpose:
- Candidate/source reference:
- Expected run scale:
- Known prerequisites:

## Validation

```bash
python tools/verify.py reproduce-contract --path reproduce/configs/spider/gpt-baseline.json
```

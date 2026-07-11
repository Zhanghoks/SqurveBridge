# {{ title }}

<!--
Generated fields are bracketed by markers so tools can refresh them from the
reproduce config. Keep manual notes outside generated blocks.
-->

<!-- SQURVE:CONFIG-README:BEGIN -->
| Field | Value |
|---|---|
| Config | `{{ config_path }}` |
| Dataset | `{{ dataset }}` |
| Method | `{{ method }}` |
| Run identifier | `{{ run_id }}` |
| Data source | `{{ data_source }}` |
| Schema source | `{{ schema_source }}` |
| LLM provider | `{{ llm_provider }}` |
| LLM model | `{{ llm_model }}` |
| Generate num | `{{ generate_num }}` |
| Checkpoint | `{{ checkpoint }}` |

## Run

From the repository root:

```bash
{{ run_command }}
```

{{ smoke_guidance }}

## Workflow

{{ workflow_table }}

## Outputs

{{ outputs_table }}
<!-- SQURVE:CONFIG-README:END -->

## Project Notes

- Purpose:
- Candidate/source reference:
- Expected run scale:
- Known prerequisites:

## Validation

```bash
python tools/verify.py reproduce-contract --path {{ config_path }}
```

---
name: evaluator-report
description: 汇总 scores.json，写 report.md，判断是否进入 Meta-Evo MCTS 自进化。/run 完成后可选触发。
internal_only: true
parent_skill: integration-pipeline
parent_phase: Phase 5
disable-model-invocation: true
---

# Evaluator Report

**接收**：`artifacts/<dataset>-<method>-YYYYMMDD-HHMMSS/scores.json`（由 `python reproduce/run.py <dataset> <method>` 生成）
**产出**：同一 artifact 目录下的 `report.md` + `weakness_profile.md` → 可选触发 `/meta-evo`
模板：`templates/evaluation/`、`templates/report/evaluator-report.md`

---

## 交互门控

写 `artifacts/<run_id>/report-spec-draft.md`（指标、阈值、是否建议 self-improve）→ SPEC_REVIEW → report.md。

---

## Steps

1. 确认 reproduce run 完成，读取最新 `artifacts/<dataset>-<method>-*/scores.json`。
2. 若没有 `scores.json`，不得退回旧 `runs/eval-result` 或 stdout 估算；用 `tools/eval_scores.py` 从 reproduce saved datasets、pred_sql、config 重建。
3. 调用 `tools/profile_weakness.py` 生成 `weakness_profile.md`。
4. 写 `report-spec-draft.md`，包含 EX/EM/CF1/FD/stage/workflow attribution/SQL feature/QVT/token/error_root 摘要。
5. SPEC_REVIEW → approve → 写 `report.md`。
6. 阈值判断 → 询问是否进入 `/meta-evo`。

## Meta-Evo Gate

建议触发 Meta-Evo 的条件：
- 目标指标低于用户阈值；
- `error_root_distribution` 有明确 top 根因；
- `by_hardness` 或 `by_db_type` 暴露稳定短板；
- 没有 execution_error 大面积污染评估。

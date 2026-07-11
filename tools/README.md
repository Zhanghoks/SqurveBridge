# Squrve Tools

`tools/` 存放 Squrve skills 与 agents 调用的确定性脚本。原则：

- skill 负责语义判断、源码阅读、接入决策和人工报告。
- tool 负责固定、可复用、无 LLM 判断的状态管理和校验。
- 所有命令从**仓库根目录**执行。

当前工具：

- `artifact_state.py`: 管理 reader、细粒度 adapter stage、最终 adapter 与 run 状态；
  `validate-reader-artifacts` / `validate-integration-dag` / `adapter-plan`（DAG 调度）；
  `complete-reader` 前强制通过 reader 校验。
- `verify.py`: 提供 Actor syntax/import、provider 注册、Task 分支、RAG 索引、
  few-shot 示例、reproduce config、benchmark 注册与 reader-artifacts 校验；评估统一由 `reproduce/run.py` 产出 artifact。
- `reproduce_contract.py`: 生成/校验 `reproduce/configs/<dataset>/<method>.README.md`，
  并提供 `verify.py reproduce-contract` 使用的静态 reproduce workspace 合同检查。
- `eval_scores.py`: 对已保存的 reproduce 输出运行带明细评估，组装并写出 `scores.json`。
- `delta_report.py`: 对比两份 `scores.json`，输出 Markdown delta 报告和 JSON verdict。
- `profile_weakness.py`: 从 `scores.json` 生成 Meta-Evo 可读的弱点画像 Markdown，并可用 `--json-output` 写结构化 `weakness-profile.json`。
- `mcts/orchestrator.py`: tools 边界下的 MCTS 搜索入口，转发到 `reproduce.metrics.mcts.orchestrator`。

# Task 5 Report: Evidence, Diagnose and Improve

## Scope

- Track: metric- and artifact-backed diagnosis and bounded improvement.
- Hypothesis: persisted comparison/archive fields can drive the Diagnose and Improve modules without inferred metrics or synthetic improvement state.
- Evidence: `/api/comparisons/latest/results` and `/api/archive`.
- Target: the isolated `full-flow-bilingual-demo` worktree in the public SqurveBridge repository.

## RED

- `npm test --prefix demo-app -- EvidenceWorkspace.test.js`
  - Failed with `ERR_MODULE_NOT_FOUND` for `DiagnosisWorkspace.jsx`, confirming the evidence modules did not exist.
- `python -m unittest tests.test_space_api.SpaceApiTests.test_comparison_results_expose_only_sanitized_sample_diagnostics -v`
  - Failed with `KeyError: 'by_hardness'`, confirming the comparison response lacked the required diagnostic serialization.

## GREEN

- `npm test --prefix demo-app -- EvidenceWorkspace.test.js`
  - Passed: 47 tests, 0 failures.
- `python -m unittest tests.test_space_api -v`
  - Passed: 18 tests, 0 failures.
- `npm run build --prefix demo-app`
  - Passed: Vite production build completed successfully.
- `git diff --check`
  - Passed with no whitespace errors.

## Evidence and Safety Contract

- Diagnosis reads only `errors`, `by_hardness`, `by_sql_feature`, `stage_metrics`, `latency`, and sanitized `samples`.
- Each serialized sample is restricted to `instance_id`, `db_id`, `hardness`, `ex`, `error_root`, `error_sub`, `sl_recall`, and `act_elapsed_s`.
- The API regression asserts that `question`, `gold_sql`, and `pred_sql` are absent from the complete JSON response.
- No persisted diagnostic fields produces an explicit score-bundle empty state.
- Improvement reads only explicit `weakness`/`weakness_profile` and `evolution`/`evolution_record` fields.
- Improvement renders only Baseline, Weakness Profile, Candidate Change, Smoke, Bounded Evaluation, Confirmation, and Human Review records; unrecognized stages are ignored.

## Staging and Commit

- Frontend Task 5 files and bilingual dictionary integrations are staged as complete files.
- `demo/api_server.py` and `tests/test_space_api.py` are staged interactively by hunk.
- The pre-task snapshots in `.superpowers/sdd/task-5-before-*.py` are used to verify that only Task 5 serialization/test hunks differ from the captured auth work.
- `git diff --cached` shows no custom-model auth validation or auth regression changes.
- Commit subject: `feat: add evidence-backed diagnosis modules`.

## Attention

- The passing frontend run reports React `act(...)` warnings from pre-existing synchronous `MatrixStudio.test.js` assertions while the new evidence hook settles asynchronously; there are no test failures.
- The Python run reports the environment's existing incompatible `pyarrow` warning from the Snowflake connector; there are no test failures.
- No screenshot was captured in this task; production compilation is verified, and visual QA can be performed with the integrated full-flow demo.

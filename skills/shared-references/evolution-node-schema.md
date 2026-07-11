# Evolution Node Schema

Each candidate node writes `node.json` under `artifacts/evolve/<evolve_slug>/nodes/<node_id>/`.

Copy/fill skeleton: `templates/evolution/node.json`.

Required fields:

- `node_id`: stable id such as `n001_schema_linking`
- `parent_id`: `baseline` or a previous node id
- `branch_id`: numeric branch id for diversity and stagnation
- `stage`: `improve`, `debug`, `fusion`, `aggregate`, `smoke`, `bounded`, or `full`
- `method`: reproduce method slug
- `benchmark`: reproduce dataset slug
- `target_dimensions`: metrics or weaknesses targeted by this node
- `change_scope`: prompt, config, adapter, actor, evaluator, or runtime
- `allowed_scope`: list of allowed edit areas
- `plan_path`: usually `change-plan.md`
- `patch_path`: usually `patch.diff`
- `run_command_path`: usually `run-command.sh`
- `fitness`: numeric fitness after evaluation, or null before evaluation
- `status`: `planned`, `running`, `pass`, `buggy`, `reverted`, or `recommended`
- `decision`: `candidate`, `smoke_promoted`, `full_confirmation`, `accept`, `continue`, or `rollback`

Candidate artifacts should also include `delta.json`, `status.json`, smoke/bounded scores when available, and an evaluator report when generated.

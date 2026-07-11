#!/usr/bin/env python3
"""Generate and validate reproduce config README contracts.

The reproduce workspace contract is intentionally deterministic: it reads a
config JSON, derives stable run facts, and owns only the generated README block.
Manual project notes live outside the generated markers.
"""

from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parent.parent
CONFIG_ROOT = PROJECT_ROOT / "reproduce" / "configs"
TEMPLATE_PATH = PROJECT_ROOT / "templates" / "reproduce" / "config-readme.md"
BEGIN_MARKER = "<!-- SQURVE:CONFIG-README:BEGIN -->"
END_MARKER = "<!-- SQURVE:CONFIG-README:END -->"
REQUIRED_TOP_LEVEL = ("api_key", "llm", "dataset", "database", "task", "engine", "generate_num")
PATH_KEYS = {
    # Compatibility keys without a _path/_dir suffix that still carry paths.
    "bird_root",
    "data_source_dir",
    "dataset_save_dir",
    "db_path",
    "few_shot_path",
    "generate_save_dir",
    "parse_save_dir",
    "reduce_save_dir",
    "save_dir",
    "schema_source_dir",
    "sql_save_dir",
    "stage_dataset_save_path",
    "vector_store",
}
OUTPUT_PATH_KEYS = {
    "dataset_save_dir",
    "dataset_save_path",
    "generate_save_dir",
    "parse_save_dir",
    "reduce_save_dir",
    "save_dir",
    "sql_save_dir",
    "stage_dataset_save_path",
}


@dataclass(frozen=True)
class ConfigFacts:
    path: Path
    repo_path: str
    dataset: str
    method: str
    run_id: str
    data_source: str
    schema_source: str
    llm_provider: str
    llm_model: str
    generate_num: Any
    checkpoint: str
    run_command: str
    workflow_rows: list[dict[str, str]]
    output_rows: list[dict[str, str]]


class ContractError(Exception):
    """A deterministic reproduce contract violation."""


def read_json(path: Path) -> Any:
    try:
        with path.open(encoding="utf-8") as handle:
            return json.load(handle)
    except json.JSONDecodeError as exc:
        raise ContractError(f"{path}: invalid JSON: {exc}") from exc


def repo_relative(path: Path) -> str:
    return path.resolve().relative_to(PROJECT_ROOT).as_posix()


def readme_path_for(config_path: Path) -> Path:
    return config_path.with_suffix(".README.md")


def is_runnable_config(path: Path) -> bool:
    if path.name == "template.json":
        return False
    data = read_json(path)
    if not isinstance(data, dict):
        return False
    task = data.get("task")
    engine = data.get("engine")
    if not isinstance(task, dict) or not isinstance(engine, dict):
        return False
    task_meta = task.get("task_meta")
    exec_process = engine.get("exec_process")
    return bool(task_meta) and bool(exec_process)


def discover_configs() -> list[Path]:
    paths = []
    for path in sorted(CONFIG_ROOT.glob("*/*.json")):
        try:
            if is_runnable_config(path):
                paths.append(path)
        except ContractError:
            paths.append(path)
    return paths


def _path_parts(config_path: Path) -> tuple[str, str]:
    try:
        rel = config_path.resolve().relative_to(CONFIG_ROOT)
    except ValueError as exc:
        raise ContractError(f"{config_path}: must be under {repo_relative(CONFIG_ROOT)}") from exc
    parts = rel.parts
    if len(parts) != 2 or not parts[1].endswith(".json"):
        raise ContractError(
            f"{config_path}: expected reproduce/configs/<dataset>/<method>.json"
        )
    return parts[0], Path(parts[1]).stem


def validate_config_shape(config_path: Path, config: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    for key in REQUIRED_TOP_LEVEL:
        if key not in config:
            errors.append(f"missing top-level section: {key}")

    llm = config.get("llm")
    if not isinstance(llm, dict):
        errors.append("llm must be an object")
    else:
        provider = llm.get("use")
        if not provider:
            errors.append("llm.use is required")
        if not llm.get("model_name"):
            errors.append("llm.model_name is required")
        api_key = config.get("api_key")
        if not isinstance(api_key, dict):
            errors.append("api_key must be an object")
        elif provider and provider not in api_key:
            errors.append(f"api_key must include active llm provider: {provider}")

    dataset = config.get("dataset")
    if not isinstance(dataset, dict):
        errors.append("dataset must be an object")
    elif not dataset.get("data_source"):
        errors.append("dataset.data_source is required")
    elif not _valid_source_identifier(dataset.get("data_source"), require_filter=True):
        errors.append(
            "dataset.data_source must be <benchmark>:<split>:<filter> or a local JSON path"
        )

    database = config.get("database")
    if not isinstance(database, dict):
        errors.append("database must be an object")
    elif not database.get("schema_source"):
        errors.append("database.schema_source is required")
    elif not _valid_source_identifier(database.get("schema_source"), require_filter=False):
        errors.append("database.schema_source must be <benchmark>:<split> or <benchmark>:<split>:")

    task = config.get("task")
    task_meta = task.get("task_meta") if isinstance(task, dict) else None
    cpx_meta = task.get("cpx_task_meta", []) if isinstance(task, dict) else []
    if not isinstance(task, dict):
        errors.append("task must be an object")
        task_meta = []
    if not isinstance(task_meta, list) or not task_meta:
        errors.append("task.task_meta must be a non-empty list")
        task_meta = []
    if not isinstance(cpx_meta, list):
        errors.append("task.cpx_task_meta must be a list when present")
        cpx_meta = []

    task_ids: set[str] = set()
    for index, item in enumerate(task_meta):
        prefix = f"task.task_meta[{index}]"
        if not isinstance(item, dict):
            errors.append(f"{prefix} must be an object")
            continue
        task_id = item.get("task_id")
        if not task_id:
            errors.append(f"{prefix}.task_id is required")
        elif task_id in task_ids:
            errors.append(f"duplicate task_id: {task_id}")
        else:
            task_ids.add(str(task_id))
        if not item.get("task_type"):
            errors.append(f"{prefix}.task_type is required")
        if item.get("is_save_dataset") is not True:
            errors.append(f"{prefix}.is_save_dataset must be true")
        if not item.get("dataset_save_path"):
            errors.append(f"{prefix}.dataset_save_path is required")
        elif not _valid_workspace_output(item.get("dataset_save_path")):
            errors.append(
                f"{prefix}.dataset_save_path should stay under reproduce workspace outputs"
            )
        data_source = item.get("data_source")
        if data_source and not _valid_source_identifier(data_source, require_filter=True):
            errors.append(f"{prefix}.data_source must be <benchmark>:<split>:<filter>")
        schema_source = item.get("schema_source")
        if schema_source and not _valid_source_identifier(schema_source, require_filter=False):
            errors.append(f"{prefix}.schema_source must be <benchmark>:<split> or <benchmark>:<split>:")
        eval_type = item.get("eval_type")
        if not isinstance(eval_type, list) or not eval_type:
            errors.append(f"{prefix}.eval_type must be a non-empty list")
        meta_task = item.get("meta", {}).get("task") if isinstance(item.get("meta"), dict) else None
        if not isinstance(meta_task, dict) or not meta_task:
            errors.append(f"{prefix}.meta.task must name the actor class binding")

    cpx_ids: set[str] = set()
    for index, item in enumerate(cpx_meta):
        prefix = f"task.cpx_task_meta[{index}]"
        if not isinstance(item, dict):
            errors.append(f"{prefix} must be an object")
            continue
        task_id = item.get("task_id")
        if not task_id:
            errors.append(f"{prefix}.task_id is required")
        else:
            cpx_ids.add(str(task_id))
        task_lis = item.get("task_lis")
        if not isinstance(task_lis, list) or not task_lis:
            errors.append(f"{prefix}.task_lis must be a non-empty list")
        else:
            for child in task_lis:
                if child not in task_ids:
                    errors.append(f"{prefix}.task_lis references unknown task_id: {child}")
        if item.get("is_save_dataset") is False:
            errors.append(f"{prefix}.is_save_dataset should not be false")
        if not item.get("dataset_save_path"):
            errors.append(f"{prefix}.dataset_save_path is required for workflow snapshots")
        elif not _valid_workspace_output(item.get("dataset_save_path")):
            errors.append(
                f"{prefix}.dataset_save_path should stay under reproduce workspace outputs"
            )

    engine = config.get("engine")
    exec_process = engine.get("exec_process") if isinstance(engine, dict) else None
    if not isinstance(engine, dict):
        errors.append("engine must be an object")
    elif not isinstance(exec_process, list) or not exec_process:
        errors.append("engine.exec_process must be a non-empty list")
    else:
        allowed = task_ids | cpx_ids | {"~p"}
        for item in exec_process:
            if item not in allowed:
                errors.append(f"engine.exec_process references unknown task: {item}")

    checkpoint = config.get("checkpoint")
    if checkpoint is not None and not isinstance(checkpoint, dict):
        errors.append("checkpoint must be an object when present")
    elif isinstance(checkpoint, dict) and checkpoint.get("enabled") and not checkpoint.get("interval"):
        errors.append("checkpoint.interval is required when checkpoint.enabled is true")

    try:
        dataset_name, _ = _path_parts(config_path)
    except ContractError as exc:
        errors.append(str(exc))
    else:
        ds_source = config.get("dataset", {}).get("data_source")
        if isinstance(ds_source, str) and ds_source and not ds_source.endswith(".json"):
            source_dataset = ds_source.split(":", 1)[0]
            if source_dataset != dataset_name:
                errors.append(
                    f"dataset.data_source benchmark {source_dataset!r} does not match path dataset {dataset_name!r}"
                )

    errors.extend(_validate_path_fields(config))
    errors.extend(_validate_external_eval(config_path, config))
    return errors


def _validate_external_eval(config_path: Path, config: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    external_eval = config.get("external_eval")
    if external_eval is None:
        return errors
    if not isinstance(external_eval, dict):
        return ["external_eval must be an object when present"]

    enabled = external_eval.get("enabled", False)
    if enabled is not True:
        return errors

    adapters = external_eval.get("adapters")
    if not isinstance(adapters, list):
        return ["external_eval.adapters must be a list when external_eval.enabled is true"]

    enabled_adapters = [
        (index, adapter)
        for index, adapter in enumerate(adapters)
        if isinstance(adapter, dict) and adapter.get("enabled") is True
    ]
    if not enabled_adapters:
        errors.append("external_eval.enabled true requires at least one enabled adapter")

    try:
        _, method_name = _path_parts(config_path)
    except ContractError as exc:
        return errors + [str(exc)]

    for index, adapter in enumerate(adapters):
        prefix = f"external_eval.adapters[{index}]"
        if not isinstance(adapter, dict):
            errors.append(f"{prefix} must be an object")
            continue
        if adapter.get("enabled") is not True:
            continue

        metric_id = adapter.get("id")
        source_artifact = adapter.get("source_artifact")
        if not metric_id:
            errors.append(f"{prefix}.id is required for enabled external metric adapters")
        if not source_artifact:
            errors.append(
                f"{prefix}.source_artifact is required for enabled external metric adapters"
            )
            continue

        artifact_path = _project_path(source_artifact)
        if artifact_path is None:
            errors.append(f"{prefix}.source_artifact must resolve inside the project workspace")
            continue
        if not _is_canonical_metric_spec_path(artifact_path, method_name):
            errors.append(
                f"{prefix}.source_artifact must be artifacts/{method_name}/metric/spec.json"
            )
            continue
        if not artifact_path.exists():
            errors.append(f"{prefix}.source_artifact does not exist: {source_artifact}")
            continue
        if not artifact_path.is_file():
            errors.append(f"{prefix}.source_artifact must be a JSON file: {source_artifact}")
            continue

        spec = _read_metric_spec(artifact_path, prefix)
        if not isinstance(spec, dict):
            errors.append(str(spec))
            continue
        if spec.get("confirmed_by_user") is not True:
            errors.append(f"{prefix}.source_artifact must have confirmed_by_user: true")
        if spec.get("enabled") is not True:
            errors.append(f"{prefix}.source_artifact must have enabled: true")
        if metric_id and spec.get("metric_id") != metric_id:
            errors.append(
                f"{prefix}.id {metric_id!r} must match metric/spec.json metric_id {spec.get('metric_id')!r}"
            )

    return errors


def _is_canonical_metric_spec_path(path: Path, method_name: str) -> bool:
    try:
        rel = path.resolve().relative_to(PROJECT_ROOT.resolve())
    except ValueError:
        return False
    return rel.parts == ("artifacts", method_name, "metric", "spec.json")


def _project_path(value: Any) -> Path | None:
    if not isinstance(value, str) or not value:
        return None
    path = Path(value)
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    resolved = path.resolve()
    if not _is_relative_to(resolved, PROJECT_ROOT):
        return None
    return resolved


def _read_metric_spec(path: Path, prefix: str) -> dict[str, Any] | str:
    try:
        data = read_json(path)
    except (ContractError, OSError) as exc:
        return f"{prefix}.source_artifact invalid metric spec JSON: {exc}"
    if not isinstance(data, dict):
        return f"{prefix}.source_artifact metric spec must be an object"
    return data


def _validate_path_fields(value: Any, prefix: str = "") -> list[str]:
    errors: list[str] = []
    if isinstance(value, dict):
        for key, child in value.items():
            child_prefix = f"{prefix}.{key}" if prefix else key
            if isinstance(child, (dict, list)):
                errors.extend(_validate_path_fields(child, child_prefix))
            elif _is_path_key(key) and isinstance(child, str) and child:
                if _is_output_path_key(key):
                    valid = _valid_workspace_output(child)
                    message = f"{child_prefix} should stay under reproduce workspace outputs: {child}"
                else:
                    valid = _path_stays_in_project(child)
                    message = f"{child_prefix} must resolve inside the project workspace: {child}"
                if not valid:
                    errors.append(message)
    elif isinstance(value, list):
        for index, child in enumerate(value):
            errors.extend(_validate_path_fields(child, f"{prefix}[{index}]"))
    return errors


def _is_path_key(key: str) -> bool:
    return key in PATH_KEYS or key.endswith("_path") or key.endswith("_dir")


def _is_output_path_key(key: str) -> bool:
    return key in OUTPUT_PATH_KEYS or key.endswith("_save_path") or key.endswith("_save_dir")


def _path_stays_in_project(value: str) -> bool:
    path = Path(value)
    if not path.is_absolute():
        path = PROJECT_ROOT / "reproduce" / path
    return _is_relative_to(path.resolve(), PROJECT_ROOT)


def _valid_source_identifier(value: Any, require_filter: bool) -> bool:
    if not isinstance(value, str) or not value:
        return False
    normalized = value.replace("\\", "/")
    if normalized.endswith(".json"):
        path = Path(normalized)
        if not path.is_absolute():
            path = PROJECT_ROOT / "reproduce" / path
        return _is_relative_to(path.resolve(), PROJECT_ROOT)
    parts = value.split(":")
    if require_filter:
        return len(parts) == 3 and bool(parts[0]) and bool(parts[1])
    if len(parts) == 2:
        return bool(parts[0]) and bool(parts[1])
    return len(parts) == 3 and bool(parts[0]) and bool(parts[1]) and parts[2] == ""


def _valid_workspace_output(value: Any) -> bool:
    if not isinstance(value, str) or not value:
        return False
    path = Path(value)
    if path.is_absolute():
        return False
    resolved = (PROJECT_ROOT / "reproduce" / path).resolve()
    allowed_roots = (
        PROJECT_ROOT / "files",
        PROJECT_ROOT / "artifacts",
    )
    return any(_is_relative_to(resolved, root) for root in allowed_roots)


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root.resolve())
        return True
    except ValueError:
        return False


def extract_facts(config_path: Path) -> ConfigFacts:
    data = read_json(config_path)
    if not isinstance(data, dict):
        raise ContractError(f"{config_path}: reproduce config must be a JSON object")
    errors = validate_config_shape(config_path, data)
    if errors:
        joined = "\n  - ".join(errors)
        raise ContractError(f"{repo_relative(config_path)} contract errors:\n  - {joined}")

    dataset, method = _path_parts(config_path)
    task = data["task"]
    task_meta = task.get("task_meta", [])
    cpx_meta = task.get("cpx_task_meta", [])
    task_by_id = {item["task_id"]: item for item in task_meta}
    cpx_by_id = {item["task_id"]: item for item in cpx_meta}
    workflow_rows: list[dict[str, str]] = []
    output_rows: list[dict[str, str]] = []

    for exec_item in data["engine"]["exec_process"]:
        if exec_item == "~p":
            continue
        if exec_item in cpx_by_id:
            cpx = cpx_by_id[exec_item]
            for child in cpx.get("task_lis", []):
                stage = task_by_id[child]
                workflow_rows.append(_task_row(stage))
                output_rows.append(_output_row(stage))
            output_rows.append(
                {
                    "name": cpx["task_id"],
                    "kind": "workflow",
                    "path": str(cpx.get("dataset_save_path", "")),
                }
            )
        else:
            stage = task_by_id[exec_item]
            workflow_rows.append(_task_row(stage))
            output_rows.append(_output_row(stage))

    checkpoint = data.get("checkpoint") or {}
    if checkpoint.get("enabled"):
        checkpoint_text = f"enabled, interval={checkpoint.get('interval', 'unknown')}"
    else:
        checkpoint_text = "disabled"

    return ConfigFacts(
        path=config_path,
        repo_path=repo_relative(config_path),
        dataset=dataset,
        method=method,
        run_id=f"{dataset}-{method}",
        data_source=str(data["dataset"].get("data_source", "")),
        schema_source=str(data["database"].get("schema_source", "")),
        llm_provider=str(data["llm"].get("use", "")),
        llm_model=str(data["llm"].get("model_name", "")),
        generate_num=data.get("generate_num", 1),
        checkpoint=checkpoint_text,
        run_command=f"python reproduce/run.py {dataset} {method}",
        workflow_rows=workflow_rows,
        output_rows=output_rows,
    )


def _task_row(item: dict[str, Any]) -> dict[str, str]:
    task_meta = item.get("meta", {}).get("task", {})
    actor = ", ".join(f"{key}={value}" for key, value in sorted(task_meta.items()))
    return {
        "task_id": str(item.get("task_id", "")),
        "task_type": str(item.get("task_type", "")),
        "actor": actor or "-",
        "eval_type": ", ".join(item.get("eval_type", [])) or "-",
        "save_path": str(item.get("dataset_save_path", "")),
    }


def _output_row(item: dict[str, Any]) -> dict[str, str]:
    return {
        "name": str(item.get("task_id", "")),
        "kind": "stage",
        "path": str(item.get("dataset_save_path", "")),
    }


def markdown_table(headers: list[str], rows: list[list[str]]) -> str:
    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join("---" for _ in headers) + " |",
    ]
    for row in rows:
        lines.append("| " + " | ".join(_escape_cell(value) for value in row) + " |")
    return "\n".join(lines)


def _escape_cell(value: Any) -> str:
    return str(value).replace("|", "\\|").replace("\n", " ")


def render_readme(facts: ConfigFacts) -> str:
    template = TEMPLATE_PATH.read_text(encoding="utf-8")
    workflow = markdown_table(
        ["Task", "Type", "Actor binding", "Eval", "Snapshot"],
        [
            [
                row["task_id"],
                row["task_type"],
                row["actor"],
                row["eval_type"],
                f"`{row['save_path']}`",
            ]
            for row in facts.workflow_rows
        ],
    )
    outputs = markdown_table(
        ["Name", "Kind", "Path"],
        [[row["name"], row["kind"], f"`{row['path']}`"] for row in facts.output_rows],
    )
    replacements = {
        "title": f"{facts.dataset}/{facts.method}",
        "config_path": facts.repo_path,
        "dataset": facts.dataset,
        "method": facts.method,
        "run_id": facts.run_id,
        "data_source": facts.data_source,
        "schema_source": facts.schema_source,
        "llm_provider": facts.llm_provider,
        "llm_model": facts.llm_model,
        "generate_num": str(facts.generate_num),
        "checkpoint": facts.checkpoint,
        "run_command": facts.run_command,
        "smoke_guidance": _smoke_guidance(facts.data_source),
        "workflow_table": workflow,
        "outputs_table": outputs,
    }
    rendered = template
    for key, value in replacements.items():
        rendered = rendered.replace("{{ " + key + " }}", value)
    return rendered


def _smoke_guidance(data_source: str) -> str:
    if data_source.replace("\\", "/").endswith(".json"):
        return (
            "This config uses a local JSON slice as `dataset.data_source`. For "
            "smoke/debug runs, regenerate or replace that slice with another "
            "project-local JSON file, then run the same command."
        )
    return (
        "For smoke/debug runs, prefer changing only the third `data_source` "
        "segment (`<benchmark>:<split>:<filter>`) in the config, then run the "
        "same command."
    )


def generated_block(markdown: str) -> str:
    match = re.search(
        re.escape(BEGIN_MARKER) + r".*?" + re.escape(END_MARKER),
        markdown,
        flags=re.DOTALL,
    )
    if not match:
        raise ContractError("generated README block markers are missing")
    return match.group(0).strip()


def merge_generated(existing: str, rendered: str) -> str:
    rendered_block = generated_block(rendered)
    pattern = re.escape(BEGIN_MARKER) + r".*?" + re.escape(END_MARKER)
    if re.search(pattern, existing, flags=re.DOTALL):
        return re.sub(pattern, rendered_block, existing, flags=re.DOTALL)
    return rendered


def generate_one(config_path: Path, check: bool = False) -> bool:
    facts = extract_facts(config_path)
    rendered = render_readme(facts)
    target = readme_path_for(config_path)
    if target.exists():
        desired = merge_generated(target.read_text(encoding="utf-8"), rendered)
    else:
        desired = rendered

    if check:
        if not target.exists():
            raise ContractError(f"{repo_relative(config_path)}: README missing at {repo_relative(target)}")
        current = target.read_text(encoding="utf-8")
        if current != desired:
            raise ContractError(f"{repo_relative(target)} is out of date; run generate-readmes")
        return False

    changed = not target.exists() or target.read_text(encoding="utf-8") != desired
    if changed:
        target.write_text(desired, encoding="utf-8")
    return changed


def validate_one(config_path: Path) -> None:
    generate_one(config_path, check=True)


def command_generate(args: argparse.Namespace) -> None:
    paths = discover_configs() if args.all else [Path(args.path)]
    changed = 0
    for path in paths:
        if generate_one(path):
            changed += 1
            print(f"updated {repo_relative(readme_path_for(path))}")
    print(f"generated README contract for {len(paths)} config(s); changed={changed}")


def command_validate(args: argparse.Namespace) -> None:
    paths = discover_configs() if args.all else [Path(args.path)]
    failures: list[str] = []
    for path in paths:
        try:
            validate_one(path)
        except ContractError as exc:
            failures.append(str(exc))
    if failures:
        raise SystemExit("reproduce contract failed:\n- " + "\n- ".join(failures))
    print(f"reproduce contract OK: {len(paths)} config(s)")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("generate-readmes", help="generate per-config README files")
    group = p.add_mutually_exclusive_group(required=True)
    group.add_argument("--path", help="single reproduce config path")
    group.add_argument("--all", action="store_true", help="all runnable reproduce configs")
    p.set_defaults(func=command_generate)

    p = sub.add_parser("validate", help="validate config shape and README generated block")
    group = p.add_mutually_exclusive_group(required=True)
    group.add_argument("--path", help="single reproduce config path")
    group.add_argument("--all", action="store_true", help="all runnable reproduce configs")
    p.set_defaults(func=command_validate)

    return parser


def main() -> None:
    args = build_parser().parse_args()
    try:
        args.func(args)
    except ContractError as exc:
        raise SystemExit(str(exc)) from exc


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Manage Squrve2.0 Claude artifact state from skill workflows.

This tool intentionally keeps deterministic bookkeeping out of SKILL.md files.
Run all commands from the Squrve repository root.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


TZ = timezone(timedelta(hours=8))
PLACEHOLDER_KEYS = {"your_api_key_here", "", None}
SUCCESS_STATUSES = frozenset({"done", "inline"})
DONE_STAGE_STATUSES = frozenset({"done", "inline"})
ACTOR_LAYERS = (
    "generator",
    "parser",
    "reducer",
    "scaler",
    "decomposer",
    "optimizer",
    "selector",
    "agent",
)
STAGE_ALIASES = {
    "llm-provider": "llm_provider",
    "benchmark-data": "benchmark_data",
    "db-backend": "db_backend",
    "external-knowledge": "external",
    "config": "adapter",
}
for _alias_key, _alias_value in list(STAGE_ALIASES.items()):
    STAGE_ALIASES.setdefault(_alias_key.replace("-", "_"), _alias_value)
METHOD_STAGES = (
    "llm_provider",
    "embedding",
    "prompt",
    "rag",
    "few_shot",
    "external",
    "actor",
    "workflow",
)
DATABASE_STAGES = (
    "benchmark_data",
    "sysconfig",
    "schema",
    "db_backend",
    "credential",
    "embedding",
    "rag",
    "few_shot",
    "external",
)
EXPLORATION_FILES = (
    "squrve-inventory.md",
    "squrve-coverage.json",
    "candidate-inventory.md",
    "candidate-coverage.json",
    "mapping-matrix.md",
)
PIPELINE_STAGE_TO_ACTOR_LAYER = {
    "reduce": "reducer",
    "parse": "parser",
    "generate": "generator",
    "scale": "scaler",
    "decompose": "decomposer",
    "optimize": "optimizer",
    "select": "selector",
    "agent": "agent",
}
ALLOWED_PIPELINE_STAGES = frozenset(PIPELINE_STAGE_TO_ACTOR_LAYER)
# Two valid total orders: reduce→parse (LLM-based linking after pruning)
# or parse→reduce (classifier-based linking before pruning).
# Both produce intermediate artifacts that feed into generate.
VALID_PIPELINE_ORDERS = (
    ("reduce", "parse", "decompose", "scale", "generate", "optimize", "select", "agent"),
    ("parse", "reduce", "decompose", "scale", "generate", "optimize", "select", "agent"),
)
IO_INTERMEDIATE_ARTIFACTS = frozenset({
    "instance_schemas",
    "schema_links",
    "sub_questions",
    "pred_sql_candidates",
})
IO_ARTIFACT_TO_LAYER = {
    "instance_schemas": "reducer",
    "schema_links": "parser",
    "sub_questions": "decomposer",
    "pred_sql_candidates": "scaler",
    "pred_sql": "generator",
}
COVERAGE_SKIP_DIR_NAMES = frozenset({
    ".git",
    "__pycache__",
    ".venv",
    "venv",
    "node_modules",
    ".pytest_cache",
    ".mypy_cache",
    ".tox",
    "dist",
    "build",
})
COVERAGE_SCAN_SUFFIXES = frozenset({".py", ".sh", ".bash"})
COVERAGE_CONFIG_NAMES = frozenset({
    "requirements.txt",
    "setup.py",
    "pyproject.toml",
    "makefile",
    "dockerfile",
})
COVERAGE_MODULE_REQUIRED_KEYS = ("id", "files", "summary", "squrve_component", "inputs", "outputs", "io_artifact")
COMPONENT_NEEDS_FIELDS: dict[str, tuple[str, ...]] = {
    "llm": ("needs_new_provider", "needs_factory_branch"),
    "embedding": ("needs_new_embed_model",),
    "prompt": ("needs_prompt_class", "needs_schema_linking_prompt"),
    "rag": ("needs_new_retrieval_strategy", "needs_new_schema_linking_mode"),
    "few_shot": ("needs_new_db_type_examples", "needs_new_retrieve_logic"),
    "external": ("needs_new_function",),
}
DEFAULT_SYS_CONFIG = Path("config/sys_config.json")
MAIN_BRANCHES = frozenset({"main", "master"})


def current_git_branch() -> str | None:
    override = os.environ.get("SQURVE_GIT_BRANCH")
    if override is not None:
        return override.strip() or None
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return None
    branch = result.stdout.strip()
    if branch == "HEAD":
        return None
    return branch


def is_allowed_method_branch(slug: str, branch: str) -> bool:
    if branch in MAIN_BRANCHES:
        return False
    allowed = {
        f"integrate/{slug}",
        f"feature/integrate-{slug}",
        f"feature/integrate/{slug}",
        f"feature/{slug}",
    }
    prefixes = (
        f"integrate/{slug}-",
        f"feature/{slug}-",
        f"feature/{slug}/",
        f"feature/integrate-{slug}-",
    )
    return branch in allowed or any(branch.startswith(p) for p in prefixes)


def git_dev_settings(slug: str) -> dict[str, Any]:
    path = state_path(slug)
    if not path.exists():
        return {}
    state = read_json(path)
    git = state.get("git")
    return git if isinstance(git, dict) else {}


def main_dev_allowed(slug: str) -> bool:
    settings = git_dev_settings(slug)
    return settings.get("allow_main") is True and settings.get("dev_mode") == "main"


def persist_dev_mode(slug: str, mode: str) -> None:
    if mode not in {"main", "branch", "worktree"}:
        raise SystemExit(f"invalid dev mode: {mode}")
    path = state_path(slug)
    state = read_json(path) if path.exists() else {}
    state["git"] = {
        "dev_mode": mode,
        "allow_main": mode == "main",
        "set_at": now_iso(),
    }
    write_json(path, state)


def resolve_allow_main(slug: str, *, allow_main_flag: bool = False) -> bool:
    return allow_main_flag or main_dev_allowed(slug)


def require_method_integration_branch(slug: str, *, allow_main: bool = False) -> None:
    branch = current_git_branch()
    if resolve_allow_main(slug, allow_main_flag=allow_main) and branch in MAIN_BRANCHES:
        print(
            f"WARN: method '{slug}' 在 '{branch}' 开发（用户已选择 Main 模式；Actor 改动进入共享主干）"
        )
        print(f"branch OK: {branch} (allow_main)")
        return
    if branch is None:
        raise SystemExit(
            "method 接入须在命名 git 分支或 worktree 上进行，不得在 detached HEAD 或非 git 目录开发。"
            f"\nBranch 模式: git checkout -b feature/{slug}-debug-<date>"
            f"\nWorktree 模式: git worktree add ../squrve-{slug} -b feature/{slug}-<date> main"
            f"\nMain 模式: artifact_state.py set-dev-mode --slug {slug} --mode main"
        )
    if branch in MAIN_BRANCHES:
        raise SystemExit(
            f"method '{slug}' 禁止在 '{branch}' 分支开发（未登记 Main 模式）。"
            f"\nBranch 模式: git checkout -b feature/{slug}-debug-<date>"
            f"\nWorktree 模式: git worktree add ../squrve-{slug} -b feature/{slug}-<date> main"
            f"\n或用户确认 Main 模式: set-dev-mode --slug {slug} --mode main"
        )
    if not is_allowed_method_branch(slug, branch):
        print(
            f"WARN: 当前分支 '{branch}' 非推荐命名 "
            f"(feature/{slug}-*、feature/{slug}/<date>、integrate/{slug})，继续执行"
        )
    print(f"branch OK: {branch}")


def set_dev_mode_cmd(args: argparse.Namespace) -> None:
    persist_dev_mode(args.slug, args.mode)
    print(f"dev_mode={args.mode} slug={args.slug} allow_main={args.mode == 'main'}")


def check_branch(args: argparse.Namespace) -> None:
    if args.type == "method":
        allow = resolve_allow_main(args.slug, allow_main_flag=getattr(args, "allow_main", False))
        if getattr(args, "allow_main", False):
            persist_dev_mode(args.slug, "main")
        require_method_integration_branch(args.slug, allow_main=allow)
        return
    branch = current_git_branch()
    if branch and branch not in MAIN_BRANCHES:
        print(f"branch OK: {branch} (database 可在 main，当前非 main)")
    else:
        print(f"branch OK: {branch or 'unknown'} (database 可在 main 接入)")


CASCADE = {
    "llm_provider": (
        "embedding", "prompt", "rag", "few_shot", "external", "actor",
        "workflow", "adapter",
    ),
    "embedding": ("rag", "few_shot", "adapter"),
    "prompt": ("adapter",),
    "rag": ("few_shot", "adapter"),
    "few_shot": ("adapter",),
    "external": ("adapter",),
    "actor": ("workflow", "adapter"),
    "workflow": ("adapter",),
    "benchmark_data": (
        "sysconfig", "schema", "db_backend", "credential", "rag",
        "few_shot", "external", "adapter",
    ),
    "sysconfig": ("adapter",),
    "schema": ("adapter",),
    "db_backend": ("adapter",),
    "credential": ("adapter",),
}
STAGE_TO_SKILL: dict[str, str] = {
    "llm_provider": "llm-provider-adapter",
    "embedding": "embedding-adapter",
    "prompt": "prompt-adapter",
    "rag": "retrieval-adapter",
    "few_shot": "retrieval-adapter",
    "external": "external-knowledge-adapter",
    "actor": "actor-adapter",
    "workflow": "workflow-adapter",
    "adapter": "config-adapter",
    "benchmark_data": "benchmark-data-adapter",
    "sysconfig": "sysconfig-adapter",
    "schema": "schema-adapter",
    "db_backend": "db-backend-adapter",
    "credential": "credential-adapter",
}
INTEGRATION_TERMINAL_STAGE = "adapter"


def stages_for_type(candidate_type: str) -> tuple[str, ...]:
    return METHOD_STAGES if candidate_type == "method" else DATABASE_STAGES


def active_stages_from_components(manifest: dict[str, Any]) -> set[str]:
    components = grouped_components(manifest)
    candidate_type = manifest["type"]
    active = {
        stage
        for stage in stages_for_type(candidate_type)
        if component_is_required(components, stage)
    }
    active.add(INTEGRATION_TERMINAL_STAGE)
    return active


def integration_dag_raw(manifest: dict[str, Any]) -> dict[str, list[str]]:
    integration = manifest.get("integration")
    if not isinstance(integration, dict):
        raise SystemExit("manifest requires integration object with dag")
    dag = integration.get("dag")
    if not isinstance(dag, dict) or not dag:
        raise SystemExit("manifest requires integration.dag")
    normalized: dict[str, list[str]] = {}
    for stage, requires in dag.items():
        key = canonical_stage(str(stage))
        if not isinstance(requires, list):
            raise SystemExit(f"integration.dag.{key} must be a list")
        normalized[key] = [canonical_stage(str(dep)) for dep in requires]
    return normalized


def derive_default_integration_dag(manifest: dict[str, Any]) -> dict[str, list[str]]:
    """Minimal semantic deps only — parallel starts allowed; not a fixed pipeline."""
    active = active_stages_from_components(manifest)
    dag = {stage: [] for stage in active if stage != INTEGRATION_TERMINAL_STAGE}
    if "workflow" in dag and "actor" in dag:
        dag["workflow"] = ["actor"]
    if "rag" in dag and "embedding" in dag:
        dag["rag"] = ["embedding"]
    if "few_shot" in dag and "rag" in dag:
        dag["few_shot"] = ["rag"]
    if manifest["type"] == "database" and "benchmark_data" in dag:
        for stage in list(dag):
            if stage != "benchmark_data" and not dag[stage]:
                dag[stage] = ["benchmark_data"]
    dag[INTEGRATION_TERMINAL_STAGE] = sorted(
        stage for stage in active if stage != INTEGRATION_TERMINAL_STAGE
    )
    return dag


def load_integration_dag(manifest: dict[str, Any]) -> dict[str, list[str]]:
    try:
        return integration_dag_raw(manifest)
    except SystemExit:
        return derive_default_integration_dag(manifest)


def _validate_integration_dag(manifest: dict[str, Any]) -> None:
    dag = load_integration_dag(manifest)
    candidate_type = manifest["type"]
    allowed = set(stages_for_type(candidate_type)) | {INTEGRATION_TERMINAL_STAGE}
    active = active_stages_from_components(manifest)

    unknown = sorted(set(dag) - allowed)
    if unknown:
        raise SystemExit(f"integration.dag has unknown stages: {unknown}")

    missing_active = sorted(active - set(dag))
    if missing_active:
        raise SystemExit(
            f"integration.dag missing active stages: {missing_active}"
        )

    for stage, requires in dag.items():
        unknown_deps = sorted(set(requires) - allowed)
        if unknown_deps:
            raise SystemExit(
                f"integration.dag.{stage} has unknown requires: {unknown_deps}"
            )
        for dep in requires:
            if dep not in active:
                raise SystemExit(
                    f"integration.dag.{stage} requires inactive stage {dep}"
                )

    if INTEGRATION_TERMINAL_STAGE not in dag:
        raise SystemExit("integration.dag must include adapter")

    adapter_requires = set(dag[INTEGRATION_TERMINAL_STAGE])
    expected_adapter_requires = active - {INTEGRATION_TERMINAL_STAGE}
    if adapter_requires != expected_adapter_requires:
        raise SystemExit(
            "integration.dag.adapter must require all other active stages: "
            f"expected {sorted(expected_adapter_requires)}, "
            f"got {sorted(adapter_requires)}"
        )

    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(node: str) -> None:
        if node in visiting:
            raise SystemExit(f"integration.dag cycle detected at {node}")
        if node in visited:
            return
        visiting.add(node)
        for dep in dag.get(node, []):
            visit(dep)
        visiting.remove(node)
        visited.add(node)

    for node in dag:
        visit(node)


def topological_sort_dag(dag: dict[str, list[str]]) -> list[str]:
    """Return a topological order for integration.dag.

    ``dag[stage]`` lists *prerequisites* — stages that must be done before
    ``stage`` (see adapter-integration-dag.md). Kahn's algorithm therefore
    sets ``indegree[stage] = len(dag[stage])`` (prerequisite count per node).
    """
    nodes = set(dag)
    for stage, requires in dag.items():
        unknown = sorted(set(requires) - nodes)
        if unknown:
            raise SystemExit(
                f"integration.dag.{stage} requires unknown stages: {unknown}"
            )

    indegree = {node: len(requires) for node, requires in dag.items()}
    dependents: dict[str, list[str]] = {node: [] for node in dag}
    for node, requires in dag.items():
        for dep in requires:
            dependents[dep].append(node)

    queue = sorted(node for node, degree in indegree.items() if degree == 0)
    order: list[str] = []
    while queue:
        node = queue.pop(0)
        order.append(node)
        for child in sorted(dependents[node]):
            indegree[child] -= 1
            if indegree[child] == 0:
                queue.append(child)
                queue.sort()
    if len(order) != len(dag):
        raise SystemExit("integration.dag cycle detected during topological sort")
    return order


def downstream_stages(dag: dict[str, list[str]], stage: str) -> set[str]:
    dependents: dict[str, set[str]] = {node: set() for node in dag}
    for node, requires in dag.items():
        for dep in requires:
            dependents.setdefault(dep, set()).add(node)
    seen: set[str] = set()
    stack = list(dependents.get(stage, ()))

    while stack:
        current = stack.pop()
        if current in seen:
            continue
        seen.add(current)
        stack.extend(dependents.get(current, ()))
    return seen


def _workflow_actor_layers_ready(state: dict[str, Any]) -> None:
    actor = state.get("actor")
    if not actor:
        return
    for layer, layer_state in actor.get("layers", {}).items():
        if layer_state is not None and layer_state.get("status") not in SUCCESS_STATUSES:
            raise SystemExit(f"actor layer {layer} not done: {layer_state.get('status')}")


def require_integration_dependencies(
    state: dict[str, Any],
    manifest: dict[str, Any],
    stage: str,
) -> None:
    dag = load_integration_dag(manifest)
    if stage not in dag:
        raise SystemExit(f"stage {stage} missing from integration.dag")
    for dep in dag[stage]:
        if state.get(dep) is None:
            continue
        require_status(state, dep)
    if stage == "workflow":
        _workflow_actor_layers_ready(state)


def ready_integration_stages(
    state: dict[str, Any],
    manifest: dict[str, Any],
) -> list[str]:
    dag = load_integration_dag(manifest)
    order = topological_sort_dag(dag)
    ready: list[str] = []
    for stage in order:
        if stage == INTEGRATION_TERMINAL_STAGE:
            continue
        current = state.get(stage)
        if current is None:
            continue
        if status_ok(state, stage):
            continue
        try:
            require_integration_dependencies(state, manifest, stage)
        except SystemExit:
            continue
        ready.append(stage)
    return ready


def adapter_plan(args: argparse.Namespace) -> None:
    state = load_state(args.slug)
    manifest = read_json(manifest_path(args.slug))
    _validate_integration_dag(manifest)
    dag = load_integration_dag(manifest)

    ready = ready_integration_stages(state, manifest)
    for stage in ready:
        skill = STAGE_TO_SKILL.get(stage, stage)
        print(f"READY_STAGE={stage}")
        print(f"READY_SKILL={skill}")

    adapter_state = state.get(INTEGRATION_TERMINAL_STAGE, {})
    adapter_pending = (
        isinstance(adapter_state, dict)
        and adapter_state.get("status") != "done"
    )
    if adapter_pending:
        try:
            require_integration_dependencies(state, manifest, INTEGRATION_TERMINAL_STAGE)
            print("ADAPTER_READY=true")
        except SystemExit as exc:
            print(f"ADAPTER_READY=false")
            print(f"ADAPTER_BLOCKER={exc}")

    if not ready and not adapter_pending:
        print("INTEGRATION_COMPLETE=true")
    elif not ready:
        print("READY_STAGE=")
        print("READY_SKILL=")


def validate_integration_dag_cmd(args: argparse.Namespace) -> None:
    manifest = read_json(manifest_path(args.slug))
    if manifest.get("slug") != args.slug:
        raise SystemExit(f"slug mismatch: {manifest.get('slug')}")
    _validate_integration_dag(manifest)
    order = topological_sort_dag(load_integration_dag(manifest))
    print(f"integration dag OK: {' -> '.join(order)}")


def now_iso() -> str:
    return datetime.now(TZ).isoformat()


def read_json(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.write("\n")


def append_history(slug: str, event: dict[str, Any]) -> None:
    path = Path("artifacts") / slug / "history.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps({"ts": now_iso(), **event}, ensure_ascii=False) + "\n")


def state_path(slug: str) -> Path:
    return Path("artifacts") / slug / "state.json"


def manifest_path(slug: str) -> Path:
    return Path("artifacts") / slug / "reader" / "manifest.json"


def canonical_stage(stage: str) -> str:
    key = stage.strip().lower()
    normalized = key.replace("-", "_")
    if key in STAGE_ALIASES:
        return STAGE_ALIASES[key]
    if normalized in STAGE_ALIASES:
        return STAGE_ALIASES[normalized]
    return normalized


def parse_run_number(run_id: str) -> int:
    """Parse zero-padded run ids such as '001' into an integer sequence number."""
    return int(run_id, 10)


def grouped_components(manifest: dict[str, Any]) -> dict[str, Any]:
    components = manifest.get("components")
    if not isinstance(components, dict):
        raise SystemExit("components must be a grouped object")
    return components


def pending_stage() -> dict[str, Any]:
    return {"status": "pending", "attempt": 0}


def component_is_required(components: dict[str, Any], stage: str) -> bool:
    if stage in {"workflow", "benchmark_data", "sysconfig", "schema", "prompt"}:
        return True
    if stage == "llm_provider":
        return bool(components.get("llm"))
    if stage == "embedding":
        return (
            bool(components.get("embedding"))
            or bool(components.get("rag"))
            or bool(components.get("few_shot"))
        )
    group = {
        "benchmark_data": "dataset",
        "db_backend": "db_backend",
    }.get(stage, stage)
    value = components.get(group)
    if stage == "actor":
        return isinstance(value, dict) and any(value.get(layer) for layer in ACTOR_LAYERS)
    return bool(value)


def initialize_stages(manifest: dict[str, Any]) -> dict[str, Any]:
    components = grouped_components(manifest)
    stages = METHOD_STAGES if manifest["type"] == "method" else DATABASE_STAGES
    result: dict[str, Any] = {}
    for stage in stages:
        if stage == "actor":
            actor_components = components.get("actor", {})
            layers = {
                layer: pending_stage() if actor_components.get(layer) else None
                for layer in ACTOR_LAYERS
            }
            result[stage] = (
                {"status": "pending", "attempt": 0, "layers": layers}
                if component_is_required(components, stage)
                else None
            )
        else:
            result[stage] = pending_stage() if component_is_required(components, stage) else None
    return result


def load_state(slug: str) -> dict[str, Any]:
    path = state_path(slug)
    if not path.exists():
        raise SystemExit(f"state not found: {path}")
    return read_json(path)


def reader_exploration_dir(slug: str) -> Path:
    return Path("artifacts") / slug / "reader" / "exploration"


def benchmark_ids(sys_config_path: Path = DEFAULT_SYS_CONFIG) -> set[str]:
    if not sys_config_path.exists():
        raise SystemExit(f"sys_config not found: {sys_config_path}")
    data = read_json(sys_config_path)
    benchmarks = data.get("benchmark", [])
    if not isinstance(benchmarks, list):
        raise SystemExit("sys_config benchmark must be a list")
    return {item["id"] for item in benchmarks if isinstance(item, dict) and item.get("id")}


def _source_file_in_coverage(source_file: str, scanned_files: set[str]) -> bool:
    normalized = source_file.replace("\\", "/").lstrip("./")
    for scanned in scanned_files:
        candidate = scanned.replace("\\", "/").lstrip("./")
        if normalized == candidate or candidate.endswith("/" + normalized) or normalized.endswith("/" + candidate):
            return True
    return False


def _collect_manifest_source_files(manifest: dict[str, Any]) -> list[str]:
    components = grouped_components(manifest)
    paths: list[str] = []
    for group in ("llm", "embedding", "prompt", "rag", "few_shot", "external"):
        for item in components.get(group, []) or []:
            paths.extend(item.get("source_files", []) or [])
    actor = components.get("actor", {})
    if isinstance(actor, dict):
        for layer in ACTOR_LAYERS:
            for item in actor.get(layer, []) or []:
                paths.extend(item.get("source_files", []) or [])
    return paths


def _validate_component_needs(components: dict[str, Any]) -> None:
    for group, fields in COMPONENT_NEEDS_FIELDS.items():
        for index, item in enumerate(components.get(group, []) or []):
            if not isinstance(item, dict):
                raise SystemExit(f"components.{group}[{index}] must be an object")
            if group == "external":
                if "needs_new_function" not in item and "needs_new_external_function" not in item:
                    raise SystemExit(
                        f"components.external[{index}] missing needs_new_function "
                        "or needs_new_external_function"
                    )
                continue
            missing = [field for field in fields if field not in item]
            if missing:
                raise SystemExit(
                    f"components.{group}[{index}] missing fields: {missing}"
                )


def _validate_actor_entries(components: dict[str, Any]) -> None:
    actor = components.get("actor", {})
    if not isinstance(actor, dict):
        return
    for layer in ACTOR_LAYERS:
        for index, item in enumerate(actor.get(layer, []) or []):
            if not isinstance(item, dict):
                raise SystemExit(f"components.actor.{layer}[{index}] must be an object")
            if not item.get("class_name"):
                raise SystemExit(
                    f"components.actor.{layer}[{index}] missing class_name"
                )
            source_files = item.get("source_files") or []
            if not source_files:
                raise SystemExit(
                    f"components.actor.{layer}[{index}] missing source_files"
                )


def _validate_target_datasets(
    manifest: dict[str, Any],
    sys_config_path: Path = DEFAULT_SYS_CONFIG,
) -> None:
    if manifest.get("type") != "method":
        return
    targets = manifest.get("target_datasets")
    if not targets:
        raise SystemExit("method manifest requires target_datasets")
    if not isinstance(targets, list):
        raise SystemExit("target_datasets must be a list")
    registered = benchmark_ids(sys_config_path)
    unknown = sorted({target for target in targets if target not in registered})
    if unknown:
        raise SystemExit(
            f"target_datasets not registered in {sys_config_path}: {unknown}"
        )


def _validate_embedding_consistency(components: dict[str, Any]) -> None:
    embedding = components.get("embedding") or []
    rag = components.get("rag") or []
    few_shot = components.get("few_shot") or []
    if embedding and not rag and not few_shot:
        for index, item in enumerate(embedding):
            description = (item.get("description") or "").strip()
            if not description:
                raise SystemExit(
                    "components.embedding entries require description when "
                    f"rag/few_shot are empty (item {index})"
                )


def _validate_pipeline(manifest: dict[str, Any]) -> None:
    if manifest.get("type") != "method":
        return
    pipeline = manifest.get("pipeline")
    if not isinstance(pipeline, dict):
        raise SystemExit("method manifest requires pipeline object")
    exec_process = pipeline.get("exec_process")
    if not isinstance(exec_process, list) or not exec_process:
        raise SystemExit("pipeline.exec_process must be a non-empty list")
    invalid = [stage for stage in exec_process if stage not in ALLOWED_PIPELINE_STAGES]
    if invalid:
        raise SystemExit(f"invalid pipeline.exec_process stages: {invalid}")
    actor = grouped_components(manifest).get("actor", {})
    for stage in exec_process:
        layer = PIPELINE_STAGE_TO_ACTOR_LAYER[stage]
        if not actor.get(layer):
            raise SystemExit(
                f"pipeline.exec_process includes {stage} but actor.{layer} is empty"
            )


def _validate_exploration_files(slug: str) -> None:
    exploration = reader_exploration_dir(slug)
    missing = [name for name in EXPLORATION_FILES if not (exploration / name).exists()]
    empty = [
        name
        for name in EXPLORATION_FILES
        if (exploration / name).exists() and (exploration / name).stat().st_size == 0
    ]
    if missing:
        raise SystemExit(f"missing exploration files under {exploration}: {missing}")
    if empty:
        raise SystemExit(f"empty exploration files under {exploration}: {empty}")


def _normalize_rel_path(path: str | Path, root: Path | None = None) -> str:
    raw = Path(path)
    if root is not None and raw.is_absolute():
        try:
            raw = raw.relative_to(root)
        except ValueError:
            return str(raw).replace("\\", "/").lstrip("./")
    return str(raw).replace("\\", "/").lstrip("./")


def _discover_candidate_files(source_path: Path) -> set[str]:
    if not source_path.exists():
        raise SystemExit(f"source_path not found: {source_path}")
    discovered: set[str] = set()
    for path in source_path.rglob("*"):
        if not path.is_file():
            continue
        rel = path.relative_to(source_path).as_posix()
        parts = set(rel.split("/"))
        if parts & COVERAGE_SKIP_DIR_NAMES:
            continue
        suffix = path.suffix.lower()
        name = path.name.lower()
        if suffix in COVERAGE_SCAN_SUFFIXES:
            discovered.add(rel)
            continue
        if name in COVERAGE_CONFIG_NAMES:
            discovered.add(rel)
            continue
        if suffix in {".json", ".yaml", ".yml", ".toml", ".cfg", ".ini"} and (
            "config" in rel.lower() or name.startswith("config")
        ):
            discovered.add(rel)
    return discovered


def _coverage_paths(coverage: dict[str, Any]) -> tuple[set[str], set[str]]:
    scanned = {
        _normalize_rel_path(path)
        for path in coverage.get("scanned_files", [])
    }
    skipped = {
        _normalize_rel_path(entry.get("path"))
        for entry in coverage.get("skipped_paths", [])
        if isinstance(entry, dict) and entry.get("path")
    }
    return scanned, skipped


def _validate_coverage_module_schema(coverage: dict[str, Any], filename: str) -> None:
    modules = coverage.get("modules", [])
    if not isinstance(modules, list):
        raise SystemExit(f"{filename}.modules must be a list")
    for index, module in enumerate(modules):
        if not isinstance(module, dict):
            raise SystemExit(f"{filename}.modules[{index}] must be an object")
        missing = [key for key in COVERAGE_MODULE_REQUIRED_KEYS if key not in module]
        if missing:
            raise SystemExit(f"{filename}.modules[{index}] missing keys: {missing}")
        if not module.get("files"):
            raise SystemExit(f"{filename}.modules[{index}].files must not be empty")
        if not module.get("inputs") or not isinstance(module.get("inputs"), list):
            raise SystemExit(f"{filename}.modules[{index}].inputs must be a non-empty list")
        if not module.get("outputs") or not isinstance(module.get("outputs"), list):
            raise SystemExit(f"{filename}.modules[{index}].outputs must be a non-empty list")


def _validate_recursive_source_coverage(source_path: Path, coverage: dict[str, Any]) -> None:
    discovered = _discover_candidate_files(source_path)
    scanned, skipped = _coverage_paths(coverage)
    accounted = scanned | skipped
    missing = sorted(
        path
        for path in discovered
        if not any(
            path == item or item.endswith("/" + path) or path.endswith("/" + item)
            for item in accounted
        )
    )
    if missing:
        preview = ", ".join(missing[:8])
        suffix = " ..." if len(missing) > 8 else ""
        raise SystemExit(
            f"candidate source not fully covered in candidate-coverage.json "
            f"({len(missing)} files): {preview}{suffix}"
        )


def _validate_modules_reference_scanned_files(coverage: dict[str, Any]) -> None:
    scanned, _ = _coverage_paths(coverage)
    referenced: set[str] = set()
    for module in coverage.get("modules", []):
        for file_path in module.get("files", []) or []:
            referenced.add(_normalize_rel_path(file_path))
    missing = sorted(
        path
        for path in scanned
        if not any(
            path == item or item.endswith("/" + path) or path.endswith("/" + item)
            for item in referenced
        )
    )
    if missing:
        preview = ", ".join(missing[:8])
        suffix = " ..." if len(missing) > 8 else ""
        raise SystemExit(
            "scanned_files not assigned to any modules[].files: "
            f"{preview}{suffix}"
        )


def _actor_layer_from_component(component: str) -> str | None:
    if not isinstance(component, str) or not component.startswith("actor."):
        return None
    layer = component.split(".", 1)[1]
    return layer if layer in ACTOR_LAYERS else None


def _manifest_actor_layers(manifest: dict[str, Any]) -> set[str]:
    actor = grouped_components(manifest).get("actor", {})
    if not isinstance(actor, dict):
        return set()
    return {layer for layer in ACTOR_LAYERS if actor.get(layer)}


def _coverage_actor_layers(coverage: dict[str, Any]) -> set[str]:
    layers: set[str] = set()
    for module in coverage.get("modules", []):
        layer = _actor_layer_from_component(module.get("squrve_component", ""))
        if layer:
            layers.add(layer)
    return layers


def _module_intermediate_artifacts(module: dict[str, Any]) -> set[str]:
    artifacts: set[str] = set()
    io_artifact = module.get("io_artifact")
    if isinstance(io_artifact, str) and io_artifact != "none":
        artifacts.add(io_artifact)
    for output in module.get("outputs", []) or []:
        if isinstance(output, str) and output in IO_INTERMEDIATE_ARTIFACTS:
            artifacts.add(output)
    return artifacts


def _validate_actor_allocation(manifest: dict[str, Any], coverage: dict[str, Any]) -> None:
    if manifest.get("type") != "method":
        return

    coverage_layers = _coverage_actor_layers(coverage)
    manifest_layers = _manifest_actor_layers(manifest)
    missing_layers = sorted(coverage_layers - manifest_layers)
    if missing_layers:
        raise SystemExit(
            "coverage maps actor layers that manifest omits (do not collapse into one "
            f"component): {missing_layers}"
        )

    intermediate_modules = [
        module
        for module in coverage.get("modules", [])
        if _module_intermediate_artifacts(module)
    ]
    distinct_intermediate_layers = {
        _actor_layer_from_component(module.get("squrve_component", ""))
        for module in intermediate_modules
    } - {None}

    generator_entries = grouped_components(manifest).get("actor", {}).get("generator", []) or []
    has_standalone = any(entry.get("standalone_fallback") for entry in generator_entries)

    if len(distinct_intermediate_layers) >= 2 and len(manifest_layers) < 2 and not has_standalone:
        raise SystemExit(
            "multiple intermediate pipeline stages detected in coverage but manifest "
            "uses a single actor layer; split by I/O per reader-recursion-contract.md "
            "or set standalone_fallback + standalone_reason on actor.generator"
        )

    layer_files: dict[str, set[str]] = {layer: set() for layer in ACTOR_LAYERS}
    for module in coverage.get("modules", []):
        layer = _actor_layer_from_component(module.get("squrve_component", ""))
        if not layer:
            continue
        for file_path in module.get("files", []) or []:
            layer_files[layer].add(_normalize_rel_path(file_path))

    actor = grouped_components(manifest).get("actor", {})
    for layer in ACTOR_LAYERS:
        for index, item in enumerate(actor.get(layer, []) or []):
            manifest_files = {
                _normalize_rel_path(path) for path in item.get("source_files", []) or []
            }
            foreign_files = set()
            for other_layer, files in layer_files.items():
                if other_layer == layer:
                    continue
                foreign_files |= files
            overlap = sorted(manifest_files & foreign_files)
            if overlap:
                preview = ", ".join(overlap[:5])
                suffix = " ..." if len(overlap) > 5 else ""
                raise SystemExit(
                    f"actor.{layer}[{index}] source_files belong to other layers in "
                    f"coverage: {preview}{suffix}"
                )


def _validate_pipeline_actor_alignment(manifest: dict[str, Any]) -> None:
    if manifest.get("type") != "method":
        return
    pipeline = manifest.get("pipeline", {})
    exec_process = pipeline.get("exec_process", [])
    manifest_layers = _manifest_actor_layers(manifest)
    expected_layers = {
        PIPELINE_STAGE_TO_ACTOR_LAYER[stage]
        for stage in exec_process
        if stage in PIPELINE_STAGE_TO_ACTOR_LAYER
    }
    if manifest_layers != expected_layers:
        raise SystemExit(
            "pipeline.exec_process stages must exactly match non-empty actor layers: "
            f"exec_process={exec_process}, actor_layers={sorted(manifest_layers)}"
        )
    # exec_process must be a subsequence of one of the valid orders
    valid = False
    for order in VALID_PIPELINE_ORDERS:
        indices = [order.index(stage) for stage in exec_process if stage in order]
        if indices == sorted(indices):
            valid = True
            break
    if not valid:
        raise SystemExit(
            f"pipeline.exec_process does not follow any valid data-flow order "
            f"{[list(o) for o in VALID_PIPELINE_ORDERS]}; got {exec_process}"
        )


def _load_coverage_json(slug: str, filename: str) -> dict[str, Any]:
    path = reader_exploration_dir(slug) / filename
    data = read_json(path)
    for key in ("root", "scanned_files", "modules"):
        if key not in data:
            raise SystemExit(f"{filename} missing key: {key}")
    if not isinstance(data["scanned_files"], list):
        raise SystemExit(f"{filename}.scanned_files must be a list")
    if not isinstance(data["modules"], list):
        raise SystemExit(f"{filename}.modules must be a list")
    if not data["scanned_files"]:
        raise SystemExit(f"{filename}.scanned_files must not be empty")
    if not data["modules"]:
        raise SystemExit(f"{filename}.modules must not be empty")
    _validate_coverage_module_schema(data, filename)
    return data


def _validate_mapping_matrix_references(slug: str, manifest: dict[str, Any]) -> None:
    matrix_text = (reader_exploration_dir(slug) / "mapping-matrix.md").read_text(
        encoding="utf-8"
    )
    components = grouped_components(manifest)
    missing: list[str] = []

    actor = components.get("actor", {})
    if isinstance(actor, dict):
        for layer, items in actor.items():
            for item in items or []:
                class_name = item.get("class_name")
                if class_name and class_name not in matrix_text:
                    missing.append(f"actor.{layer} class {class_name}")
                for source_file in item.get("source_files", []) or []:
                    if source_file not in matrix_text:
                        missing.append(f"actor.{layer} source_file {source_file}")

    for group in ("llm", "embedding", "prompt", "rag", "few_shot", "external"):
        for item in components.get(group, []) or []:
            for source_file in item.get("source_files", []) or []:
                if source_file not in matrix_text:
                    missing.append(f"{group} source_file {source_file}")

    if missing:
        preview = "; ".join(missing[:5])
        suffix = " ..." if len(missing) > 5 else ""
        raise SystemExit(
            f"mapping-matrix.md missing manifest references: {preview}{suffix}"
        )


def _validate_manifest_source_files_in_coverage(
    slug: str,
    manifest: dict[str, Any],
) -> None:
    coverage = _load_coverage_json(slug, "candidate-coverage.json")
    scanned = {
        str(path).replace("\\", "/").lstrip("./")
        for path in coverage.get("scanned_files", [])
    }
    missing = [
        source_file
        for source_file in _collect_manifest_source_files(manifest)
        if not _source_file_in_coverage(source_file, scanned)
    ]
    if missing:
        preview = ", ".join(missing[:5])
        suffix = " ..." if len(missing) > 5 else ""
        raise SystemExit(
            "manifest source_files not found in candidate-coverage.json "
            f"scanned_files: {preview}{suffix}"
        )


def validate_manifest_content(
    manifest: dict[str, Any],
    *,
    slug: str | None = None,
    sys_config_path: Path = DEFAULT_SYS_CONFIG,
) -> None:
    if slug is not None and manifest.get("slug") != slug:
        raise SystemExit(f"slug mismatch: {manifest.get('slug')}")
    if manifest.get("type") not in {"method", "database"}:
        raise SystemExit(f"invalid type: {manifest.get('type')}")
    components = grouped_components(manifest)
    if not components:
        raise SystemExit("components empty")
    required_groups = (
        {"llm", "embedding", "prompt", "rag", "few_shot", "external", "actor", "config"}
        if manifest["type"] == "method"
        else {
            "dataset", "schema", "database_files", "benchmark_meta", "embedding",
            "rag", "few_shot", "external", "db_backend", "credential",
        }
    )
    missing_groups = sorted(required_groups - components.keys())
    if missing_groups:
        raise SystemExit(f"missing component groups: {missing_groups}")
    if manifest["type"] == "method" and not isinstance(components.get("actor", {}), dict):
        raise SystemExit("components.actor must be an object grouped by layer")
    if not components.get("llm") and manifest["type"] == "method":
        raise SystemExit("method manifest requires at least one llm component")
    _validate_component_needs(components)
    _validate_actor_entries(components)
    _validate_target_datasets(manifest, sys_config_path)
    _validate_embedding_consistency(components)
    _validate_pipeline(manifest)
    _validate_pipeline_actor_alignment(manifest)
    _validate_integration_dag(manifest)


def validate_reader_artifacts(args: argparse.Namespace) -> None:
    slug = args.slug
    sys_config_path = Path(getattr(args, "sys_config", str(DEFAULT_SYS_CONFIG)))
    _validate_exploration_files(slug)
    _load_coverage_json(slug, "squrve-coverage.json")
    candidate_coverage = _load_coverage_json(slug, "candidate-coverage.json")
    manifest = read_json(manifest_path(slug))
    validate_manifest_content(manifest, slug=slug, sys_config_path=sys_config_path)
    source_path = Path(manifest.get("source_path", ""))
    _validate_recursive_source_coverage(source_path, candidate_coverage)
    _validate_modules_reference_scanned_files(candidate_coverage)
    _validate_actor_allocation(manifest, candidate_coverage)
    _validate_mapping_matrix_references(slug, manifest)
    _validate_manifest_source_files_in_coverage(slug, manifest)
    print(f"reader artifacts OK: {slug}")


def validate_manifest(args: argparse.Namespace) -> dict[str, Any]:
    manifest = read_json(manifest_path(args.slug))
    sys_config_path = Path(getattr(args, "sys_config", str(DEFAULT_SYS_CONFIG)))
    validate_manifest_content(
        manifest,
        slug=args.slug,
        sys_config_path=sys_config_path,
    )
    print(
        f"manifest OK: type={manifest['type']}, "
        f"{len(grouped_components(manifest))} component groups"
    )
    return manifest


def complete_reader(args: argparse.Namespace) -> None:
    validate_reader_artifacts(args)
    manifest = read_json(manifest_path(args.slug))
    if manifest.get("type") == "method":
        allow = resolve_allow_main(args.slug, allow_main_flag=getattr(args, "allow_main", False))
        require_method_integration_branch(args.slug, allow_main=allow)
    slug = args.slug
    path = state_path(slug)
    old: dict[str, Any] = read_json(path) if path.exists() else {}
    old_attempt = old.get("reader", {}).get("attempt", 0)
    old_run = old.get(
        "run",
        {
            "latest_run_id": None,
            "total_runs": 0,
            "best_run_id": None,
            "best_ex_score": None,
        },
    )
    if old_run.get("total_runs"):
        old_run["stale_since"] = now_iso()

    artifact_root = Path("artifacts") / slug
    if artifact_root.exists():
        for child in artifact_root.iterdir():
            if child.is_dir() and child.name not in {"reader", "runs"}:
                shutil.rmtree(child)
    artifact_root.mkdir(parents=True, exist_ok=True)
    (artifact_root / "adapter").mkdir(parents=True, exist_ok=True)
    (artifact_root / "runs").mkdir(parents=True, exist_ok=True)

    timestamp = now_iso()
    state = {
        "slug": slug,
        "source_path": args.source_path,
        "created_at": old.get("created_at", timestamp),
        "type": manifest["type"],
        "reader": {
            "status": "done",
            "attempt": old_attempt + 1,
            "finished_at": timestamp,
            "type": manifest["type"],
        },
        "adapter": {"status": "pending"},
        "run": old_run,
        **initialize_stages(manifest),
    }
    write_json(path, state)
    append_history(
        slug,
        {
            "stage": "reader",
            "event": "done",
            "attempt": state["reader"]["attempt"],
            "type": manifest["type"],
        },
    )
    print(f"reader complete: attempt {state['reader']['attempt']}")


def status_ok(state: dict[str, Any], stage: str) -> bool:
    value = state.get(stage)
    if value is None:
        return True
    if not isinstance(value, dict):
        return False
    status = value.get("status")
    if status == "null":
        raise SystemExit(
            f"{stage} uses invalid status string 'null'; skipped stages must be "
            "JSON null (omit the stage object), not {{\"status\": \"null\"}}"
        )
    return status in SUCCESS_STATUSES


def require_status(state: dict[str, Any], stage: str) -> None:
    if not status_ok(state, stage):
        value = state.get(stage)
        status = value.get("status") if isinstance(value, dict) else "missing"
        raise SystemExit(f"{stage} not done: {status}")


def gate_stage(args: argparse.Namespace) -> None:
    stage = canonical_stage(args.stage)
    if stage == "adapter":
        raise SystemExit("config-adapter must use gate-adapter")
    state = load_state(args.slug)
    manifest = read_json(manifest_path(args.slug))
    components = grouped_components(manifest)
    reader = state.get("reader", {})
    if reader.get("status") != "done":
        raise SystemExit(f"reader not done: {reader.get('status')}")
    candidate_type = reader.get("type")
    allowed = METHOD_STAGES if candidate_type == "method" else DATABASE_STAGES
    if stage not in allowed:
        raise SystemExit(f"stage {stage} is not valid for {candidate_type}")
    if not component_is_required(components, stage):
        raise SystemExit(f"stage {stage} is not required by manifest")

    if candidate_type == "method":
        allow = resolve_allow_main(args.slug, allow_main_flag=getattr(args, "allow_main", False))
        require_method_integration_branch(args.slug, allow_main=allow)

    require_integration_dependencies(state, manifest, stage)

    current = state.get(stage)
    if isinstance(current, dict) and current.get("status") in SUCCESS_STATUSES:
        print(f"WARN: {stage} 已完成过，本次将覆盖")
    print("GATE passed")


def parse_value(raw: str) -> Any:
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return raw


def reset_stage(state: dict[str, Any], stage: str) -> None:
    current = state.get(stage)
    if current is None:
        return
    if stage == "actor":
        for layer_state in current.get("layers", {}).values():
            if layer_state is not None:
                layer_state["status"] = "pending"
                layer_state.pop("finished_at", None)
        current["status"] = "pending"
        current.pop("finished_at", None)
    elif isinstance(current, dict):
        current["status"] = "pending"
        current.pop("finished_at", None)


def done_stage(args: argparse.Namespace) -> None:
    stage = canonical_stage(args.stage)
    if stage == "adapter":
        raise SystemExit("config-adapter must use complete-adapter")
    state = load_state(args.slug)
    current = state.get(stage)
    if current is None:
        current = pending_stage()
        state[stage] = current
    if not isinstance(current, dict):
        raise SystemExit(f"invalid state for stage {stage}")

    timestamp = now_iso()
    current["attempt"] = int(current.get("attempt", 0)) + 1
    current["status"] = args.status
    current["finished_at"] = timestamp
    for item in getattr(args, "values", []) or []:
        if "=" not in item:
            raise SystemExit(f"--set requires KEY=VALUE: {item}")
        key, raw = item.split("=", 1)
        current[key] = parse_value(raw)

    event: dict[str, Any] = {
        "stage": stage,
        "event": args.status,
        "attempt": current["attempt"],
    }
    if stage == "actor":
        if not args.layer or args.layer not in ACTOR_LAYERS:
            raise SystemExit("actor done requires --layer with a supported actor layer")
        layer_state = current.setdefault("layers", {}).get(args.layer) or {}
        layer_state.update({"status": args.status, "finished_at": timestamp})
        if args.class_name:
            layer_state["class_name"] = args.class_name
        current["layers"][args.layer] = layer_state
        declared = [value for value in current["layers"].values() if value is not None]
        current["status"] = (
            "done" if declared and all(value.get("status") in SUCCESS_STATUSES for value in declared)
            else "pending"
        )
        event.update({"layer": args.layer, "class_name": args.class_name})

    manifest = read_json(manifest_path(args.slug))
    for downstream in downstream_stages(load_integration_dag(manifest), stage):
        reset_stage(state, downstream)
    if stage == "rag" and (
        current.get("needs_new_retrieval_strategy") is True
        or current.get("needs_new_schema_linking_mode") is True
    ):
        reset_stage(state, "actor")
        reset_stage(state, "workflow")
    write_json(state_path(args.slug), state)
    append_history(args.slug, event)
    print(f"{stage} complete: attempt {current['attempt']}")


def gate_adapter(args: argparse.Namespace) -> None:
    state = load_state(args.slug)
    reader = state.get("reader", {})
    if reader.get("status") != "done":
        raise SystemExit(f"reader not done: {reader.get('status')}")
    if reader.get("type") != args.expected_type:
        raise SystemExit(
            f"type is {reader.get('type')}, not {args.expected_type}"
        )
    if args.expected_type == "method":
        allow = resolve_allow_main(args.slug, allow_main_flag=getattr(args, "allow_main", False))
        require_method_integration_branch(args.slug, allow_main=allow)
    manifest = read_json(manifest_path(args.slug))
    require_integration_dependencies(state, manifest, INTEGRATION_TERMINAL_STAGE)
    if state.get("adapter", {}).get("status") == "done":
        print("WARN: adapter 已完成过，本次将覆盖")
    print("GATE passed")


def complete_adapter(args: argparse.Namespace) -> None:
    state = load_state(args.slug)
    old_attempt = state.get("adapter", {}).get("attempt", 0)
    state["adapter"] = {
        "status": "done",
        "attempt": old_attempt + 1,
        "adapter_type": args.adapter_type,
        "finished_at": now_iso(),
        "target_dataset": args.target_dataset,
        "reproduce_config": args.reproduce_config,
    }
    write_json(state_path(args.slug), state)
    append_history(
        args.slug,
        {
            "stage": "adapter",
            "event": "done",
            "attempt": state["adapter"]["attempt"],
            "adapter_type": args.adapter_type,
            "reproduce_config": args.reproduce_config,
        },
    )
    print(f"adapter complete: attempt {state['adapter']['attempt']}")


def sanitize_config(config: dict[str, Any]) -> dict[str, Any]:
    data = json.loads(json.dumps(config))
    api_keys = data.get("api_key")
    if isinstance(api_keys, dict):
        for provider, key in list(api_keys.items()):
            if key not in PLACEHOLDER_KEYS:
                api_keys[provider] = "<redacted>"
    return data


def prepare_run(args: argparse.Namespace) -> None:
    slug = args.method
    path = state_path(slug)
    if path.exists():
        state = read_json(path)
        adapter = state.get("adapter", {})
        if adapter.get("status") != "done":
            raise SystemExit(f"adapter not done: {adapter.get('status')}")
        config_path = Path(adapter["reproduce_config"])
        total = parse_run_number(str(state.get("run", {}).get("total_runs", 0)))
    else:
        config_path = Path("reproduce") / "configs" / args.dataset / f"{args.method}.json"
        total = 0

    if not config_path.exists():
        raise SystemExit(f"config not found: {config_path}")

    config = read_json(config_path)
    repo_root = Path(__file__).resolve().parents[2]
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))
    from reproduce.lib.env_config import api_key_ready

    ready, message = api_key_ready(config)
    if not ready:
        raise SystemExit(message)

    run_id = str(total + 1).zfill(3)
    run_dir = Path("artifacts") / slug / "reproduce-runs" / run_id
    run_dir.mkdir(parents=True, exist_ok=False)
    write_json(run_dir / "config-snapshot.json", sanitize_config(config))
    print(f"RUN_ID={run_id}")
    print(f"RUN_DIR={run_dir}")
    print(f"CONFIG={config_path}")


def record_run(args: argparse.Namespace) -> None:
    slug = args.method
    run_dir = Path("artifacts") / slug / "reproduce-runs" / args.run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    config = read_json(Path(args.config_path))
    result = {
        "run_id": args.run_id,
        "method": args.method,
        "dataset": args.dataset,
        "split": args.split,
        "ex_score": args.ex_score,
        "generate_num": config.get("generate_num", 1),
        "debug_rounds": args.debug_rounds,
        "config_path": args.config_path,
        "pred_sql_dir": args.pred_sql_dir,
        "dataset_save_dir": args.dataset_save_dir,
        "artifact_dir": args.artifact_dir,
        "scores_path": args.scores_path,
        "eval_store_path": args.eval_store_path,
        "timestamp": now_iso(),
    }
    write_json(run_dir / "reproduce-run.json", result)

    state = load_state(slug)
    run_state = state.get(
        "run",
        {
            "latest_run_id": None,
            "total_runs": 0,
            "best_run_id": None,
            "best_ex_score": None,
        },
    )
    run_state["latest_run_id"] = args.run_id
    run_state["total_runs"] = max(
        int(run_state.get("total_runs", 0)),
        parse_run_number(args.run_id),
    )
    if (
        run_state.get("best_ex_score") is None
        or args.ex_score > run_state["best_ex_score"]
    ):
        run_state["best_run_id"] = args.run_id
        run_state["best_ex_score"] = args.ex_score
    run_state.pop("stale_since", None)
    state["run"] = run_state
    write_json(state_path(slug), state)
    append_history(
        slug,
        {
            "stage": "run",
            "event": "done",
            "run_id": args.run_id,
            "ex_score": args.ex_score,
            "debug_rounds": args.debug_rounds,
        },
    )
    print(f"run recorded: {args.run_id}, EX={args.ex_score}")


def write_self_improve_state(args: argparse.Namespace) -> None:
    data = {
        "improve_slug": args.improve_slug,
        "run_slug": args.run_slug,
        "round": args.round,
        "status": args.status,
        "updated_at": now_iso(),
    }
    path = (
        Path("artifacts")
        / "step5"
        / args.improve_slug
        / "self-improve-state.json"
    )
    write_json(path, data)
    print(f"self-improve state written: {path}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("validate-manifest")
    p.add_argument("--slug", required=True)
    p.add_argument("--sys-config", default=str(DEFAULT_SYS_CONFIG))
    p.set_defaults(func=validate_manifest)

    p = sub.add_parser("validate-integration-dag")
    p.add_argument("--slug", required=True)
    p.set_defaults(func=validate_integration_dag_cmd)

    p = sub.add_parser("adapter-plan")
    p.add_argument("--slug", required=True)
    p.set_defaults(func=adapter_plan)

    p = sub.add_parser("validate-reader-artifacts")
    p.add_argument("--slug", required=True)
    p.add_argument("--sys-config", default=str(DEFAULT_SYS_CONFIG))
    p.set_defaults(func=validate_reader_artifacts)

    p = sub.add_parser("check-branch")
    p.add_argument("--slug", required=True)
    p.add_argument("--type", choices=["method", "database"], required=True)
    p.add_argument(
        "--allow-main",
        action="store_true",
        help="User chose Main mode; persist allow_main and permit method on main",
    )
    p.set_defaults(func=check_branch)

    p = sub.add_parser("set-dev-mode")
    p.add_argument("--slug", required=True)
    p.add_argument("--mode", choices=["main", "branch", "worktree"], required=True)
    p.set_defaults(func=set_dev_mode_cmd)

    p = sub.add_parser("complete-reader")
    p.add_argument("--slug", required=True)
    p.add_argument("--source-path", required=True)
    p.add_argument("--sys-config", default=str(DEFAULT_SYS_CONFIG))
    p.add_argument("--allow-main", action="store_true")
    p.set_defaults(func=complete_reader)

    p = sub.add_parser("gate-adapter")
    p.add_argument("--slug", required=True)
    p.add_argument("--expected-type", choices=["method", "database"], required=True)
    p.add_argument("--allow-main", action="store_true")
    p.set_defaults(func=gate_adapter)

    p = sub.add_parser("gate")
    p.add_argument("stage")
    p.add_argument("slug")
    p.add_argument("--allow-main", action="store_true")
    p.set_defaults(func=gate_stage)

    p = sub.add_parser("done")
    p.add_argument("stage")
    p.add_argument("slug")
    p.add_argument("--status", choices=sorted(DONE_STAGE_STATUSES), default="done")
    p.add_argument("--layer", choices=ACTOR_LAYERS)
    p.add_argument("--class-name")
    p.add_argument("--set", dest="values", action="append", default=[])
    p.set_defaults(func=done_stage)

    p = sub.add_parser("complete-adapter")
    p.add_argument("--slug", required=True)
    p.add_argument(
        "--adapter-type",
        choices=["method-adapter", "database-adapter"],
        required=True,
    )
    p.add_argument("--target-dataset", required=True)
    p.add_argument("--reproduce-config", required=True)
    p.set_defaults(func=complete_adapter)

    p = sub.add_parser("prepare-run")
    p.add_argument("--dataset", required=True)
    p.add_argument("--method", required=True)
    p.set_defaults(func=prepare_run)

    p = sub.add_parser("record-run")
    p.add_argument("--dataset", required=True)
    p.add_argument("--method", required=True)
    p.add_argument("--run-id", required=True)
    p.add_argument("--ex-score", type=float, required=True)
    p.add_argument("--debug-rounds", type=int, required=True)
    p.add_argument("--config-path", required=True)
    p.add_argument("--pred-sql-dir", required=True)
    p.add_argument("--dataset-save-dir", required=True)
    p.add_argument("--artifact-dir")
    p.add_argument("--scores-path")
    p.add_argument("--eval-store-path")
    p.add_argument("--split", default="dev")
    p.set_defaults(func=record_run)

    p = sub.add_parser("write-self-improve-state")
    p.add_argument("--improve-slug", required=True)
    p.add_argument("--run-slug", required=True)
    p.add_argument("--round", type=int, required=True)
    p.add_argument("--status", default="complete")
    p.set_defaults(func=write_self_improve_state)

    return parser


def main() -> None:
    args = build_parser().parse_args()
    args.func(args)


if __name__ == "__main__":
    main()

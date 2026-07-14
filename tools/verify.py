#!/usr/bin/env python3
"""Deterministic verification helpers used by SqurveBridge skills."""

from __future__ import annotations

import argparse
import ast
import importlib
import importlib.util
import json
import os
import sys
from pathlib import Path
from typing import Any


def read_json(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def actor_import(args: argparse.Namespace) -> None:
    module = importlib.import_module(f"core.actor.{args.layer}")
    getattr(module, args.class_name)
    print(f"import OK: {args.class_name}")


def actor_syntax(args: argparse.Namespace) -> None:
    path = Path(args.path)
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    classes = {node.name for node in tree.body if isinstance(node, ast.ClassDef)}
    if args.class_name not in classes:
        raise SystemExit(f"class {args.class_name} not found in {path}")
    print(f"actor syntax OK: {args.class_name}")


def provider_registered(args: argparse.Namespace) -> None:
    model_path = Path("core/llm") / f"{args.model_class}.py"
    if not model_path.exists():
        raise SystemExit(f"provider model not found: {model_path}")
    data_manage = Path(args.data_manage).read_text(encoding="utf-8")
    missing = [token for token in (args.provider, args.model_class) if token not in data_manage]
    if missing:
        raise SystemExit(f"provider registration missing tokens: {missing}")
    print(f"provider registered OK: {args.provider}")


def task_branch(args: argparse.Namespace) -> None:
    source = Path(args.path).read_text(encoding="utf-8")
    missing = [token for token in (args.actor_type, args.class_name) if token not in source]
    if missing:
        raise SystemExit(f"task branch missing tokens: {missing}")
    print(f"task branch OK: {args.actor_type} -> {args.class_name}")


def rag_index(args: argparse.Namespace) -> None:
    path = Path(args.path)
    required = {"docstore.json", "index_store.json"}
    present = {item.name for item in path.iterdir()} if path.is_dir() else set()
    missing = sorted(required - present)
    if missing:
        raise SystemExit(f"rag index incomplete at {path}: missing {missing}")
    print(f"rag index OK: {path}")


def few_shot_examples(args: argparse.Namespace) -> None:
    path = Path(args.path)
    examples = [item for item in path.glob("*.txt") if item.stat().st_size > 0] if path.is_dir() else []
    if len(examples) < args.minimum:
        raise SystemExit(
            f"few-shot examples at {path}: {len(examples)}, expected >= {args.minimum}"
        )
    print(f"few-shot examples OK: {len(examples)}")


def config_task(args: argparse.Namespace) -> None:
    config = read_json(Path(args.path))
    task = config["task"]["task_meta"][0]["meta"]["task"]
    if args.expected_task and task.get("generate_type") != args.expected_task:
        raise SystemExit(
            f"generate_type is {task.get('generate_type')}, not {args.expected_task}"
        )
    print(f"config OK: {task.get('generate_type')}")


def json_load(args: argparse.Namespace) -> None:
    read_json(Path(args.path))
    print(f"json OK: {args.path}")


def benchmark_registered(args: argparse.Namespace) -> None:
    from core.base import Router

    Router._sys_config_path = args.sys_config
    router = Router()
    benchmark_ids = [benchmark["id"] for benchmark in router.benchmark]
    if args.slug not in benchmark_ids:
        raise SystemExit(f"{args.slug} not in {benchmark_ids}")
    print(f"benchmark registered OK: {args.slug}")


TOOLS_DIR = Path(__file__).resolve().parent


def _load_tool_module(name: str):
    path = TOOLS_DIR / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise SystemExit(f"{name} module not found or cannot be loaded: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _load_artifact_state():
    return _load_tool_module("artifact_state")


def reader_artifacts(args: argparse.Namespace) -> None:
    artifact_state = _load_artifact_state()
    artifact_state.validate_reader_artifacts(args)


def evaluate_reproduce(args: argparse.Namespace) -> None:
    root = Path.cwd()
    os.chdir(REPRODUCE_ROOT := (root / "reproduce"))
    try:
        from reproduce.eval.utils import evaluate, load_router
        from reproduce.lib.paths import config_filename, run_identifier

        config_name = config_filename(args.dataset, args.method)
        _, save_lis = load_router(config_name, run_identifier(args.dataset, args.method))
        score = evaluate(save_lis, config_name)
    finally:
        os.chdir(root)
    print(f"EX_SCORE={score}")


def reproduce_contract(args: argparse.Namespace) -> None:
    contract = _load_tool_module("reproduce_contract")
    command_args = argparse.Namespace(path=args.path, all=args.all)
    contract.command_validate(command_args)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("actor-import")
    p.add_argument("--class-name", required=True)
    p.add_argument("--layer", default="generator")
    p.set_defaults(func=actor_import)

    p = sub.add_parser("actor-syntax")
    p.add_argument("--path", required=True)
    p.add_argument("--class-name", required=True)
    p.set_defaults(func=actor_syntax)

    p = sub.add_parser("provider-registered")
    p.add_argument("--provider", required=True)
    p.add_argument("--model-class", required=True)
    p.add_argument("--data-manage", default="core/data_manage.py")
    p.set_defaults(func=provider_registered)

    p = sub.add_parser("task-branch")
    p.add_argument("--path", required=True)
    p.add_argument("--actor-type", required=True)
    p.add_argument("--class-name", required=True)
    p.set_defaults(func=task_branch)

    p = sub.add_parser("rag-index")
    p.add_argument("--path", required=True)
    p.set_defaults(func=rag_index)

    p = sub.add_parser("few-shot-examples")
    p.add_argument("--path", required=True)
    p.add_argument("--minimum", type=int, default=1)
    p.set_defaults(func=few_shot_examples)

    p = sub.add_parser("config-task")
    p.add_argument("--path", required=True)
    p.add_argument("--expected-task")
    p.set_defaults(func=config_task)

    p = sub.add_parser("json-load")
    p.add_argument("--path", required=True)
    p.set_defaults(func=json_load)

    p = sub.add_parser("benchmark-registered")
    p.add_argument("--slug", required=True)
    p.add_argument("--sys-config", default="config/sys_config.json")
    p.set_defaults(func=benchmark_registered)

    p = sub.add_parser("reader-artifacts")
    p.add_argument("--slug", required=True)
    p.add_argument("--sys-config", default="config/sys_config.json")
    p.set_defaults(func=reader_artifacts)

    p = sub.add_parser("evaluate")
    p.add_argument("--dataset", required=True)
    p.add_argument("--method", required=True)
    p.set_defaults(func=evaluate_reproduce)

    p = sub.add_parser("reproduce-contract")
    group = p.add_mutually_exclusive_group(required=True)
    group.add_argument("--path", help="single reproduce config path")
    group.add_argument("--all", action="store_true", help="all runnable reproduce configs")
    p.set_defaults(func=reproduce_contract)

    return parser


def main() -> None:
    args = build_parser().parse_args()
    args.func(args)


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Run reproduce in sequential mini-batches until metrics stabilize.

Like mini-batch gradient descent: each step adds `batch_size` samples,
tracks a running metric on all data seen so far, and stops when the
metric change stays below `delta` for `patience` consecutive batches.

Usage (from reproduce/):
    python batch_run.py spider c3sql
    python batch_run.py spider c3sql --batch-size 10 --metric ex --delta 0.02 --patience 2
    python batch_run.py spider c3sql --max-batches 3   # smoke: only 3 batches
    python batch_run.py spider c3sql --resume          # continue from state file
"""

from __future__ import annotations

import argparse
import json
import sys
import os
from datetime import datetime
from pathlib import Path

project_root = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(project_root))

from core.engine import Engine
from core.utils import load_dataset
from reproduce.runner.batch_utils import (
    append_batch_predictions,
    assert_batches_disjoint,
    empty_cumulative,
    eval_results_to_cumulative,
    is_stable,
    load_benchmark_rows,
    load_state,
    make_batch_config,
    make_eval_config,
    metric_value,
    print_batch_step,
    print_convergence_header,
    save_state,
    split_batches,
    cumulative_to_report,
)
from reproduce.lib.env_config import resolve_config_api_keys
from reproduce.lib.paths import REPRODUCE_ROOT, config_filename, config_repo_path, run_identifier
from reproduce.eval.report import print_eval_report, print_report_header
from core.llm.token_logger import collect_all_token_data
from reproduce.eval.utils import evaluate, evaluate_with_details, load_router
from reproduce.metrics.assembly import build_scores
from reproduce.metrics.persistence import persist_scores_bundle
from reproduce.runner.run import (
    _load_custom_metrics,
    _run_custom_metrics,
    _run_custom_metrics_with_details,
    _suppress_eval_warnings,
)


def main():
    parser = argparse.ArgumentParser(description="Sequential batch reproduce until metric stabilizes")
    parser.add_argument("dataset", help="benchmark name, e.g. spider")
    parser.add_argument("method", help="method slug, e.g. dinsql")
    parser.add_argument("--batch-size", type=int, default=10, help="samples per batch (default: 10)")
    parser.add_argument("--metric", default="ex", choices=["ex", "em", "sf1", "sc", "ves", "cf1"],
                        help="metric to monitor for convergence (default: ex)")
    parser.add_argument("--delta", type=float, default=0.02,
                        help="stop when |Δmetric| < delta for patience batches (default: 0.02)")
    parser.add_argument("--patience", type=int, default=2,
                        help="consecutive stable batches required (default: 2)")
    parser.add_argument("--max-batches", type=int, default=0,
                        help="cap batches (0 = until stable or data exhausted)")
    parser.add_argument("--resume", action="store_true", help="resume from saved state")
    parser.add_argument("--dry-run", action="store_true", help="print batch plan only")
    args = parser.parse_args()

    identifier = run_identifier(args.dataset, args.method)
    config_path = config_filename(args.dataset, args.method)
    reproduce_dir = REPRODUCE_ROOT
    original_cwd = Path.cwd()

    try:
        os.chdir(reproduce_dir)
        _run_batches(args, identifier, config_path, reproduce_dir)
    finally:
        os.chdir(original_cwd)


def _run_batches(args, identifier: str, config_path: str, reproduce_dir: Path) -> None:
    base_config = resolve_config_api_keys(load_dataset(config_path))
    data_source = base_config["task"]["task_meta"][0]["data_source"]
    sys_config_path = (reproduce_dir / "../config/sys_config.json").resolve()

    all_rows = load_benchmark_rows(data_source, sys_config_path)
    batches = split_batches(all_rows, args.batch_size)
    assert_batches_disjoint(batches)
    if not batches:
        print("数据集为空，退出。")
        return

    run_dir = (reproduce_dir / f"../files/datasets/{identifier}/batch_run").resolve()
    source_dir = run_dir / "sources"
    cumulative_dir = run_dir / "cumulative"
    cumulative_save = cumulative_dir / "task_1.json"
    state_path = run_dir / "state.json"
    eval_config = make_eval_config(base_config)
    source_dir.mkdir(parents=True, exist_ok=True)
    cumulative_dir.mkdir(parents=True, exist_ok=True)

    if args.dry_run:
        print_convergence_header(identifier, args.batch_size, args.metric, args.delta, args.patience, len(all_rows))
        for idx, batch in enumerate(batches):
            print(f"  batch {idx:>3}  样本 {len(batch):>2}  [{batch[0]['instance_id']} … {batch[-1]['instance_id']}]")
        print(f"\n共 {len(batches)} 个 batch，全集 {len(all_rows)} 条")
        return

    if _load_custom_metrics() is None:
        print("警告: sqlglot 未安装，自定义指标将跳过（EX 仍可用）")

    state = load_state(state_path) if args.resume else None
    start_batch = state["next_batch"] if state else 0
    cumulative = state["cumulative"] if state else empty_cumulative()
    history: list[float] = state.get("history", []) if state else []

    if args.resume:
        if not cumulative_save.exists():
            print(f"警告: --resume 但缺少累计结果 {cumulative_save}，将从 step {start_batch} 重建")
        elif cumulative["samples_seen"] and cumulative_save.exists():
            saved_rows = load_dataset(cumulative_save)
            if len(saved_rows) != cumulative["samples_seen"]:
                print(
                    f"警告: state 记录 {cumulative['samples_seen']} 条，"
                    f"累计文件 {len(saved_rows)} 条，以文件为准"
                )
    elif cumulative_save.exists():
        cumulative_save.unlink()

    print_convergence_header(identifier, args.batch_size, args.metric, args.delta, args.patience, len(all_rows))

    batches_run = 0
    stop_reason = None

    for batch_index in range(start_batch, len(batches)):
        if args.max_batches and batches_run >= args.max_batches:
            stop_reason = f"达到 --max-batches={args.max_batches}"
            break

        batch_rows = batches[batch_index]
        batch_source = source_dir / f"batch_{batch_index:04d}.json"
        batch_config = make_batch_config(
            base_config,
            batch_rows,
            batch_index,
            batch_source,
        )
        batch_id = f"{identifier}/batch_{batch_index:04d}"

        print(
            f"\n▶ step {batch_index + 1}/{len(batches)}  "
            f"本批 {len(batch_rows)} 条 "
            f"[{batch_rows[0]['instance_id']} … {batch_rows[-1]['instance_id']}]  执行中..."
        )
        router, save_lis = load_router(config=batch_config, identifier=batch_id)
        engine = Engine(router)
        engine.execute()

        total_seen, batch_added = append_batch_predictions(cumulative_save, save_lis[0])
        cumulative_save_lis = [str(cumulative_save)]

        with _suppress_eval_warnings():
            ex_result = evaluate(cumulative_save_lis, config=eval_config, quiet=True)
            custom_results = _run_custom_metrics(
                cumulative_save_lis, config=eval_config, quiet=True
            )

        prev_metric = metric_value(cumulative, args.metric) if cumulative["samples_seen"] else None
        cumulative = eval_results_to_cumulative(ex_result, custom_results, total_seen)
        current_metric = metric_value(cumulative, args.metric)
        if current_metric is not None:
            history.append(current_metric)

        step_delta = None
        if prev_metric is not None and current_metric is not None:
            step_delta = abs(current_metric - prev_metric)
        print_batch_step(
            batch_index + 1,
            batch_added,
            cumulative,
            metric=args.metric,
            delta=step_delta,
        )

        batches_run += 1
        save_state(state_path, {
            "next_batch": batch_index + 1,
            "cumulative": cumulative,
            "history": history,
            "identifier": identifier,
            "metric": args.metric,
        })

        if is_stable(history, args.delta, args.patience):
            stop_reason = (
                f"{args.metric.upper()} 连续 {args.patience} 步变化 < {args.delta:.3f}，判定收敛"
            )
            break
    else:
        if start_batch >= len(batches):
            stop_reason = "已全部跑完（state 显示无剩余 batch）"
        else:
            stop_reason = "数据集已遍历完毕"

    print()
    if stop_reason:
        print(f"停止原因: {stop_reason}")

    generate_num = base_config.get("generate_num", 1)
    ex_report, custom_report = cumulative_to_report(cumulative)
    print_report_header(identifier, generate_num, cumulative["samples_seen"])
    print_eval_report(ex_report, custom_report, generate_num)

    if history:
        print("收敛曲线 ({}):".format(args.metric.upper()))
        print("  " + " → ".join(f"{v:.4f}" for v in history))

    if os.environ.get("SQURVE_EVAL_MODE", "full").lower() != "minimal":
        _persist_batch_scores(
            identifier=identifier,
            dataset_name=args.dataset,
            method=args.method,
            config_path=config_path,
            generate_num=generate_num,
            save_lis=[str(cumulative_save)],
            eval_config=eval_config,
            history=history,
            metric=args.metric,
            cumulative=cumulative,
        )


def _persist_batch_scores(
        *,
        identifier: str,
        dataset_name: str,
        method: str,
        config_path: str,
        generate_num: int,
        save_lis: list[str],
        eval_config: dict,
        history: list[float],
        metric: str,
        cumulative: dict,
) -> Path:
    run_id = f"{identifier}-batch-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
    output_dir = Path(os.environ.get("SQURVE_EVAL_OUTPUT_DIR", project_root / "artifacts" / run_id))
    output_dir.mkdir(parents=True, exist_ok=True)
    with _suppress_eval_warnings():
        ex_result = evaluate_with_details(save_lis, config=eval_config, quiet=True)
        custom_results = _run_custom_metrics_with_details(save_lis, config=eval_config, quiet=True)
    data_lists = [load_dataset(path) for path in save_lis]
    token_data = collect_all_token_data()
    scores = build_scores(
        run_id=run_id,
        method=method,
        dataset_name=dataset_name,
        split=eval_config.get("split", "dev"),
        generate_num=generate_num,
        config_path=str(config_repo_path(dataset_name, method)),
        data_lists=data_lists,
        ex_result=ex_result,
        custom_results=custom_results,
        token_data=token_data,
        base_dataset=None,
        scope="batch",
        statistical_validity="batch",
        convergence={
            "metric": metric,
            "history": history,
            "samples_seen": cumulative.get("samples_seen"),
        },
    )
    scores_path = persist_scores_bundle(
        output_dir=output_dir,
        scores=scores,
        token_data=token_data,
    )["scores"]
    print(f"scores.json: {scores_path}")
    return scores_path


if __name__ == "__main__":
    main()

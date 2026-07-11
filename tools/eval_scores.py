#!/usr/bin/env python3
"""Build scores.json from saved reproduce datasets."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))



def resolve_saved_dataset_path(path: str | Path) -> Path:
    path = Path(path)
    if path.exists():
        return path
    stem = path.stem
    candidates = [
        p for p in sorted(path.parent.glob(stem + "*.json"))
        if p.stem == stem or p.stem.startswith(stem + "_")
    ]
    if candidates:
        return candidates[0]
    return path


def load_json_dataset(path: str | Path):
    path = Path(path)
    if not path.exists():
        return None
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def load_data_lists(save_lis: list[str]) -> list[list[dict]]:
    return [load_json_dataset(resolve_saved_dataset_path(path)) for path in save_lis]


def build_scores_from_paths(
        *,
        save_lis: list[str],
        config_path: str,
        run_id: str,
        dataset_name: str,
        method: str,
        split: str = "dev",
        generate_num: int = 1,
) -> dict:
    from core.llm.token_logger import collect_all_token_data
    from reproduce.eval.utils import _load_dataset_from_engine, evaluate_with_details
    from reproduce.metrics.assembly import build_scores
    from reproduce.runner.run import _run_custom_metrics_with_details

    data_lists = load_data_lists(save_lis)
    ex_result = evaluate_with_details(save_lis, config_path=config_path, quiet=True)
    custom_results = _run_custom_metrics_with_details(save_lis, config_path=config_path, quiet=True)
    token_data = collect_all_token_data()
    return build_scores(
        run_id=run_id,
        method=method,
        dataset_name=dataset_name,
        split=split,
        generate_num=generate_num,
        config_path=config_path,
        data_lists=data_lists,
        ex_result=ex_result,
        custom_results=custom_results,
        token_data=token_data,
        base_dataset=_load_dataset_from_engine(config_path=config_path),
    )


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Evaluate saved reproduce outputs into scores.json")
    parser.add_argument("--save-lis", nargs="+", required=True)
    parser.add_argument("--config", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--dataset", required=True)
    parser.add_argument("--method", required=True)
    parser.add_argument("--split", default="dev")
    parser.add_argument("--generate-num", type=int, default=1)
    parser.add_argument("--output", required=True)
    args = parser.parse_args(argv)

    scores = build_scores_from_paths(
        save_lis=args.save_lis,
        config_path=args.config,
        run_id=args.run_id,
        dataset_name=args.dataset,
        method=args.method,
        split=args.split,
        generate_num=args.generate_num,
    )
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(scores, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

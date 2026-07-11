#!/usr/bin/env python3
"""Render a weakness profile from scores.json."""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path

from reproduce.metrics.profile import build_weakness_profile


def build_weakness_json(scores: dict, top_n: int = 5) -> dict:
    aggregate = scores.get("aggregate") or {}
    error_dist = aggregate.get("error_root_distribution") or {}
    ranked_errors = sorted(error_dist.items(), key=lambda item: item[1].get("count", 0), reverse=True)
    return {
        "run_id": scores.get("run_id"),
        "sample_count": scores.get("sample_count"),
        "aggregate": {
            "ex": (aggregate.get("ex") or {}).get("avg") if isinstance(aggregate.get("ex"), dict) else aggregate.get("ex"),
            "em": (aggregate.get("em") or {}).get("avg") if isinstance(aggregate.get("em"), dict) else aggregate.get("em"),
            "ves": (aggregate.get("ves") or {}).get("avg") if isinstance(aggregate.get("ves"), dict) else aggregate.get("ves"),
            "error_root_distribution": error_dist,
        },
        "by_hardness": scores.get("by_hardness") or {},
        "by_sql_feature": scores.get("by_sql_feature") or {},
        "top_error_roots": [
            {"root": root, **stats}
            for root, stats in ranked_errors[:top_n]
        ],
        "examples_by_root": _examples_by_root(scores.get("per_sample") or [], top_n),
    }


def render_profile(scores: dict, top_n: int = 5) -> str:
    markdown = build_weakness_profile(scores)
    examples = _examples_by_root(scores.get("per_sample") or [], top_n)
    lines = [markdown.rstrip(), "", "## Typical Failed Samples"]
    if not examples:
        lines.append("- none")
    for root, rows in examples.items():
        lines.append(f"### {root}")
        for row in rows:
            lines.extend([
                f"- {row.get('instance_id')}: {row.get('question')}",
                f"  - pred_sql: `{row.get('pred_sql')}`",
                f"  - gold_sql: `{row.get('gold_sql')}`",
            ])
    return "\n".join(lines) + "\n"


def _examples_by_root(per_sample: list[dict], top_n: int) -> dict:
    grouped = defaultdict(list)
    for row in per_sample:
        root = row.get("error_root")
        if root and len(grouped[root]) < top_n:
            grouped[root].append(row)
    return dict(grouped)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Render weakness profile markdown")
    parser.add_argument("scores")
    parser.add_argument("--output", default="weakness_profile.md")
    parser.add_argument("--json-output")
    parser.add_argument("--top-n", type=int, default=5)
    args = parser.parse_args(argv)

    scores = json.loads(Path(args.scores).read_text(encoding="utf-8"))
    Path(args.output).write_text(render_profile(scores, top_n=args.top_n), encoding="utf-8")
    if args.json_output:
        Path(args.json_output).write_text(
            json.dumps(build_weakness_json(scores, top_n=args.top_n), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

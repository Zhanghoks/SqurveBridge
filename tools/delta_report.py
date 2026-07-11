#!/usr/bin/env python3
"""Compare two scores.json files and render a Meta-Evo delta report."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from reproduce.metrics.evolution import compare_scores
from reproduce.metrics.mcts.rollout import score_from_scores, rollout_verdict


def build_delta_report(
        previous: dict,
        current: dict,
        metric: str = "ex",
        dry_threshold: float = 0.01,
        regression_threshold: float = 0.02,
) -> dict:
    comparison = compare_scores(previous, current)
    verdict = rollout_verdict(
        baseline=score_from_scores(previous, metric),
        current=score_from_scores(current, metric),
        dry_threshold=dry_threshold,
        regression_threshold=regression_threshold,
    )
    return {"comparison": comparison, "verdict": verdict, "metric": metric}


def render_markdown(report: dict) -> str:
    verdict = report["verdict"]
    lines = [
        f"# Delta Report: {verdict['verdict']}",
        "",
        f"- Metric: {report.get('metric')}",
        f"- Baseline: {verdict.get('baseline')}",
        f"- Current: {verdict.get('current')}",
        f"- Delta: {verdict.get('delta')}",
        "",
        "## Metrics",
    ]
    for name, stats in (report.get("comparison", {}).get("metrics") or {}).items():
        lines.append(f"- {name}: {stats.get('previous')} -> {stats.get('current')} (delta={stats.get('delta')})")
    regressions = (report.get("comparison", {}).get("regressions") or {}).get("ex") or []
    lines.extend(["", "## Regressions"])
    lines.append("- none" if not regressions else "- " + ", ".join(regressions))
    return "\n".join(lines) + "\n"


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Compare two scores.json files")
    parser.add_argument("previous")
    parser.add_argument("current")
    parser.add_argument("--metric", default="ex")
    parser.add_argument("--json-output")
    parser.add_argument("--markdown-output")
    args = parser.parse_args(argv)

    previous = json.loads(Path(args.previous).read_text(encoding="utf-8"))
    current = json.loads(Path(args.current).read_text(encoding="utf-8"))
    report = build_delta_report(previous, current, metric=args.metric)
    markdown = render_markdown(report)
    if args.json_output:
        Path(args.json_output).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    if args.markdown_output:
        Path(args.markdown_output).write_text(markdown, encoding="utf-8")
    if not args.json_output and not args.markdown_output:
        print(markdown)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

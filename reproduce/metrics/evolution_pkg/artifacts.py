"""Artifact IO for artifacts/evolve."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from reproduce.metrics.evolution import compare_scores
from reproduce.metrics.evolution_pkg.process_artifacts import (
    append_process_event,
    init_process_artifacts,
    render_progress,
    update_artifact_manifest,
)
from reproduce.metrics.evolution_pkg.state_machine import (
    EvolvePhase,
    initialize_state,
    read_state,
    transition_evolve_dir,
    write_state,
)


def init_evolve_dir(
        evolve_slug: str,
        *,
        artifacts_root: str | Path = "artifacts/evolve",
        baseline_run_slug: str | None = None,
        method: str | None = None,
        benchmark: str | None = None,
        policy: str = "bounded_search_default",
        baseline_summary: str | None = None,
        meta_evo_input: dict[str, Any] | None = None,
        weakness_markdown: str | None = None,
        weakness_profile: dict[str, Any] | None = None,
        weakness_analysis: str | None = None,
) -> Path:
    root = Path(artifacts_root)
    root.mkdir(parents=True, exist_ok=True)
    memory = root / "evolution-memory.md"
    if not memory.exists():
        memory.write_text("# Evolution Memory\n\n", encoding="utf-8")

    evolve_dir = root / evolve_slug
    (evolve_dir / "nodes").mkdir(parents=True, exist_ok=True)
    state = initialize_state(
        slug=evolve_slug,
        baseline_run_slug=baseline_run_slug,
        method=method,
        benchmark=benchmark,
        policy=policy,
        budget={
            "dry_round_limit": 2,
            "smoke_rollouts": 20,
            "bounded_rollouts": 10,
        },
    )
    write_state(evolve_dir / "evolve-state.json", state)
    init_process_artifacts(evolve_dir)
    if baseline_summary is not None:
        (evolve_dir / "baseline-summary.md").write_text(baseline_summary, encoding="utf-8")
    if meta_evo_input is not None:
        write_json(evolve_dir / "meta-evo-input.json", meta_evo_input)
    if weakness_markdown is not None:
        (evolve_dir / "weakness_profile.md").write_text(weakness_markdown, encoding="utf-8")
    if weakness_profile is not None:
        write_json(evolve_dir / "weakness-profile.json", weakness_profile)
    if weakness_analysis is not None:
        (evolve_dir / "weakness-analysis.md").write_text(weakness_analysis, encoding="utf-8")

    journal_path = evolve_dir / "journal.json"
    if not journal_path.exists():
        write_json(journal_path, {
            "evolve_slug": evolve_slug,
            "baseline_run_slug": baseline_run_slug,
            "method": method,
            "benchmark": benchmark,
            "policy": policy,
            "round": 0,
            "rounds_completed": 0,
            "nodes": [],
            "best_node": None,
            "recommendation": None,
            "stagnation": {
                "branch_stagnant": [],
                "global_stagnant": False,
                "dry_rounds": 0,
            },
        })
    update_artifact_manifest(
        evolve_dir,
        ["evolve-state.json", "journal.json", "process-events.jsonl", "artifact-manifest.json", "progress.md"],
        kind="state",
        phase="initialized",
        round=0,
        producer="artifacts.init_evolve_dir",
    )
    append_process_event(evolve_dir, {
        "type": "transition",
        "phase": "initialized",
        "round": 0,
        "producer": "artifacts.init_evolve_dir",
        "outputs": ["evolve-state.json", "journal.json"],
        "status": "completed",
    })
    render_progress(evolve_dir)
    return evolve_dir


def create_node_dir(evolve_dir: str | Path, node_id: str) -> Path:
    node_dir = Path(evolve_dir) / "nodes" / node_id
    node_dir.mkdir(parents=True, exist_ok=True)
    return node_dir


def write_json(path: str | Path, data: Any) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def read_json(path: str | Path) -> Any:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write_status(node_dir: str | Path, status: str, **extra: Any) -> Path:
    payload = {"status": status, "updated_at": _now(), **extra}
    return write_json(Path(node_dir) / "status.json", payload)


def write_comparison_report(
        evolve_dir: str | Path,
        *,
        baseline_scores: dict[str, Any],
        best_scores: dict[str, Any],
) -> Path:
    comparison = compare_scores(baseline_scores, best_scores)
    lines = [
        "# Baseline vs Best Candidate",
        "",
        "| Metric | Baseline | Best | Delta |",
        "|---|---:|---:|---:|",
    ]
    for metric, stats in (comparison.get("metrics") or {}).items():
        lines.append(
            f"| {metric} | {_fmt(stats.get('previous'))} | {_fmt(stats.get('current'))} | {_fmt(stats.get('delta'))} |"
        )
    regressions = (comparison.get("regressions") or {}).get("ex") or []
    improvements = (comparison.get("improvements") or {}).get("ex") or []
    lines.extend([
        "",
        f"- Regressions: {len(regressions)}",
        f"- Improvements: {len(improvements)}",
    ])
    path = Path(evolve_dir) / "comparison-report.md"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    write_json(Path(evolve_dir) / "comparison-report.json", comparison)
    return path


def write_best_node_report(
        evolve_dir: str | Path,
        *,
        node: dict[str, Any],
        comparison_summary: str = "",
) -> Path:
    lines = [
        f"# Best Node: {node.get('node_id')}",
        "",
        "## Why Recommended",
        comparison_summary or "- Selected by highest bounded fitness.",
        "",
        "## Change Summary",
        f"- Stage: {node.get('stage')}",
        f"- Status: {node.get('status')}",
        f"- Fitness: {node.get('fitness')}",
        f"- Patch: nodes/{node.get('node_id')}/{node.get('patch_path', 'patch.diff')}",
    ]
    path = Path(evolve_dir) / "best-node.md"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def record_user_review(
        evolve_dir: str | Path,
        *,
        recommendation: str,
        outcome: str,
        best_node_id: str | None = None,
        summary: str = "",
) -> dict[str, Any]:
    evolve_dir = Path(evolve_dir)
    journal_path = evolve_dir / "journal.json"
    journal = read_json(journal_path)
    journal["recommendation"] = recommendation
    write_json(journal_path, journal)

    experience = [
        f"# Evolution Experience: {journal.get('evolve_slug')}",
        "",
        f"## Outcome: {outcome}",
        f"- Best node: {best_node_id or journal.get('best_node')}",
        f"- Recommendation: {recommendation}",
    ]
    if summary:
        experience.extend(["", "## Summary", summary])
    (evolve_dir / "experience.md").write_text("\n".join(experience) + "\n", encoding="utf-8")

    memory = evolve_dir.parent / "evolution-memory.md"
    existing = memory.read_text(encoding="utf-8") if memory.exists() else "# Evolution Memory\n\n"
    memory.write_text(
        existing.rstrip()
        + "\n\n"
        + f"## Review: {journal.get('evolve_slug')}\n"
        + f"- Outcome: {outcome}\n"
        + f"- Recommendation: {recommendation}\n"
        + f"- Best node: {best_node_id or journal.get('best_node')}\n",
        encoding="utf-8",
    )
    _record_review_state_transition(
        evolve_dir,
        outcome=outcome,
        recommendation=recommendation,
        best_node_id=best_node_id or journal.get("best_node"),
    )
    return journal


def _record_review_state_transition(
        evolve_dir: Path,
        *,
        outcome: str,
        recommendation: str,
        best_node_id: str | None,
) -> None:
    state_path = evolve_dir / "evolve-state.json"
    if not state_path.exists():
        return
    state = read_state(state_path)
    normalized = _normalize_review_outcome(outcome)
    target = {
        "accept": EvolvePhase.ACCEPTED,
        "continue": EvolvePhase.CONTINUED,
        "rollback": EvolvePhase.ROLLED_BACK,
    }[normalized]
    if state.phase != EvolvePhase.REVIEW_PENDING:
        # Backward-compatible direct review for legacy tests and pre-state-machine artifacts.
        state.phase = EvolvePhase.REVIEW_PENDING
        state.active_stage = "review"
        state.current_node = best_node_id
        write_state(state_path, state)
    transition_evolve_dir(
        evolve_dir,
        target,
        reason=f"user_review_{normalized}",
        artifact_refs=["journal.json", "experience.md", "../evolution-memory.md"],
        active_stage="review",
        current_node=best_node_id,
        kind="review",
        producer="artifacts.record_user_review",
    )


def _normalize_review_outcome(outcome: str) -> str:
    normalized = outcome.strip().lower()
    aliases = {
        "accepted": "accept",
        "accept": "accept",
        "continued": "continue",
        "continue": "continue",
        "rolled_back": "rollback",
        "rollback": "rollback",
    }
    if normalized not in aliases:
        raise ValueError(f"Invalid review outcome: {outcome}")
    return aliases[normalized]


def _fmt(value: Any) -> str:
    if value is None:
        return "-"
    if isinstance(value, float):
        return f"{value:.6g}"
    return str(value)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()

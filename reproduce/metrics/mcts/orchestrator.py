"""MCTS orchestration for Meta-Evo smoke search."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Callable, List

from reproduce.metrics.evolution_pkg.artifacts import create_node_dir, write_json, write_status
from reproduce.metrics.evolution_pkg.budget import bounded_eval_promote, smoke_gate_promote
from reproduce.metrics.evolution_pkg.fitness import compute_fitness
from reproduce.metrics.evolution_pkg.journal import EvolutionJournal
from reproduce.metrics.evolution_pkg.node import EvolutionNode
from reproduce.metrics.evolution_pkg.process_artifacts import (
    append_process_event,
    create_attempt_dir,
    render_progress,
    update_artifact_manifest,
    write_json as write_process_json,
)
from reproduce.metrics.evolution_pkg.state_machine import (
    EvolvePhase,
    next_resume_action,
    read_state,
    transition_evolve_dir,
)
from reproduce.metrics.mcts.expand import Action, generate_actions, load_actions
from reproduce.metrics.mcts.rollout import run_action_rollout, rollout_verdict
from reproduce.metrics.mcts.tree import (
    TreeNode,
    add_child,
    backpropagate,
    best_path,
    decay_exploration,
    progressive_width,
    select_leaf,
)


def select_leaf_for_progress(root: TreeNode, *, progress: float, exploration: float) -> TreeNode:
    if progress >= 0.7 and root.children:
        return _top_k_exploitation_leaf(root)
    return select_leaf(root, exploration=exploration)


def should_force_backprop(iteration: int, rollouts: int, node: TreeNode, recent_best: float | None) -> bool:
    progress = (iteration + 1) / max(rollouts, 1)
    if recent_best is not None and node.average_score >= recent_best:
        return False
    if progress > 0.8:
        return iteration % 2 == 0
    if progress > 0.4:
        return iteration % 3 == 0
    return False


def run_search(
        *,
        actions: List[Action],
        rollouts: int = 20,
        simulator: Callable[[Action, int], float | dict[str, Any]],
        baseline_score: float = 0.0,
        journal_path: str | Path | None = None,
        evolve_dir: str | Path | None = None,
        stage: str = "smoke",
        smoke_promote_top_k: int = 2,
        bounded_promote_top_k: int = 1,
        dry_round_limit: int = 2,
) -> dict:
    root = TreeNode(node_id="root")
    nodes_by_id = {"root": root}
    used_action_ids = set()
    journal = EvolutionJournal.read(journal_path) if journal_path else None

    for iteration in range(rollouts):
        progress = iteration / max(rollouts, 1)
        exploration = decay_exploration(1.41421356237, progress)
        root_width = progressive_width(root.visits + 1)
        if len(root.children) < root_width:
            leaf = root
            width = root_width
        else:
            leaf = select_leaf_for_progress(root, progress=progress, exploration=exploration)
            width = progressive_width(max(leaf.visits, 1))
        available = [action for action in actions if action.action_id not in used_action_ids]
        if available and len(leaf.children) < width:
            action = available[0]
            used_action_ids.add(action.action_id)
            branch_id = len(nodes_by_id) if leaf.node_id == "root" else leaf.branch_id
            leaf = add_child(leaf, f"node-{len(nodes_by_id)}", action.to_dict(), branch_id=branch_id)
            nodes_by_id[leaf.node_id] = leaf

        if not leaf.action:
            continue
        recent_best = _recent_best(root, window=4)
        rollout = _normalize_rollout_result(
            simulator(Action.from_dict(leaf.action), iteration),
            baseline_score=baseline_score,
        )
        backpropagate(leaf, rollout["tree_score"], nodes_by_id)
        if should_force_backprop(iteration, rollouts, leaf, recent_best):
            leaf.forced_backprop = True
        if journal is not None:
            _record_rollout_node(
                journal=journal,
                evolve_dir=evolve_dir,
                tree_node=leaf,
                rollout=rollout,
                baseline_score=baseline_score,
                stage=stage,
            )
            if stage == "smoke":
                smoke_gate_promote(journal.nodes, promote_top_k=smoke_promote_top_k)
            elif stage == "bounded":
                bounded_eval_promote(journal.nodes, promote_top_k=bounded_promote_top_k)
            _rewrite_node_artifacts(journal=journal, evolve_dir=evolve_dir)
            journal.rounds_completed = iteration + 1
            journal.global_stagnant()
            for branch_id in {node.branch_id for node in journal.nodes}:
                journal.branch_stagnant(branch_id)
            journal.write(journal_path)
            if int(journal.stagnation.get("dry_rounds") or 0) >= dry_round_limit:
                break

    path = best_path(root)
    best_score = path[-1].average_score if path else baseline_score
    return {
        "tree": root.to_dict(),
        "best_path": [node.action for node in path if node.action],
        "verdict": rollout_verdict(baseline=baseline_score, current=best_score),
    }


def run_bounded_funnel(
        *,
        actions: List[Action],
        smoke_simulator: Callable[[Action, int], float | dict[str, Any]],
        bounded_simulator: Callable[[Action, int], float | dict[str, Any]] | None = None,
        full_simulator: Callable[[Action, int], float | dict[str, Any]] | None = None,
        baseline_score: float = 0.0,
        journal_path: str | Path | None = None,
        evolve_dir: str | Path | None = None,
        smoke_rollouts: int = 20,
        bounded_rollouts: int = 10,
        smoke_promote_top_k: int = 2,
        bounded_promote_top_k: int = 1,
        dry_round_limit: int = 2,
) -> dict[str, Any]:
    state = _prepare_funnel_state(evolve_dir)
    journal = EvolutionJournal.read(journal_path) if journal_path else None
    action = next_resume_action(state, journal) if state and journal else "run_smoke"

    smoke_result = None
    if action == "run_smoke":
        _transition_if_possible(evolve_dir, EvolvePhase.SMOKE_RUNNING, reason="run_smoke", active_stage="smoke")
        smoke_result = run_search(
            actions=actions,
            rollouts=smoke_rollouts,
            simulator=smoke_simulator,
            baseline_score=baseline_score,
            journal_path=journal_path,
            evolve_dir=evolve_dir,
            stage="smoke",
            smoke_promote_top_k=smoke_promote_top_k,
            dry_round_limit=dry_round_limit,
        )
        _write_tree_artifact(evolve_dir, "smoke", smoke_result)
        if journal_path:
            journal = EvolutionJournal.read(journal_path)
            if [node for node in journal.nodes if node.promoted and node.status == "pass"]:
                _transition_if_possible(
                    evolve_dir,
                    EvolvePhase.SMOKE_PROMOTED,
                    reason="smoke_promoted",
                    active_stage=None,
                    artifact_refs=["journal.json", "mcts-tree.smoke.json"],
                )
            else:
                _transition_if_possible(
                    evolve_dir,
                    EvolvePhase.STOPPED,
                    reason="smoke_no_promotions",
                    active_stage=None,
                    artifact_refs=["journal.json", "mcts-tree.smoke.json"],
                )
    elif action in {"run_bounded", "run_full", "reconcile_review", "await_review"}:
        smoke_result = {"skipped": True, "reason": f"resume_action:{action}"}

    if not journal_path:
        return {"smoke": smoke_result, "bounded": None, "full": None}

    journal = EvolutionJournal.read(journal_path)
    smoke_promoted = [node.node_id for node in journal.nodes if node.promoted and node.status == "pass"]
    bounded_actions = [
        Action.from_dict((journal.get_node(node_id).metadata or {}).get("action") or {})
        for node_id in smoke_promoted[:smoke_promote_top_k]
    ]
    bounded_result = None
    state = _read_funnel_state(evolve_dir)
    action = next_resume_action(state, journal) if state else "run_bounded"
    if bounded_simulator and bounded_actions and action == "run_bounded":
        _transition_if_possible(evolve_dir, EvolvePhase.BOUNDED_RUNNING, reason="run_bounded", active_stage="bounded")
        bounded_result = run_search(
            actions=bounded_actions,
            rollouts=bounded_rollouts,
            simulator=bounded_simulator,
            baseline_score=baseline_score,
            journal_path=journal_path,
            evolve_dir=evolve_dir,
            stage="bounded",
            bounded_promote_top_k=bounded_promote_top_k,
            dry_round_limit=dry_round_limit,
        )
        _write_tree_artifact(evolve_dir, "bounded", bounded_result)
        journal = EvolutionJournal.read(journal_path)
        if journal.best_node:
            _transition_if_possible(
                evolve_dir,
                EvolvePhase.BOUNDED_PROMOTED,
                reason="bounded_promoted",
                active_stage=None,
                current_node=journal.best_node,
                artifact_refs=["journal.json", "mcts-tree.bounded.json"],
            )
        else:
            _transition_if_possible(
                evolve_dir,
                EvolvePhase.STOPPED,
                reason="bounded_no_best_node",
                active_stage=None,
                artifact_refs=["journal.json", "mcts-tree.bounded.json"],
            )
    elif action in {"run_full", "reconcile_review", "await_review"}:
        bounded_result = {"skipped": True, "reason": f"resume_action:{action}"}

    full_result = None
    journal = EvolutionJournal.read(journal_path)
    state = _read_funnel_state(evolve_dir)
    action = next_resume_action(state, journal) if state else "run_full"
    if full_simulator and action in {"run_full", "reconcile_review"}:
        best = journal.get_node(journal.best_node) if journal.best_node else None
        if best is not None:
            _transition_if_possible(
                evolve_dir,
                EvolvePhase.FULL_CONFIRMING,
                reason="run_full_confirmation",
                active_stage="full",
                current_node=best.node_id,
                artifact_refs=["journal.json"],
            )
            full_result = full_simulator(Action.from_dict((best.metadata or {}).get("action") or {}), 0)
            _write_full_artifacts(evolve_dir, best.node_id, full_result)
            _transition_if_possible(
                evolve_dir,
                EvolvePhase.REVIEW_PENDING,
                reason="full_confirmation_complete",
                active_stage=None,
                current_node=best.node_id,
                artifact_refs=[
                    f"nodes/{best.node_id}/scores.full.json",
                    "comparison-report.json",
                    "comparison-report.md",
                    "journal.json",
                ],
            )
    elif action == "await_review":
        full_result = {"skipped": True, "reason": "await_review"}

    return {"smoke": smoke_result, "bounded": bounded_result, "full": full_result}


def _top_k_exploitation_leaf(root: TreeNode, top_k: int = 3) -> TreeNode:
    candidates = sorted(root.children, key=lambda node: (node.average_score, node.visits), reverse=True)[:top_k]
    node = candidates[0] if candidates else root
    while node.children:
        ranked = sorted(node.children, key=lambda child: (child.average_score, child.visits), reverse=True)
        node = ranked[0]
    return node


def _recent_best(root: TreeNode, window: int = 4) -> float | None:
    scores = root.scores[-window:]
    return max(scores) if scores else None


def _normalize_rollout_result(result: float | dict[str, Any], *, baseline_score: float) -> dict[str, Any]:
    if isinstance(result, dict):
        score = result.get("score")
        verdict = result.get("verdict") or rollout_verdict(baseline=baseline_score, current=score)
        tree_score = float(score) if isinstance(score, (int, float)) else baseline_score
        return {**result, "score": score, "tree_score": tree_score, "verdict": verdict}
    score = float(result)
    return {
        "score": score,
        "tree_score": score,
        "verdict": rollout_verdict(baseline=baseline_score, current=score),
    }


def _record_rollout_node(
        *,
        journal: EvolutionJournal,
        evolve_dir: str | Path | None,
        tree_node: TreeNode,
        rollout: dict[str, Any],
        baseline_score: float,
        stage: str,
) -> None:
    action = tree_node.action or {}
    existing_ids = {node.node_id for node in journal.nodes}
    score = rollout.get("score")
    verdict = rollout.get("verdict") or rollout_verdict(baseline=baseline_score, current=score)
    verdict_name = verdict.get("verdict")
    status = "buggy" if verdict_name in {"STOP", "REGRESSION"} else "pass"
    fitness = compute_fitness(ex=score if isinstance(score, (int, float)) else None)
    score_metadata = _scores_metadata(stage, rollout)
    if tree_node.node_id in existing_ids:
        existing = journal.get_node(tree_node.node_id)
        merged_scores = {**existing.scores, **score_metadata}
        merged_metadata = {**existing.metadata, "action": action}
        journal.update_node(
            tree_node.node_id,
            status=status,
            fitness=fitness,
            scores=merged_scores,
            delta=verdict,
            metadata=merged_metadata,
        )
    else:
        node = EvolutionNode(
            node_id=tree_node.node_id,
            parent_id=tree_node.parent_id or "baseline",
            branch_id=tree_node.branch_id,
            stage=stage,
            method=journal.method or "",
            benchmark=journal.benchmark or "",
            target_dimensions=[str(action.get("target_metric", "ex"))],
            change_scope=str(action.get("scope", "")),
            fitness=fitness,
            status=status,
            decision="candidate",
            scores=score_metadata,
            delta=verdict,
            metadata={"action": action},
        )
        journal.add_node(node)
    if evolve_dir:
        node_dir = create_node_dir(evolve_dir, tree_node.node_id)
        attempt_dir = create_attempt_dir(evolve_dir, tree_node.node_id, stage)
        _write_action_artifacts(node_dir, action, rollout)
        _write_scores_artifact(node_dir, stage, rollout)
        _write_attempt_artifacts(attempt_dir, stage, action, rollout, status, fitness)
        write_json(node_dir / "node.json", journal.get_node(tree_node.node_id).to_dict())
        write_json(node_dir / "delta.json", verdict)
        write_status(node_dir, status, fitness=fitness, stage=stage, verdict=verdict)
        update_artifact_manifest(
            evolve_dir,
            [
                node_dir / "node.json",
                node_dir / "delta.json",
                node_dir / "status.json",
                attempt_dir / "command.json",
                attempt_dir / "status.json",
            ],
            kind="node",
            phase=f"{stage}_running",
            round=journal.round,
            producer="mcts.run_search",
            node_id=tree_node.node_id,
        )
        append_process_event(evolve_dir, {
            "type": "artifact",
            "phase": f"{stage}_running",
            "round": journal.round,
            "node_id": tree_node.node_id,
            "stage": stage,
            "producer": "mcts.run_search",
            "inputs": ["action-pool.json"],
            "outputs": [
                f"nodes/{tree_node.node_id}/node.json",
                f"nodes/{tree_node.node_id}/attempts/{attempt_dir.name}/status.json",
            ],
            "status": status,
        })
        render_progress(evolve_dir)


def _scores_metadata(stage: str, rollout: dict[str, Any]) -> dict[str, Any]:
    metadata = {}
    if rollout.get("score") is not None:
        metadata[stage] = rollout.get("score")
    return metadata


def _write_action_artifacts(node_dir: Path, action: dict[str, Any], rollout: dict[str, Any]) -> None:
    plan_path = node_dir / "change-plan.md"
    if not plan_path.exists():
        plan_path.write_text(f"# Change Plan\n\n{action.get('description', '')}\n", encoding="utf-8")
    patch_path = node_dir / "patch.diff"
    if not patch_path.exists():
        patch_path.write_text(json.dumps(action.get("patches") or [], ensure_ascii=False, indent=2), encoding="utf-8")
    command = action.get("run_command") or rollout.get("run_command") or ""
    command_path = node_dir / "run-command.sh"
    if not command_path.exists():
        command_path.write_text((command.rstrip() + "\n") if command else "# command unavailable\n", encoding="utf-8")
    report_path = node_dir / "evaluator-report.md"
    if not report_path.exists():
        report_path.write_text("# Evaluator Report\n\nPending bounded evaluation report.\n", encoding="utf-8")


def _write_scores_artifact(node_dir: Path, stage: str, rollout: dict[str, Any]) -> None:
    scores = rollout.get("scores")
    if not isinstance(scores, dict):
        return
    filename = {
        "smoke": "scores.smoke50.json",
        "bounded": "scores.bounded200.json",
        "full": "scores.full.json",
    }.get(stage, f"scores.{stage}.json")
    write_json(node_dir / filename, scores)


def _write_attempt_artifacts(
        attempt_dir: Path,
        stage: str,
        action: dict[str, Any],
        rollout: dict[str, Any],
        status: str,
        fitness: float | None,
) -> None:
    write_process_json(attempt_dir / "command.json", {
        "stage": stage,
        "action_id": action.get("action_id"),
        "run_command": action.get("run_command") or rollout.get("run_command") or "",
    })
    (attempt_dir / "stdout.txt").write_text(str(rollout.get("stdout", "")), encoding="utf-8")
    (attempt_dir / "stderr.txt").write_text(str(rollout.get("stderr", "")), encoding="utf-8")
    if isinstance(rollout.get("scores"), dict):
        write_process_json(attempt_dir / "scores.json", rollout["scores"])
    write_process_json(attempt_dir / "status.json", {
        "status": status,
        "fitness": fitness,
        "verdict": rollout.get("verdict"),
    })


def _prepare_funnel_state(evolve_dir: str | Path | None):
    state = _read_funnel_state(evolve_dir)
    if state and state.phase in {EvolvePhase.INITIALIZED, EvolvePhase.BASELINE_LOADED, EvolvePhase.WEAKNESS_PROFILED}:
        return _transition_if_possible(
            evolve_dir,
            EvolvePhase.ACTIONS_GENERATED,
            reason="funnel_actions_ready",
            active_stage=None,
            artifact_refs=["journal.json"],
        )
    return state


def _read_funnel_state(evolve_dir: str | Path | None):
    if not evolve_dir:
        return None
    state_path = Path(evolve_dir) / "evolve-state.json"
    return read_state(state_path) if state_path.exists() else None


def _transition_if_possible(
        evolve_dir: str | Path | None,
        phase: EvolvePhase,
        *,
        reason: str,
        active_stage: str | None = None,
        current_node: str | None = None,
        artifact_refs: list[str] | None = None,
):
    if not evolve_dir:
        return None
    try:
        return transition_evolve_dir(
            evolve_dir,
            phase,
            reason=reason,
            artifact_refs=artifact_refs or ["journal.json"],
            active_stage=active_stage,
            current_node=current_node,
            producer="mcts.run_bounded_funnel",
        )
    except ValueError:
        return _read_funnel_state(evolve_dir)


def _write_tree_artifact(evolve_dir: str | Path | None, stage: str, result: dict[str, Any] | None) -> None:
    if not evolve_dir or result is None:
        return
    path = Path(evolve_dir) / f"mcts-tree.{stage}.json"
    write_process_json(path, result)
    update_artifact_manifest(
        evolve_dir,
        [path],
        kind="report",
        phase=f"{stage}_running",
        producer="mcts.run_bounded_funnel",
    )


def _write_full_artifacts(evolve_dir: str | Path | None, node_id: str, full_result: Any) -> None:
    if not evolve_dir:
        return
    evolve_dir = Path(evolve_dir)
    node_dir = create_node_dir(evolve_dir, node_id)
    scores = full_result.get("scores") if isinstance(full_result, dict) else None
    if isinstance(scores, dict):
        write_process_json(node_dir / "scores.full.json", scores)
    else:
        write_process_json(node_dir / "scores.full.json", {"result": full_result})
    write_process_json(evolve_dir / "comparison-report.json", {
        "best_node": node_id,
        "full_result": full_result,
    })
    (evolve_dir / "comparison-report.md").write_text(
        f"# Full Confirmation\n\n- Best node: {node_id}\n",
        encoding="utf-8",
    )
    update_artifact_manifest(
        evolve_dir,
        [
            node_dir / "scores.full.json",
            evolve_dir / "comparison-report.json",
            evolve_dir / "comparison-report.md",
        ],
        kind="score",
        phase="full_confirming",
        producer="mcts.run_bounded_funnel",
        node_id=node_id,
    )


def _rewrite_node_artifacts(*, journal: EvolutionJournal, evolve_dir: str | Path | None) -> None:
    if not evolve_dir:
        return
    for node in journal.nodes:
        node_dir = create_node_dir(evolve_dir, node.node_id)
        write_json(node_dir / "node.json", node.to_dict())


def _load_policy(path: str | Path | None) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8")) if path else {}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Run deterministic MCTS over a JSON action pool")
    parser.add_argument("--actions", required=True, help="JSON file containing candidate actions")
    parser.add_argument("--weakness-profile", help="Optional weakness profile used when action pool is empty")
    parser.add_argument("--rollouts", type=int, default=20)
    parser.add_argument("--baseline-score", type=float, default=0.0)
    parser.add_argument("--simulated-scores", help="Optional JSON map action_id -> score")
    parser.add_argument("--repo-root", help="Run real rollouts in git worktrees rooted at this repo")
    parser.add_argument("--smoke-command", help="Command to run inside each worktree")
    parser.add_argument("--scores-path", help="scores.json path relative to worktree after smoke command")
    parser.add_argument("--metric", default="ex", help="Metric path to optimize, e.g. ex or cf1.cf1_join.avg")
    parser.add_argument("--base-ref", default="HEAD")
    parser.add_argument("--policy-config", help="Optional reproduce/configs/evolution/*.json policy file")
    parser.add_argument("--journal", help="Optional artifacts/evolve/<slug>/journal.json to update")
    parser.add_argument("--evolve-dir", help="Optional artifacts/evolve/<slug> directory for node artifacts")
    parser.add_argument("--stage", default="smoke", choices=["smoke", "bounded", "full"])
    parser.add_argument("--output", help="Write search result JSON to this path")
    args = parser.parse_args(argv)

    actions = load_actions(args.actions)
    if not actions and args.weakness_profile:
        actions = generate_actions(Path(args.weakness_profile).read_text(encoding="utf-8"))
    simulated = json.loads(Path(args.simulated_scores).read_text(encoding="utf-8")) if args.simulated_scores else {}
    policy = _load_policy(args.policy_config)
    policy_env = dict(policy.get("env") or {})
    promotion = policy.get("promotion") or {}
    dry_round_limit = int(policy.get("dry_round_limit", 2))
    if "promote_top_k" in policy:
        if args.stage == "smoke":
            promotion.setdefault("smoke_top_k", policy["promote_top_k"])
        elif args.stage == "bounded":
            promotion.setdefault("bounded_top_k", policy["promote_top_k"])

    def simulator(action: Action, _iteration: int) -> float | dict[str, Any]:
        if args.repo_root and args.smoke_command and args.scores_path:
            return run_action_rollout(
                repo_root=args.repo_root,
                action=action,
                smoke_command=args.smoke_command,
                scores_path=args.scores_path,
                metric=args.metric,
                baseline_score=args.baseline_score,
                base_ref=args.base_ref,
                env=policy_env,
            )
        return float(simulated.get(action.action_id, args.baseline_score))

    result = run_search(
        actions=actions,
        rollouts=args.rollouts,
        simulator=simulator,
        baseline_score=args.baseline_score,
        journal_path=args.journal,
        evolve_dir=args.evolve_dir,
        stage=args.stage,
        smoke_promote_top_k=int(promotion.get("smoke_top_k", 2)),
        bounded_promote_top_k=int(promotion.get("bounded_top_k", 1)),
        dry_round_limit=dry_round_limit,
    )
    payload = json.dumps(result, ensure_ascii=False, indent=2)
    if args.output:
        Path(args.output).write_text(payload, encoding="utf-8")
    else:
        print(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Self-evolution engine: bounded MCTS search over candidate method updates.

Package layout:

- ``mcts/``: search loop (tree policy, expansion, rollout, orchestrator)
- ``fitness``: multi-objective reward contract
- ``journal`` / ``node`` / ``artifacts`` / ``process_artifacts``: evidence ledger
- ``state_machine``: run-level phases, resume, and human gates
- ``budget`` / ``sampling``: promotion policy and bounded-slice manifests
- ``meta_input``: diagnostic payload handed to the Meta-Evo entry skill
"""

from reproduce.evolve.artifacts import (
    create_node_dir,
    init_evolve_dir,
    record_user_review,
    write_best_node_report,
    write_comparison_report,
)
from reproduce.evolve.budget import bounded_eval_promote, smoke_gate_promote
from reproduce.evolve.fitness import R_INVALID, compute_fitness, fitness_from_scores
from reproduce.evolve.journal import EvolutionJournal
from reproduce.evolve.meta_input import build_meta_evo_input
from reproduce.evolve.node import EvolutionNode

__all__ = [
    "EvolutionJournal",
    "EvolutionNode",
    "R_INVALID",
    "bounded_eval_promote",
    "build_meta_evo_input",
    "compute_fitness",
    "create_node_dir",
    "fitness_from_scores",
    "init_evolve_dir",
    "record_user_review",
    "smoke_gate_promote",
    "write_best_node_report",
    "write_comparison_report",
]

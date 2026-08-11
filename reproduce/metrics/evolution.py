"""Forwarding facade: score comparison moved to ``reproduce.eval.bundle.compare``
and the Meta-Evo payload to ``reproduce.evolve.meta_input``."""

from reproduce.eval.bundle.compare import compare_scores  # noqa: F401
from reproduce.evolve.meta_input import build_meta_evo_input  # noqa: F401

__all__ = ["build_meta_evo_input", "compare_scores"]

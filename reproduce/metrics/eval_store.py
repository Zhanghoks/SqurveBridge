"""Forwarding facade: the eval-store writer moved to ``reproduce.eval.views.store``.

Store schema v2 replaces the wide ``samples`` table with long
``sample_metrics`` / ``sample_meta`` tables derived from the metric registry,
and keeps raw question/SQL text out of the store by default (opt-in
``include_text`` writes them to a local-only ``sample_text`` table).
"""

from reproduce.eval.views.store import (  # noqa: F401
    STORE_SCHEMA_VERSION,
    load_sample_metric,
    per_sample_sources,
    persist_eval_store,
)

__all__ = [
    "STORE_SCHEMA_VERSION",
    "load_sample_metric",
    "per_sample_sources",
    "persist_eval_store",
]

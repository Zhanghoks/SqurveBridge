"""Dependency-free security policy shared by the local demo API and tests."""

from __future__ import annotations

import os
from collections.abc import Mapping

from demo.deployment import is_hf_space


AGENT_TERMINAL_ENV = "SQURVE_ENABLE_AGENT_TERMINALS"
_TRUE_VALUES = {"1", "true", "yes"}


def agent_terminals_enabled(environment: Mapping[str, str] | None = None) -> bool:
    values = os.environ if environment is None else environment
    if is_hf_space(values):
        return False
    return str(values.get(AGENT_TERMINAL_ENV, "")).strip().lower() in _TRUE_VALUES

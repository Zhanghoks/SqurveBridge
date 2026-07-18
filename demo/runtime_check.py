"""Fast dependency preflight for the local Demo App runtime."""

from __future__ import annotations

import importlib.util
import sys
from collections.abc import Callable, Iterable


REQUIRED_MODULES = (
    "flask",
    "flask_sock",
    "llama_index",
    "numpy",
    "pandas",
    "torch",
)


def missing_modules(
    modules: Iterable[str] = REQUIRED_MODULES,
    *,
    find_spec: Callable[[str], object | None] = importlib.util.find_spec,
) -> list[str]:
    return [module for module in modules if find_spec(module) is None]


def main() -> int:
    missing = missing_modules()
    if not missing:
        return 0
    print(
        "SqurveBridge runtime is incomplete; missing Python modules: "
        f"{', '.join(missing)}. Install both requirements.txt and "
        "demo/requirements.txt in the selected environment.",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Single-command status for an evolution run: where it is, what to do next.

    python3 tools/evolve_status.py --evolve-dir artifacts/evolve/<slug>

Prints one JSON object combining phase, resume action, review gates,
consistency, and a ready-to-run ``next_command``. This is the entry point
the Meta-Evo AI execution protocol uses to resume a run without relying on
chat memory.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from reproduce.evolve.state_machine import next_step


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--evolve-dir", required=True, help="artifacts/evolve/<slug> directory")
    args = parser.parse_args(argv)

    evolve_dir = Path(args.evolve_dir)
    if not (evolve_dir / "evolve-state.json").exists():
        print(json.dumps({"error": f"no evolve-state.json under {evolve_dir}"}, ensure_ascii=False))
        return 1
    print(json.dumps(next_step(evolve_dir), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

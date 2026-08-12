#!/usr/bin/env python3
"""Single-command status for an evolution run: where it is, what to do next.

    python3 tools/evolve_status.py --evolve-dir artifacts/evolve/<slug>
    python3 tools/evolve_status.py --evolve-dir <dir> --record-phase candidates_reviewed

Prints one JSON object combining phase, resume action, review gates,
consistency, and a ready-to-run ``next_command``. This is the entry point
the Meta-Evo AI execution protocol uses to resume a run without relying on
chat memory.

``--record-phase`` records a review-gate transition (``candidates_reviewed``
or ``report_reviewed``) before printing the status. Recording
``candidates_reviewed`` is refused while candidate gate blockers remain.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from reproduce.evolve.review import candidate_gate_blockers
from reproduce.evolve.state_machine import next_step, transition_evolve_dir


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--evolve-dir", required=True, help="artifacts/evolve/<slug> directory")
    parser.add_argument(
        "--record-phase",
        choices=["candidates_reviewed", "report_reviewed"],
        help="Record a review-gate phase transition before printing status",
    )
    args = parser.parse_args(argv)

    evolve_dir = Path(args.evolve_dir)
    if not (evolve_dir / "evolve-state.json").exists():
        print(json.dumps({"error": f"no evolve-state.json under {evolve_dir}"}, ensure_ascii=False))
        return 1

    if args.record_phase:
        if args.record_phase == "candidates_reviewed":
            blockers = candidate_gate_blockers(evolve_dir)
            if blockers:
                print(json.dumps({"error": "candidate gate not clear", "blockers": blockers}, ensure_ascii=False))
                return 1
        transition_evolve_dir(
            evolve_dir,
            args.record_phase,
            reason=f"review gate recorded: {args.record_phase}",
            producer="tools/evolve_status.py",
        )

    print(json.dumps(next_step(evolve_dir), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

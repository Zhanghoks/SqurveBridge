#!/usr/bin/env python3
"""CLI entry: python reproduce/run.py <dataset> <method>"""

import os
import sys

project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from reproduce.runner.run import main

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Run a Squrve reproduce config from reproduce/configs/<dataset>/<method>.json",
    )
    parser.add_argument("dataset", help="benchmark name, e.g. spider")
    parser.add_argument("method", help="method slug, e.g. dinsql")
    parser.add_argument("--resume", action="store_true", help="resume from the last checkpoint")
    parser.add_argument("--resume-from", default=None, help="resume from a specific checkpoint state file")
    args = parser.parse_args()
    if args.resume or args.resume_from:
        main(args.dataset, args.method, resume=args.resume, resume_from=args.resume_from)
    else:
        main(args.dataset, args.method)

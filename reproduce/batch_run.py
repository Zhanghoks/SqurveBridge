#!/usr/bin/env python3
"""CLI entry: python reproduce/batch_run.py <dataset> <method>"""

import os
import sys

project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from reproduce.runner.batch_run import main

if __name__ == "__main__":
    main()

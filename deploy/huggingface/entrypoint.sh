#!/usr/bin/env bash
set -euo pipefail

export SQURVE_DEPLOYMENT_TARGET=hf-space

python demo/runtime_check.py

exec gunicorn \
  --bind 0.0.0.0:7860 \
  --workers 1 \
  --threads 4 \
  --timeout 180 \
  --access-logfile - \
  --error-logfile - \
  demo.space_server:app

#!/usr/bin/env bash
set -euo pipefail

: "${SQURVE_LLM_PROVIDER:?SQURVE_LLM_PROVIDER is required}"
: "${SQURVE_LLM_MODEL:?SQURVE_LLM_MODEL is required}"

export PI_AGENT_PROVIDER="${PI_AGENT_PROVIDER:-$SQURVE_LLM_PROVIDER}"
export PI_AGENT_MODEL="${PI_AGENT_MODEL:-$SQURVE_LLM_MODEL}"

export SQURVE_DEPLOYMENT_TARGET=hf-space

exec gunicorn \
  --bind 0.0.0.0:7860 \
  --workers 1 \
  --threads 4 \
  --timeout 180 \
  --access-logfile - \
  --error-logfile - \
  demo.space_server:app

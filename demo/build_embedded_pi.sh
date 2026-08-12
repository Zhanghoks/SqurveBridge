#!/usr/bin/env bash
# Install the embedded Pi SDK (@earendil-works/pi-coding-agent) for the demo backend.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

npm ci --prefix "$ROOT/demo" --ignore-scripts

test -d "$ROOT/demo/node_modules/@earendil-works/pi-coding-agent/dist"

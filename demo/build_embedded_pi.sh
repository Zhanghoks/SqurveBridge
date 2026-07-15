#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT/pi"

npm ci --ignore-scripts

TSGO="$PWD/node_modules/.bin/tsgo"
"$TSGO" -p packages/tui/tsconfig.build.json
"$TSGO" -p packages/ai/tsconfig.build.json
"$TSGO" -p packages/agent/tsconfig.build.json
"$TSGO" -p packages/coding-agent/tsconfig.build.json
npm --prefix packages/coding-agent run copy-assets

test -f packages/coding-agent/dist/index.js

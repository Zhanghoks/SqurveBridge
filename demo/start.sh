#!/usr/bin/env bash
# Start SqurveBridge interactive demo (API + React workspace).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RUNTIME_DIR="${ROOT}/tmp/demo-runtime"
API_PORT="${SQURVE_DEMO_API_PORT:-7861}"
WEB_PORT="${SQURVE_DEMO_WEB_PORT:-5173}"
API_HOST="${SQURVE_DEMO_API_HOST:-127.0.0.1}"
WEB_HOST="${SQURVE_DEMO_WEB_HOST:-127.0.0.1}"

mkdir -p "${RUNTIME_DIR}"

log() { printf '[squrve-demo] %s\n' "$*"; }
die() { printf '[squrve-demo] ERROR: %s\n' "$*" >&2; exit 1; }

cleanup_on_fail() {
  local code=$?
  if [[ "${code}" -ne 0 ]]; then
    log "Startup failed; cleaning up…"
    "${ROOT}/demo/stop.sh" >/dev/null 2>&1 || true
  fi
}
trap cleanup_on_fail EXIT

port_in_use() {
  local port="$1"
  if command -v lsof >/dev/null 2>&1; then
    lsof -nP -iTCP:"${port}" -sTCP:LISTEN >/dev/null 2>&1
  else
    return 1
  fi
}

pid_alive() {
  local pid="$1"
  [[ -n "${pid}" ]] && kill -0 "${pid}" 2>/dev/null
}

resolve_python() {
  if [[ -x "${ROOT}/.venv/bin/python" ]]; then
    echo "${ROOT}/.venv/bin/python"
  elif command -v python3 >/dev/null 2>&1; then
    command -v python3
  else
    die "Python not found. Create .venv at repo root first."
  fi
}

wait_http() {
  local url="$1"
  local label="$2"
  local tries="${3:-40}"
  local i
  for ((i = 1; i <= tries; i++)); do
    if curl -fsS --max-time 1 "${url}" >/dev/null 2>&1; then
      return 0
    fi
    sleep 0.25
  done
  die "${label} did not become ready: ${url}"
}

cd "${ROOT}"

if [[ -f "${RUNTIME_DIR}/api.pid" ]] || [[ -f "${RUNTIME_DIR}/web.pid" ]]; then
  api_pid="$(cat "${RUNTIME_DIR}/api.pid" 2>/dev/null || true)"
  web_pid="$(cat "${RUNTIME_DIR}/web.pid" 2>/dev/null || true)"
  if pid_alive "${api_pid}" || pid_alive "${web_pid}" || port_in_use "${API_PORT}" || port_in_use "${WEB_PORT}"; then
    trap - EXIT
    die "Demo already appears running. Use: demo/stop.sh"
  fi
  rm -f "${RUNTIME_DIR}/api.pid" "${RUNTIME_DIR}/web.pid"
fi

if port_in_use "${API_PORT}"; then
  trap - EXIT
  die "API port ${API_PORT} is already in use."
fi
if port_in_use "${WEB_PORT}"; then
  trap - EXIT
  die "Web port ${WEB_PORT} is already in use."
fi

PYTHON="$(resolve_python)"
command -v npm >/dev/null 2>&1 || die "npm not found. Install Node.js first."
command -v curl >/dev/null 2>&1 || die "curl not found."

if [[ ! -d "${ROOT}/demo-app/node_modules" ]]; then
  log "Installing frontend dependencies (npm ci)…"
  (cd "${ROOT}/demo-app" && npm ci)
fi

log "Starting API on http://${API_HOST}:${API_PORT}"
nohup "${PYTHON}" "${ROOT}/demo/api_server.py" --host "${API_HOST}" --port "${API_PORT}" \
  >"${RUNTIME_DIR}/api.log" 2>&1 &
api_pid=$!
echo "${api_pid}" >"${RUNTIME_DIR}/api.pid"

log "Starting frontend on http://${WEB_HOST}:${WEB_PORT}"
cd "${ROOT}/demo-app"
nohup npm run dev -- --host "${WEB_HOST}" --port "${WEB_PORT}" \
  >"${RUNTIME_DIR}/web.log" 2>&1 &
web_pid=$!
echo "${web_pid}" >"${RUNTIME_DIR}/web.pid"
cd "${ROOT}"

wait_http "http://${API_HOST}:${API_PORT}/api/health" "API"
wait_http "http://${WEB_HOST}:${WEB_PORT}/" "Frontend" 60

cat >"${RUNTIME_DIR}/demo.env" <<EOF
API_HOST=${API_HOST}
API_PORT=${API_PORT}
WEB_HOST=${WEB_HOST}
WEB_PORT=${WEB_PORT}
API_PID=${api_pid}
WEB_PID=${web_pid}
STARTED_AT=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
EOF

trap - EXIT
log "SqurveBridge demo is up."
log "  Workspace: http://${WEB_HOST}:${WEB_PORT}"
log "  API:       http://${API_HOST}:${API_PORT}"
log "  Logs:      ${RUNTIME_DIR}/api.log , ${RUNTIME_DIR}/web.log"
log "Stop with:   demo/stop.sh"

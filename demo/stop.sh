#!/usr/bin/env bash
# Stop SqurveBridge interactive demo started by demo/start.sh.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RUNTIME_DIR="${ROOT}/tmp/demo-runtime"
API_PORT="${SQURVE_DEMO_API_PORT:-7861}"
WEB_PORT="${SQURVE_DEMO_WEB_PORT:-5173}"

log() { printf '[squrve-demo] %s\n' "$*"; }

pid_alive() {
  local pid="$1"
  [[ -n "${pid}" ]] && kill -0 "${pid}" 2>/dev/null
}

stop_pid() {
  local label="$1"
  local pid="$2"
  if ! pid_alive "${pid}"; then
    return 0
  fi
  log "Stopping ${label} (pid ${pid})"
  kill "${pid}" 2>/dev/null || true
  local i
  for ((i = 1; i <= 20; i++)); do
    if ! pid_alive "${pid}"; then
      return 0
    fi
    sleep 0.15
  done
  log "Force-killing ${label} (pid ${pid})"
  kill -9 "${pid}" 2>/dev/null || true
}

stop_port_listeners() {
  local port="$1"
  local label="$2"
  if ! command -v lsof >/dev/null 2>&1; then
    return 0
  fi
  local pids
  pids="$(lsof -nP -iTCP:"${port}" -sTCP:LISTEN -t 2>/dev/null || true)"
  if [[ -z "${pids}" ]]; then
    return 0
  fi
  local pid
  for pid in ${pids}; do
    # Skip empty / non-numeric
    [[ "${pid}" =~ ^[0-9]+$ ]] || continue
    stop_pid "${label}@:${port}" "${pid}"
  done
  # Second pass after SIGTERM window
  pids="$(lsof -nP -iTCP:"${port}" -sTCP:LISTEN -t 2>/dev/null || true)"
  for pid in ${pids}; do
    [[ "${pid}" =~ ^[0-9]+$ ]] || continue
    log "Force-clearing ${label}@:${port} (pid ${pid})"
    kill -9 "${pid}" 2>/dev/null || true
  done
}

# Prefer recorded PIDs from start.sh
if [[ -f "${RUNTIME_DIR}/demo.env" ]]; then
  # shellcheck disable=SC1091
  source "${RUNTIME_DIR}/demo.env"
  API_PORT="${API_PORT:-7861}"
  WEB_PORT="${WEB_PORT:-5173}"
fi

api_pid=""
web_pid=""
[[ -f "${RUNTIME_DIR}/api.pid" ]] && api_pid="$(cat "${RUNTIME_DIR}/api.pid" 2>/dev/null || true)"
[[ -f "${RUNTIME_DIR}/web.pid" ]] && web_pid="$(cat "${RUNTIME_DIR}/web.pid" 2>/dev/null || true)"

# Vite often spawns a child; kill the process group when possible.
if pid_alive "${web_pid}"; then
  log "Stopping frontend process tree (pid ${web_pid})"
  kill -- -"${web_pid}" 2>/dev/null || kill "${web_pid}" 2>/dev/null || true
  sleep 0.3
  if pid_alive "${web_pid}"; then
    kill -9 -- -"${web_pid}" 2>/dev/null || kill -9 "${web_pid}" 2>/dev/null || true
  fi
fi

stop_pid "API" "${api_pid}"

# Fallback: clear listeners on known ports (covers orphaned children).
stop_port_listeners "${API_PORT}" "API"
stop_port_listeners "${WEB_PORT}" "Frontend"

rm -f "${RUNTIME_DIR}/api.pid" "${RUNTIME_DIR}/web.pid" "${RUNTIME_DIR}/demo.env"

log "SqurveBridge demo stopped."
log "Logs kept at: ${RUNTIME_DIR}/api.log , ${RUNTIME_DIR}/web.log"
